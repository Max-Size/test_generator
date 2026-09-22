import asyncio

import pymupdf
from fastapi.testclient import TestClient

from app import llm, text_extract
from app.config import settings
from app.llm import PageTranscription
from app.main import app
from app.schemas import Question, QuestionType, Quiz, SourceKind

from .conftest import parse_sse, sse_result

client = TestClient(app)


def _collector():
    events: list[tuple[str, object]] = []

    def emit(stage, detail=None):
        events.append((stage, detail))

    return emit, events


def test_extract_text_emits_filename_only_for_txt(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "ingest_cache_dir", str(tmp_path))
    emit, events = _collector()

    asyncio.run(text_extract.extract_text("a.txt", b"hello", emit))

    assert events == [("extract", {"filename": "a.txt", "processed": 0, "total": 0})]


def test_from_pdf_emits_local_pass_then_vision_progress(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "ingest_cache_dir", str(tmp_path))
    doc = pymupdf.open()
    for _ in range(2):
        page = doc.new_page()
        page.insert_text((72, 72), "some regular text on this page")
    data = doc.tobytes()

    # page 1 (index 1) is "heavy" and needs vision, page 0 stays local
    monkeypatch.setattr(text_extract, "_page_needs_vision", lambda page, text: page.number == 1)

    async def fake_transcribe(png, n):
        return PageTranscription(markdown="recognized")

    monkeypatch.setattr(text_extract, "transcribe_page", fake_transcribe)

    emit, events = _collector()
    asyncio.run(text_extract._from_pdf(data, "f.pdf", emit))

    assert events[0] == ("extract", {"filename": "f.pdf", "processed": 1, "total": 2})
    assert events[-1] == ("extract", {"filename": "f.pdf", "processed": 2, "total": 2})
    assert len(events) == 2


def test_generate_quiz_emits_progress_and_retry_detail(monkeypatch) -> None:
    attempts = []
    valid_quiz_json = Quiz(
        title="t",
        questions=[Question(id=1, type=QuestionType.short, text="q", correct_text="a")],
    ).model_dump_json()

    async def fake_call_llm(messages, attempt, response_format=None, model=None):
        attempts.append(attempt)
        return "not json" if attempt == 1 else valid_quiz_json

    monkeypatch.setattr(llm, "_call_llm", fake_call_llm)

    emit, events = _collector()
    quiz = asyncio.run(
        llm.generate_quiz("ctx", 1, ["short"], None, [SourceKind.material], emit)
    )

    assert quiz.title == "t"
    assert events == [
        ("generate", None),
        ("generate", "ответ модели не прошёл проверку — генерируем заново"),
    ]
    assert attempts == [1, 2]


def test_generate_quiz_single_attempt_emits_once(monkeypatch) -> None:
    valid_quiz_json = Quiz(
        title="t",
        questions=[Question(id=1, type=QuestionType.short, text="q", correct_text="a")],
    ).model_dump_json()

    async def fake_call_llm(messages, attempt, response_format=None, model=None):
        return valid_quiz_json

    monkeypatch.setattr(llm, "_call_llm", fake_call_llm)

    emit, events = _collector()
    asyncio.run(llm.generate_quiz("ctx", 1, ["short"], None, [SourceKind.material], emit))

    assert events == [("generate", None)]


async def _fake_generate_quiz_recording(context, num_questions, types, topics, source_kinds, emit):
    emit("generate", None)
    return Quiz(
        title="Тест",
        questions=[Question(id=1, type=QuestionType.short, text="q", correct_text="a")],
    )


def test_progress_events_ordered_extract_then_generate(monkeypatch) -> None:
    monkeypatch.setattr("app.main.generate_quiz", _fake_generate_quiz_recording)

    response = client.post(
        "/api/generate",
        files=[
            ("files", ("f1.txt", b"Material one.", "text/plain")),
            ("files", ("f2.txt", b"Material two.", "text/plain")),
        ],
        data={"num_questions": 1, "source_kinds": "material"},
    )

    assert response.status_code == 200
    events = parse_sse(response)
    types = [e["type"] for e in events]
    stages = [e["stage"] for e in events if e["type"] == "progress"]

    # ровно один result в конце
    assert types[-1] == "result"
    assert types.count("result") == 1
    assert types.count("error") == 0

    # extract-события идут раньше generate-событий, третьего шага нет
    assert set(stages) <= {"extract", "generate"}
    first_generate = stages.index("generate")
    assert all(s == "extract" for s in stages[:first_generate])
    assert all(s == "generate" for s in stages[first_generate:])

    extract_events = [e for e in events if e.get("stage") == "extract"]
    assert {e["detail"]["filename"] for e in extract_events} == {"f1.txt", "f2.txt"}
    assert all(e["detail"]["total"] == 0 for e in extract_events)


def test_unsupported_format_gives_error_event() -> None:
    response = client.post(
        "/api/generate",
        files={"files": ("a.xyz", b"whatever", "application/octet-stream")},
        data={"num_questions": 1, "source_kinds": "material"},
    )

    assert response.status_code == 200
    events = parse_sse(response)
    error = next(e for e in events if e["type"] == "error")
    assert error["status"] == 415
    assert "a.xyz" in error["detail"]


def test_llm_failure_after_retries_gives_error_event(monkeypatch) -> None:
    async def fake_call_llm(messages, attempt, response_format=None, model=None):
        return "not json"

    monkeypatch.setattr(llm, "_call_llm", fake_call_llm)
    monkeypatch.setattr("app.main.generate_quiz", llm.generate_quiz)

    response = client.post(
        "/api/generate",
        files={"files": ("f1.txt", b"Material.", "text/plain")},
        data={"num_questions": 1, "source_kinds": "material"},
    )

    assert response.status_code == 200
    events = parse_sse(response)
    error = next(e for e in events if e["type"] == "error")
    assert error["status"] == 502
    assert "невалидный тест" in error["detail"]

    progress_stages = [e["stage"] for e in events if e["type"] == "progress"]
    assert progress_stages.count("generate") == 2


def test_result_event_has_full_generate_response(monkeypatch) -> None:
    monkeypatch.setattr("app.main.generate_quiz", _fake_generate_quiz_recording)

    response = client.post(
        "/api/generate",
        files={"files": ("f1.txt", b"Material.", "text/plain")},
        data={"num_questions": 1, "source_kinds": "material"},
    )

    body = sse_result(response)
    assert body["quiz"]["title"] == "Тест"
    assert "source_chars" in body and "truncated" in body and "truncated_files" in body
