import asyncio
import base64
import json
import re
import time
from collections.abc import Callable
from typing import TypedDict

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .config import settings
from .llm import generate_quiz
from .obs import log, new_request_id, setup_logging, stage
from .schemas import Diagram, GenerateResponse, Quiz, SourceKind
from .text_extract import combine, extract_text


class ExtractDetail(TypedDict):
    filename: str
    processed: int
    total: int


# emit(stage, detail): при stage="extract" — только ExtractDetail; при stage="generate" —
# только str | None. Прокидывается по цепочке вызовов вместо job-стора/polling —
# см. docs/features/generation-progress/api-contract.md.
ProgressEmit = Callable[[str, "ExtractDetail | str | None"], None]

setup_logging()

app = FastAPI(title="test_generator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALL_TYPES = ["single", "multiple", "true_false", "short"]
DEFAULT_NUM_QUESTIONS = 10
_PLACEHOLDER_RE = re.compile(r"\[Рисунок:\s*(.*?)\s*\|\s*diagram_id=([^\]\s]+)\s*\]", re.DOTALL)

@app.on_event("startup")
async def _startup() -> None:
    log.info(
        "backend started | model=%s api=%s max_context_chars=%d",
        settings.polza_model,
        settings.polza_base_url,
        settings.max_context_chars,
    )


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

        def emit(stage_name: str, detail: "ExtractDetail | str | None" = None) -> None:
            queue.put_nowait({"type": "progress", "stage": stage_name, "detail": detail})

        async def run() -> None:
            try:
                parts: list[tuple[str, str]] = []
                all_diagrams: dict[str, bytes] = {}
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
                            text, diagrams = await extract_text(name, data, emit)
                            fst["chars"] = len(text)
                        parts.append((name, text))
                        all_diagrams.update(diagrams)
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

                alt_texts = {did: alt for alt, did in _PLACEHOLDER_RE.findall(context)}
                for q in quiz.questions:
                    if q.diagram_id and q.diagram_id in all_diagrams:
                        b64 = base64.b64encode(all_diagrams[q.diagram_id]).decode()
                        q.diagram = Diagram(
                            image_base64=f"data:image/png;base64,{b64}",
                            alt_text=alt_texts.get(q.diagram_id, ""),
                        )
                    elif q.diagram_id:
                        log.warning(
                            "вопрос %d ссылается на неизвестный diagram_id=%s", q.id, q.diagram_id
                        )

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
