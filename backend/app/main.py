import time

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .llm import analyze_sources, generate_quiz
from .obs import log, new_request_id, setup_logging, stage
from .schemas import GenerateResponse, Quiz, SourceAnalysis, SourceKind
from .text_extract import combine, extract_text

setup_logging()

app = FastAPI(title="test_generator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALL_TYPES = ["single", "multiple", "true_false", "short"]
# auto — бэкенд сам определяет тип документа; material — считать теорией;
# specification — трактовать как спецификацию экзамена / образец варианта
SOURCE_MODES = ["auto", "material", "specification"]


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


@app.post("/api/generate", response_model=GenerateResponse)
async def generate(
    files: list[UploadFile] = File(...),
    num_questions: int = Form(...),
    question_types: str = Form("single,multiple,true_false"),
    topics: str | None = Form(None),
    source_mode: str = Form("auto"),
) -> GenerateResponse:
    new_request_id()
    req_t0 = time.perf_counter()
    log.info(
        "POST /api/generate | files=%d num_questions=%s types=%r topics=%r source_mode=%r",
        len(files),
        num_questions,
        question_types,
        topics,
        source_mode,
    )
    if source_mode not in SOURCE_MODES:
        raise HTTPException(422, f"source_mode должен быть одним из {SOURCE_MODES}")

    if not 1 <= num_questions <= settings.max_questions:
        raise HTTPException(422, f"num_questions должен быть 1..{settings.max_questions}")
    if len(files) > settings.max_files:
        raise HTTPException(422, f"максимум {settings.max_files} файлов")

    types = [t.strip() for t in question_types.split(",") if t.strip() in ALL_TYPES]
    if not types:
        raise HTTPException(422, "не указаны корректные типы вопросов")

    max_file_bytes = settings.max_file_size_mb * 1024 * 1024
    parts: list[tuple[str, str]] = []
    with stage("extract_text", files=len(files)) as st:
        total_bytes = 0
        for f in files:
            data = await f.read()
            name = f.filename or "file"
            if len(data) > max_file_bytes:
                raise HTTPException(
                    422,
                    f'файл "{name}" превышает максимальный размер {settings.max_file_size_mb} МБ',
                )
            total_bytes += len(data)
            with stage(f"extract:{name}", bytes=len(data)) as fst:
                text = await extract_text(name, data)
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

    analysis: SourceAnalysis | None = None
    if source_mode == "material":
        analysis = SourceAnalysis(kinds=[SourceKind.material], summary="учебный материал")
    else:
        with stage("llm.analyze_sources") as st:
            analysis = await analyze_sources(context)
            if source_mode == "specification" and SourceKind.specification not in analysis.kinds:
                analysis.kinds = [*analysis.kinds, SourceKind.specification]
            st["kinds"] = "/".join(k.value for k in analysis.kinds)
            st["topics"] = len(analysis.topics)
            st["samples"] = len(analysis.sample_tasks)

    with stage("llm.generate_quiz", n=num_questions) as st:
        quiz: Quiz = await generate_quiz(context, num_questions, types, topics, analysis)
        st["questions"] = len(quiz.questions)
        st["types"] = "/".join(sorted({q.type.value for q in quiz.questions}))

    total = time.perf_counter() - req_t0
    log.info(
        "DONE /api/generate in %.2fs | source_chars=%d truncated=%s questions=%d",
        total,
        len(context),
        truncated,
        len(quiz.questions),
    )
    return GenerateResponse(
        quiz=quiz,
        source_chars=len(context),
        truncated=truncated,
        truncated_files=truncated_files,
        analysis=analysis,
    )
