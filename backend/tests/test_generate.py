from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.schemas import Question, QuestionType, Quiz

client = TestClient(app)


async def _fake_generate_quiz(context, num_questions, types, topics, analysis=None) -> Quiz:
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
        data={"num_questions": 1, "source_mode": "material"},
    )

    assert response.status_code == 422
    assert "big.txt" in response.json()["detail"]
    assert "1 МБ" in response.json()["detail"]


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
        data={"num_questions": 1, "source_mode": "material"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["truncated"] is True
    assert body["truncated_files"] == [{"filename": "f2.txt", "reason": "dropped"}]
    assert body["source_chars"] == len(chunk1)


def test_generate_no_truncation_when_everything_fits(monkeypatch) -> None:
    monkeypatch.setattr("app.main.generate_quiz", _fake_generate_quiz)

    response = client.post(
        "/api/generate",
        files={"files": ("f1.txt", b"Short material.", "text/plain")},
        data={"num_questions": 1, "source_mode": "material"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["truncated"] is False
    assert body["truncated_files"] == []
