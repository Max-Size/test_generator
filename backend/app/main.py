import asyncio
import base64
import json
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import TypedDict

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .config import settings
from .diagrams import TikzError, render_tikz, warmup
from .llm import fix_tikz, generate_quiz
from .obs import log, new_request_id, setup_logging, stage
from .schemas import Diagram, GenerateResponse, Question, Quiz, SourceKind
from .text_extract import combine, extract_text


class ExtractDetail(TypedDict):
    filename: str
    processed: int
    total: int


class DiagramsDetail(TypedDict):
    processed: int
    total: int


# emit(stage, detail): при stage="extract" — только ExtractDetail; при stage="generate" —
# только str | None; при stage="diagrams" — только DiagramsDetail. Прокидывается по цепочке
# вызовов вместо job-стора/polling — см. docs/features/generation-progress/api-contract.md.
ProgressEmit = Callable[[str, "ExtractDetail | DiagramsDetail | str | None"], None]

setup_logging()


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    log.info(
        "backend started | model=%s api=%s max_context_chars=%d",
        settings.polza_model,
        settings.polza_base_url,
        settings.max_context_chars,
    )
    await warmup()
    yield


app = FastAPI(title="test_generator API", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALL_TYPES = ["single", "multiple", "true_false", "short"]
DEFAULT_NUM_QUESTIONS = 10


async def _draw_diagram(q: Question, sem: asyncio.Semaphore) -> bool:
    """Скомпилировать q.tikz в SVG и положить в q.diagram. При ошибке — до
    tikz_fix_attempts исправлений через LLM. False — рисунок построить не удалось."""
    tikz = q.tikz or ""
    last_err = ""
    for attempt in range(settings.tikz_fix_attempts + 1):
        if attempt:
            try:
                with stage("llm.fix_tikz", question=q.id, attempt=attempt):
                    tikz = await fix_tikz(q.text, tikz, last_err)
            # любая ошибка исправления (сеть, невалидный JSON) — неудачная попытка;
            # в лог её уже записал stage()
            except Exception:  # noqa: BLE001, S112
                continue
        try:
            async with sem:
                with stage("tikz.render", question=q.id, attempt=attempt + 1) as st:
                    svg = await render_tikz(tikz)
                    st["svg_bytes"] = len(svg)
        except TikzError as e:
            last_err = e.log
            continue
        b64 = base64.b64encode(svg).decode()
        q.diagram = Diagram(image_base64=f"data:image/svg+xml;base64,{b64}", alt_text="")
        return True
    log.warning("вопрос %d удалён: не удалось построить рисунок: %s", q.id, last_err)
    return False


async def _draw_diagrams(quiz: Quiz, emit: ProgressEmit) -> None:
    """Построить рисунки для вопросов с tikz; вопросы с непостроенными рисунками удаляются,
    оставшиеся перенумеровываются 1..n."""
    with_tikz = [q for q in quiz.questions if q.tikz]
    if not with_tikz:
        return
    total = len(with_tikz)
    processed = 0
    emit("diagrams", {"processed": 0, "total": total})
    sem = asyncio.Semaphore(settings.tikz_concurrency)

    async def one(q: Question) -> tuple[Question, bool]:
        nonlocal processed
        ok = await _draw_diagram(q, sem)
        processed += 1
        emit("diagrams", {"processed": processed, "total": total})
        return q, ok

    with stage("diagrams", total=total) as st:
        failed = {id(q) for q, ok in await asyncio.gather(*(one(q) for q in with_tikz)) if not ok}
        quiz.questions = [q for q in quiz.questions if id(q) not in failed]
        for i, q in enumerate(quiz.questions, start=1):
            q.id = i
        st["failed"] = len(failed)
    if not quiz.questions:
        raise HTTPException(502, "Не удалось построить рисунки ни для одного вопроса")


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "model": settings.polza_model}


@app.post("/api/generate")
async def generate(
    files: list[UploadFile] = File(...),
    num_questions: int | None = Form(None),
    question_types: str = Form("single,multiple,true_false"),
    topics: str | None = Form(None),
    source_kinds: str = Form("material"),
) -> StreamingResponse:
    new_request_id()
    req_t0 = time.perf_counter()
    log.info(
        "POST /api/generate | files=%d num_questions=%s types=%r topics=%r source_kinds=%r",
        len(files),
        num_questions,
        question_types,
        topics,
        source_kinds,
    )
    if num_questions is not None and not 1 <= num_questions <= settings.max_questions:
        raise HTTPException(422, f"num_questions должен быть 1..{settings.max_questions}")
    if len(files) > settings.max_files:
        raise HTTPException(422, f"максимум {settings.max_files} файлов")

    types = [t.strip() for t in question_types.split(",") if t.strip() in ALL_TYPES]
    if not types:
        raise HTTPException(422, "не указаны корректные типы вопросов")

    kinds = [
        SourceKind(k)
        for k in dict.fromkeys(s.strip() for s in source_kinds.split(","))
        if k in SourceKind._value2member_map_
    ]
    if not kinds:
        raise HTTPException(422, "не указаны корректные типы источника")

    max_file_bytes = settings.max_file_size_mb * 1024 * 1024

    async def event_stream():
        queue: asyncio.Queue = asyncio.Queue()

        def emit(
            stage_name: str, detail: "ExtractDetail | DiagramsDetail | str | None" = None
        ) -> None:
            queue.put_nowait({"type": "progress", "stage": stage_name, "detail": detail})

        async def run() -> None:
            try:
                parts: list[tuple[str, str]] = []
                with stage("extract_text", files=len(files)) as st:
                    total_bytes = 0
                    for f in files:
                        data = await f.read()
                        name = f.filename or "file"
                        if len(data) > max_file_bytes:
                            raise HTTPException(
                                422,
                                f'файл "{name}" превышает максимальный размер '
                                f"{settings.max_file_size_mb} МБ",
                            )
                        total_bytes += len(data)
                        with stage(f"extract:{name}", bytes=len(data)) as fst:
                            text = await extract_text(name, data, emit)
                            fst["chars"] = len(text)
                        parts.append((name, text))
                    st["total_bytes"] = total_bytes
                    st["total_chars"] = sum(len(t) for _, t in parts)

                with stage("combine", limit=settings.max_context_chars) as st:
                    context, truncated_files = combine(parts, settings.max_context_chars)
                    truncated = bool(truncated_files)
                    st["chars"] = len(context)
                    st["truncated"] = truncated
                    st["truncated_files"] = len(truncated_files)
                if not context.strip():
                    raise HTTPException(422, "из файлов не удалось извлечь текст")

                auto_count = num_questions is None and SourceKind.sample in kinds
                n = (
                    num_questions
                    if num_questions is not None
                    else (None if auto_count else DEFAULT_NUM_QUESTIONS)
                )

                with stage("llm.generate_quiz", n=n) as st:
                    quiz: Quiz = await generate_quiz(context, n, types, topics, kinds, emit)
                    if len(quiz.questions) > settings.max_questions:
                        log.warning(
                            "модель вернула %d вопросов, обрезаем до %d",
                            len(quiz.questions),
                            settings.max_questions,
                        )
                        quiz.questions = quiz.questions[: settings.max_questions]
                    st["questions"] = len(quiz.questions)
                    st["types"] = "/".join(sorted({q.type.value for q in quiz.questions}))

                await _draw_diagrams(quiz, emit)

                total = time.perf_counter() - req_t0
                log.info(
                    "DONE /api/generate in %.2fs | source_chars=%d truncated=%s questions=%d",
                    total,
                    len(context),
                    truncated,
                    len(quiz.questions),
                )
                response = GenerateResponse(
                    quiz=quiz,
                    source_chars=len(context),
                    truncated=truncated,
                    truncated_files=truncated_files,
                )
                await queue.put({"type": "result", "data": response.model_dump()})
            except HTTPException as e:
                await queue.put({"type": "error", "status": e.status_code, "detail": e.detail})
            except Exception as e:  # noqa: BLE001
                await queue.put({"type": "error", "status": 500, "detail": str(e)})
            finally:
                await queue.put(None)

        task = asyncio.create_task(run())
        try:
            while (item := await queue.get()) is not None:
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        finally:
            await task

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
