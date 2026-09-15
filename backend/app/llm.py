"""Клиент Polza.ai (OpenAI-совместимый chat completions): разбор типа документа,
сборка промпта, запрос JSON по схеме, ретрай при кривом ответе, vision-распознавание
страниц PDF."""
import base64
import json
import time

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

from .config import settings
from .obs import log, stage
from .schemas import Quiz, SourceAnalysis, SourceKind

SYSTEM_PROMPT = (
    "Ты — генератор экзаменационных тестов. На основе предоставленного материала "
    "составь вопросы строго по его содержанию. Не выдумывай факты, которых нет в тексте. "
    "Формулировки вопросов и вариантов — на языке исходного материала. "
    "Верни ТОЛЬКО JSON по заданной схеме, без markdown и комментариев."
)

ANALYZE_SYSTEM_PROMPT = (
    "Ты — методист. Тебе дают текст загруженных пользователем документов. "
    "Определи, какие категории информации в нём есть:\n"
    "- material: учебная теория, конспект, параграф — то, по содержанию чего можно спросить;\n"
    "- specification: спецификация/кодификатор экзамена — описание структуры работы, "
    "перечень тем и элементов содержания, типы и число заданий, уровни сложности, критерии;\n"
    "- sample: образец варианта, демоверсия, примеры конкретных заданий.\n"
    "Один документ может содержать несколько категорий сразу. "
    "Извлеки структуру экзамена, список тем/элементов содержания, типы заданий и примеры "
    "заданий, если они есть. Верни ТОЛЬКО JSON по заданной схеме, без markdown."
)


VISION_SYSTEM_PROMPT = (
    "Ты аккуратно переносишь содержимое страницы документа в Markdown. "
    "Сохраняй заголовки, списки, порядок абзацев и таблицы (Markdown-таблицами). "
    "Математические формулы записывай в LaTeX: $...$ для строчных, $$...$$ для выключных. "
    "Каждый график, диаграмму, чертёж или иллюстрацию описывай словами в квадратных "
    "скобках: [Рисунок: ...] — с подписями, обозначениями осей и числовыми значениями. "
    "Не добавляй ничего, чего нет на странице. Верни только Markdown, без пояснений."
)


def _strictify(node):
    """Привести JSON-схему Pydantic к виду, который принимает strict-режим
    OpenAI/Polza.ai: у каждого object — additionalProperties:false и все поля
    в required; поля default удаляются. Рекурсивно по properties/items/anyOf/$defs.
    """
    if isinstance(node, dict):
        node.pop("default", None)
        if node.get("type") == "object" and "properties" in node:
            node["additionalProperties"] = False
            node["required"] = list(node["properties"].keys())
        for key in ("properties", "$defs"):
            for sub in node.get(key, {}).values():
                _strictify(sub)
        for key in ("items", "additionalProperties"):
            if isinstance(node.get(key), dict):
                _strictify(node[key])
        for key in ("anyOf", "oneOf", "allOf", "prefixItems"):
            for sub in node.get(key, []):
                _strictify(sub)
    return node


# JSON-схемы — передаются модели через response_format=json_schema
QUIZ_JSON_SCHEMA = _strictify(Quiz.model_json_schema())
ANALYSIS_JSON_SCHEMA = _strictify(SourceAnalysis.model_json_schema())


def _format_analysis(a: SourceAnalysis) -> str:
    """Человекочитаемая врезка про экзамен для промпта генерации."""
    lines = [f"Что это за материал: {a.summary}"]
    if a.exam_structure:
        lines.append(f"Структура экзамена: {a.exam_structure}")
    if a.topics:
        lines.append("Темы / элементы содержания:\n- " + "\n- ".join(a.topics))
    if a.task_types:
        lines.append("Типы заданий: " + ", ".join(a.task_types))
    if a.sample_tasks:
        lines.append("Примеры заданий из образца варианта:\n- " + "\n- ".join(a.sample_tasks))
    return "\n".join(lines)


def build_user_prompt(
    context: str,
    num_questions: int,
    types: list[str],
    topics: str | None,
    analysis: SourceAnalysis | None = None,
) -> str:
    spec_like = analysis is not None and (
        SourceKind.specification in analysis.kinds or SourceKind.sample in analysis.kinds
    )
    has_material = analysis is None or SourceKind.material in analysis.kinds

    parts: list[str] = []

    if spec_like:
        parts.append(
            "ВАЖНО: приложенный документ — это не учебная теория, а описание экзамена "
            "(его структура, перечень тем и/или образец варианта). "
            "Не задавай вопросы про сам документ (сроки, регламент, число баллов, авторов). "
            f"Твоя задача — составить НОВЫЙ тест из {num_questions} заданий, который "
            "воспроизводит темы, типы заданий и уровень сложности описанного экзамена, "
            "по образцу приведённого варианта. Придумывай свои условия и числа, "
            "равномерно покрывая перечисленные темы."
        )
        if has_material:
            parts.append(
                "Если в документе есть и теоретический материал — опирайся на него как на "
                "источник фактов, но вопросы всё равно строй в формате заданий экзамена."
            )
        parts.append(_format_analysis(analysis))
        parts.append(f"\nПолный текст документа для справки:\n\"\"\"\n{context}\n\"\"\"")
    else:
        parts.append(f"Материал:\n\"\"\"\n{context}\n\"\"\"")
        parts.append(f"\nСоставь ровно {num_questions} вопросов.")

    parts += [
        f"Допустимые типы вопросов: {', '.join(types)}.",
        "Поле type — одно из: single, multiple, true_false, short.",
        "Для single/multiple/true_false заполни options и correct_indexes (индексы с нуля).",
        "Для true_false options = [\"Верно\", \"Неверно\"].",
        "Для short заполни correct_text.",
        "id нумеруй с 1. По возможности добавляй краткое explanation.",
    ]
    if topics:
        parts.append(f"Дополнительно сфокусируйся на темах: {topics}.")
    return "\n".join(parts)


def _response_format(name: str, schema: dict) -> dict:
    if settings.polza_json_schema:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": name,
                "strict": settings.polza_json_schema_strict,
                "schema": schema,
            },
        }
    return {"type": "json_object"}


def _content_len(content) -> int:
    """Длина текстовой части сообщения (content может быть строкой или списком частей)."""
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(len(p.get("text", "")) for p in content if isinstance(p, dict))
    return 0


async def _call_llm(
    messages: list[dict],
    attempt: int,
    response_format: dict | None = None,
    model: str | None = None,
) -> str:
    if not settings.polza_api_key:
        raise HTTPException(500, "POLZA_API_KEY не задан")

    payload = {
        "model": model or settings.polza_model,
        "messages": messages,
        "stream": False,
        "temperature": settings.polza_temperature,
    }
    if response_format is not None:
        payload["response_format"] = response_format
    url = f"{settings.polza_base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.polza_api_key}"}
    prompt_chars = sum(_content_len(m["content"]) for m in messages)
    log.info(
        "polza call attempt=%d | prompt_chars=%d model=%s",
        attempt, prompt_chars, payload["model"],
    )
    log.debug("polza prompt:\n%s", messages[-1]["content"])

    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=settings.polza_timeout) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            detail = e.response.text[:500]
            code = e.response.status_code
            hint = {
                401: "неверный API-ключ",
                402: "недостаточно средств на балансе Polza.ai",
                429: "превышен лимит запросов",
            }.get(code, "ошибка API")
            raise HTTPException(502, f"Polza.ai {code} ({hint}): {detail}")
        except httpx.HTTPError as e:
            raise HTTPException(502, f"Polza.ai недоступен ({url}): {e}")
    wall = time.perf_counter() - t0

    body = resp.json()
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise HTTPException(502, f"Polza.ai вернул неожиданный ответ: {json.dumps(body)[:500]}")

    usage = body.get("usage") or {}
    log.info(
        "polza done attempt=%d | wall=%.2fs prompt_tokens=%s completion_tokens=%s "
        "total_tokens=%s out_chars=%d finish=%s",
        attempt,
        wall,
        usage.get("prompt_tokens", "?"),
        usage.get("completion_tokens", "?"),
        usage.get("total_tokens", "?"),
        len(content or ""),
        body["choices"][0].get("finish_reason", "?"),
    )
    log.debug("polza raw response:\n%s", content)
    if not content:
        raise HTTPException(502, "Polza.ai вернул пустой ответ")
    return content


async def transcribe_page(png_bytes: bytes, page_no: int) -> str:
    """Распознать одну страницу PDF (PNG) в Markdown через vision-модель.
    При сбое возвращает пустую строку — вызывающий код откатится на текстовый слой."""
    b64 = base64.b64encode(png_bytes).decode()
    messages = [
        {"role": "system", "content": VISION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"Страница {page_no}. Перенеси её содержимое в Markdown."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ],
        },
    ]
    try:
        return await _call_llm(messages, attempt=1, model=settings.vision_model)
    except HTTPException as e:
        log.warning("vision-распознавание страницы %d не удалось: %s", page_no, e.detail)
        return ""


async def analyze_sources(context: str) -> SourceAnalysis:
    """Предварительный разбор: понять, теория это, спецификация экзамена или образец
    варианта. При сбое считаем материал обычной теорией (мягкая деградация)."""
    messages = [
        {"role": "system", "content": ANALYZE_SYSTEM_PROMPT},
        {"role": "user", "content": f"Текст документов:\n\"\"\"\n{context}\n\"\"\""},
    ]
    fmt = _response_format("source_analysis", ANALYSIS_JSON_SCHEMA)
    try:
        raw = await _call_llm(messages, attempt=1, response_format=fmt)
        analysis = SourceAnalysis.model_validate_json(raw)
    except (HTTPException, ValidationError, json.JSONDecodeError) as e:
        log.warning("разбор типа документа не удался (%s) — считаем теорией", e)
        return SourceAnalysis(kinds=[SourceKind.material], summary="учебный материал")
    if not analysis.kinds:
        analysis.kinds = [SourceKind.material]
    return analysis


async def generate_quiz(
    context: str,
    num_questions: int,
    types: list[str],
    topics: str | None,
    analysis: SourceAnalysis | None = None,
) -> Quiz:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": build_user_prompt(context, num_questions, types, topics, analysis),
        },
    ]
    quiz_format = _response_format("quiz", QUIZ_JSON_SCHEMA)

    last_err = ""
    for attempt in range(1, 3):
        raw = await _call_llm(messages, attempt, quiz_format)
        with stage(f"validate attempt={attempt}", raw_chars=len(raw)) as st:
            try:
                quiz = Quiz.model_validate_json(raw)
                st["questions"] = len(quiz.questions)
                st["ok"] = True
                return quiz
            except (ValidationError, json.JSONDecodeError) as e:
                last_err = str(e).splitlines()[0]
                st["ok"] = False
                st["err"] = last_err
        log.warning("LLM ответ не прошёл валидацию (attempt=%d): %s — ретрай", attempt, last_err)
        messages.append({"role": "assistant", "content": raw})
        messages.append({
            "role": "user",
            "content": f"JSON не прошёл валидацию: {last_err}. Верни исправленный JSON по схеме.",
        })

    raise HTTPException(502, f"LLM вернул невалидный тест после ретрая: {last_err}")
