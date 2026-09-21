"""Клиент Polza.ai (OpenAI-совместимый chat completions): сборка промпта, запрос JSON по схеме, ретрай при кривом ответе, vision-распознавание
страниц PDF."""
import base64
import json
import time

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

from .config import settings
from .obs import log, stage
from .schemas import Quiz, SourceKind

SYSTEM_PROMPT = (
    "Ты — генератор экзаменационных тестов. На основе предоставленного материала "
    "составь вопросы строго по его содержанию. Не выдумывай факты, которых нет в тексте. "
    "Формулировки вопросов и вариантов — на языке исходного материала. "
    "Всю математику (дроби, степени, корни, формулы) записывай в LaTeX: $...$ для строчных, "
    "$$...$$ для выключных; дроби только через \\frac{числитель}{знаменатель}, а не a/b. "
    "Верни ТОЛЬКО JSON по заданной схеме, без markdown и комментариев."
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


def build_user_prompt(
    context: str,
    num_questions: int | None,
    types: list[str],
    topics: str | None,
    source_kinds: list[SourceKind],
) -> str:
    spec_like = SourceKind.specification in source_kinds or SourceKind.sample in source_kinds
    has_material = SourceKind.material in source_kinds

    parts: list[str] = []
    count_phrase = (
        f"{num_questions} заданий"
        if num_questions is not None
        else "столько заданий, сколько их в приведённом образце варианта "
        f"(не более {settings.max_questions})"
    )

    if spec_like:
        goals = []
        if SourceKind.specification in source_kinds:
            goals.append("воспроизводи перечисленные темы и структуру")
        if SourceKind.sample in source_kinds:
            goals.append(
                "действуй по образцу приведённых заданий, придумывай свои условия и числа"
            )
        parts.append(
            "ВАЖНО: приложенный документ — это не учебная теория, а описание экзамена "
            "(его структура, перечень тем и/или образец варианта). "
            "Не задавай вопросы про сам документ (сроки, регламент, число баллов, авторов). "
            f"Твоя задача — составить НОВЫЙ тест из {count_phrase}, который "
            "воспроизводит темы, типы заданий и уровень сложности описанного экзамена: "
            + "; ".join(goals)
            + ". Равномерно покрывай темы."
        )
        if has_material:
            parts.append(
                "Если в документе есть и теоретический материал — опирайся на него как на "
                "источник фактов, но вопросы всё равно строй в формате заданий экзамена."
            )
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


async def generate_quiz(
    context: str,
    num_questions: int | None,
    types: list[str],
    topics: str | None,
    source_kinds: list[SourceKind],
) -> Quiz:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": build_user_prompt(context, num_questions, types, topics, source_kinds),
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
