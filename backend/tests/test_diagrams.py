import asyncio

import pymupdf
from fastapi.testclient import TestClient

from app import text_extract
from app.config import settings
from app.llm import QUIZ_JSON_SCHEMA, PageDiagram, PageTranscription
from app.main import app
from app.schemas import Question, QuestionType, Quiz

client = TestClient(app)


def _pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Text")
    page.draw_line((72, 100), (300, 100))
    return doc.tobytes()


def test_crop_and_cache(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "ingest_cache_dir", str(tmp_path))
    calls = []

    async def fake(png, n):
        calls.append(n)
        return PageTranscription(
            markdown="A [Рисунок: line | diagram_id=d1] [Рисунок: bad | diagram_id=d2]",
            diagrams=[
                PageDiagram(id="d1", alt_text="line", bbox=[0.1, 0.1, 0.5, 0.3]),
                PageDiagram(id="d2", alt_text="bad", bbox=[0.5, 0.5, 0.5, 0.9]),
            ],
        )

    monkeypatch.setattr(text_extract, "transcribe_page", fake)
    data = _pdf()
    text, diagrams = asyncio.run(text_extract.extract_text("a.pdf", data))
    assert len(diagrams) == 1
    did, png = next(iter(diagrams.items()))
    assert did.endswith("_p1_d1") and f"diagram_id={did}]" in text
    assert png.startswith(b"\x89PNG")

    text2, diagrams2 = asyncio.run(text_extract.extract_text("a.pdf", data))
    assert calls == [1] and text2 == text and diagrams2 == diagrams


def _quiz_with(diagram_id):
    async def gen(context, n, types, topics, kinds):
        return Quiz(title="t", questions=[Question(
            id=1, type=QuestionType.short, text="q", correct_text="a", diagram_id=diagram_id)])
    return gen


def _post(monkeypatch, diagram_id):
    async def fake_extract(name, data):
        return "[Рисунок: числовая прямая | diagram_id=x1]", {"x1": b"\x89PNGdata"}

    monkeypatch.setattr("app.main.extract_text", fake_extract)
    monkeypatch.setattr("app.main.generate_quiz", _quiz_with(diagram_id))
    r = client.post("/api/generate", files={"files": ("a.pdf", b"x")},
                    data={"num_questions": 1})
    assert r.status_code == 200
    return r.json()["quiz"]["questions"][0]


def test_diagram_resolved_and_id_hidden(monkeypatch) -> None:
    q = _post(monkeypatch, "x1")
    assert q["diagram"]["image_base64"].startswith("data:image/png;base64,")
    assert q["diagram"]["alt_text"] == "числовая прямая"
    assert "diagram_id" not in q


def test_unknown_diagram_id_gives_null(monkeypatch) -> None:
    q = _post(monkeypatch, "nope")
    assert q["diagram"] is None and "diagram_id" not in q


def test_llm_schema_hides_diagram() -> None:
    props = QUIZ_JSON_SCHEMA["$defs"]["Question"]["properties"]
    assert "diagram_id" in props and "diagram" not in props
