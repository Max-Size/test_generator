from fastapi.testclient import TestClient

from app.config import settings
from app.llm import build_user_prompt
from app.main import app
from app.schemas import Question, QuestionType, Quiz, SourceKind

from .conftest import parse_sse, sse_result

client = TestClient(app)


async def _fake_generate_quiz(context, num_questions, types, topics, source_kinds, emit) -> Quiz:
    return Quiz(
        title="Тест",
        questions=[
            Question(
                id=1,
                type=QuestionType.short,
                text="Вопрос?",
                correct_text="Ответ",
            )
        ],
    )


def test_file_over_size_limit_rejected(monkeypatch) -> None:
    monkeypatch.setattr(settings, "max_file_size_mb", 1)
    oversized = b"x" * (2 * 1024 * 1024)

    response = client.post(
        "/api/generate",
        files={"files": ("big.txt", oversized, "text/plain")},
        data={"num_questions": 1, "source_kinds": "material"},
    )

    assert response.status_code == 200
    events = parse_sse(response)
    error = next(e for e in events if e["type"] == "error")
    assert error["status"] == 422
    assert "big.txt" in error["detail"]
    assert "1 МБ" in error["detail"]


def test_generate_reports_dropped_file(monkeypatch) -> None:
    monkeypatch.setattr("app.main.generate_quiz", _fake_generate_quiz)

    text1 = "Материал первого файла."
    chunk1 = f"### f1.txt\n{text1}"
    limit = len(chunk1)  # f1 укладывается ровно, f2 не остаётся места вовсе
    monkeypatch.setattr(type(settings), "max_context_chars", property(lambda self: limit))

    response = client.post(
        "/api/generate",
        files=[
            ("files", ("f1.txt", text1.encode(), "text/plain")),
            ("files", ("f2.txt", "Материал второго файла.".encode(), "text/plain")),
        ],
        data={"num_questions": 1, "source_kinds": "material"},
    )

    assert response.status_code == 200
    body = sse_result(response)
    assert body["truncated"] is True
    assert body["truncated_files"] == [{"filename": "f2.txt", "reason": "dropped"}]
    assert body["source_chars"] == len(chunk1)


def test_generate_no_truncation_when_everything_fits(monkeypatch) -> None:
    monkeypatch.setattr("app.main.generate_quiz", _fake_generate_quiz)

    response = client.post(
        "/api/generate",
        files={"files": ("f1.txt", b"Short material.", "text/plain")},
        data={"num_questions": 1, "source_kinds": "material"},
    )

    assert response.status_code == 200
    body = sse_result(response)
    assert body["truncated"] is False
    assert body["truncated_files"] == []


def test_invalid_source_kinds_rejected() -> None:
    response = client.post(
        "/api/generate",
        files={"files": ("f1.txt", b"Text.", "text/plain")},
        data={"num_questions": 1, "source_kinds": "bogus, ,"},
    )
    assert response.status_code == 422


def test_source_kinds_defaults_to_material(monkeypatch) -> None:
    seen = {}

    async def fake(context, num_questions, types, topics, source_kinds, emit) -> Quiz:
        seen["kinds"] = source_kinds
        return await _fake_generate_quiz(context, num_questions, types, topics, source_kinds, emit)

    monkeypatch.setattr("app.main.generate_quiz", fake)
    response = client.post(
        "/api/generate",
        files={"files": ("f1.txt", b"Text.", "text/plain")},
        data={"num_questions": 1},
    )
    assert response.status_code == 200
    body = sse_result(response)
    assert "analysis" not in body
    assert seen["kinds"] == [SourceKind.material]


def test_build_user_prompt_branches() -> None:
    material = build_user_prompt("CTX", 3, ["single"], None, [SourceKind.material])
    assert "Материал:" in material and "НОВЫЙ тест" not in material

    both = build_user_prompt(
        "CTX", 3, ["single"], None, [SourceKind.specification, SourceKind.sample]
    )
    assert "перечисленные темы и структуру" in both
    assert "по образцу приведённых заданий" in both
    assert "опирайся на него" not in both

    with_material = build_user_prompt(
        "CTX", 3, ["single"], None, [SourceKind.sample, SourceKind.material]
    )
    assert "опирайся на него" in with_material


def _capture(monkeypatch, seen, n_questions=1):
    async def fake(context, num_questions, types, topics, source_kinds, emit) -> Quiz:
        seen["n"] = num_questions
        q = Question(id=1, type=QuestionType.short, text="В?", correct_text="О")
        return Quiz(title="Тест", questions=[q.model_copy(update={"id": i}) for i in range(n_questions)])

    monkeypatch.setattr("app.main.generate_quiz", fake)


def _post(data):
    return client.post(
        "/api/generate", files={"files": ("f1.txt", b"Text.", "text/plain")}, data=data
    )


def test_auto_count_with_sample(monkeypatch) -> None:
    seen = {}
    _capture(monkeypatch, seen)
    r = _post({"source_kinds": "sample"})
    assert r.status_code == 200
    sse_result(r)
    assert seen["n"] is None


def test_default_count_without_sample(monkeypatch) -> None:
    seen = {}
    _capture(monkeypatch, seen)
    r = _post({"source_kinds": "material"})
    assert r.status_code == 200
    sse_result(r)
    assert seen["n"] == 10


def test_explicit_count_wins_and_validated(monkeypatch) -> None:
    seen = {}
    _capture(monkeypatch, seen)
    r = _post({"source_kinds": "sample", "num_questions": 5})
    assert r.status_code == 200
    sse_result(r)
    assert seen["n"] == 5
    assert _post({"num_questions": settings.max_questions + 1}).status_code == 422


def test_truncates_over_max(monkeypatch) -> None:
    _capture(monkeypatch, {}, n_questions=settings.max_questions + 5)
    r = _post({"source_kinds": "sample"})
    body = sse_result(r)
    assert len(body["quiz"]["questions"]) == settings.max_questions


def test_prompt_auto_count() -> None:
    p = build_user_prompt("CTX", None, ["single"], None, [SourceKind.sample])
    assert "сколько их в приведённом образце" in p
    assert str(settings.max_questions) in p
