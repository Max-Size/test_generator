import asyncio
import json

import pytest

from app import llm
from app.llm import _fix_latex_escapes
from app.schemas import SourceKind


def _parse(raw_json_string: str) -> str:
    return json.loads(_fix_latex_escapes(raw_json_string))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # валидные JSON-escape, которые молча портили LaTeX
        (r'"$\frac{1}{2}$"', r"$\frac{1}{2}$"),
        (r'"$\beta$"', r"$\beta$"),
        (r'"$a \times b$, $\theta$, $\tan x$, $\text{см}$"', r"$a \times b$, $\theta$, $\tan x$, $\text{см}$"),
        (r'"$\rho$, $\right)$"', r"$\rho$, $\right)$"),
        (r'"$a \neq b$, $\nu$, $\not\in$, $\nabla$"', r"$a \neq b$, $\nu$, $\not\in$, $\nabla$"),
        # невалидные JSON-escape, которые роняли парсинг
        (r'"$\sqrt{2} \cdot \pi \approx \alpha$"', r"$\sqrt{2} \cdot \pi \approx \alpha$"),
        (r'"$\underline{x}$"', r"$\underline{x}$"),
        (r'"$\left( x \right)$ и $\{1\}$"', r"$\left( x \right)$ и $\{1\}$"),
        # TikZ
        (r'"\begin{tikzpicture}\fill (0,0); \node at (1,0) {$A$};\end{tikzpicture}"',
         r"\begin{tikzpicture}\fill (0,0); \node at (1,0) {$A$};\end{tikzpicture}"),
    ],
)
def test_lone_backslashes_are_repaired(raw: str, expected: str) -> None:
    assert _parse(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        r'"$\\frac{1}{2}$ и $\\sqrt{3}$"',  # корректно экранированный LaTeX
        r'"строка 1\nстрока 2\tтаб \"кавычки\" \/ \\"',  # обычные JSON-escape
        r'"буква"',  # \uXXXX
        r'"Ответ:\nВерно"',  # перенос строки перед словом — не команда
        r'"line\nnever mind"',  # \n + слово, похожее на \ne, но длиннее
    ],
)
def test_valid_json_is_unchanged(raw: str) -> None:
    assert _fix_latex_escapes(raw) == raw


def test_generate_quiz_repairs_single_backslash_latex(monkeypatch) -> None:
    raw = (
        '{"title": "Т", "questions": [{"id": 1, "type": "single", '
        r'"text": "Какое из чисел $\frac{6}{11}$ больше $\sqrt{0.25}$?", '
        r'"options": ["$\frac{6}{11}$", "$\frac{1}{2}$"], "correct_indexes": [0], '
        r'"correct_text": null, "explanation": "$\frac{6}{11} \approx 0.545$", "tikz": null}]}'
    )
    calls = []

    async def fake_call_llm(messages, attempt, response_format=None, model=None):
        calls.append(attempt)
        return raw

    monkeypatch.setattr(llm, "_call_llm", fake_call_llm)
    quiz = asyncio.run(
        llm.generate_quiz("ctx", 1, ["single"], None, [SourceKind.material], lambda *a: None)
    )

    q = quiz.questions[0]
    assert q.text == r"Какое из чисел $\frac{6}{11}$ больше $\sqrt{0.25}$?"
    assert q.options == [r"$\frac{6}{11}$", r"$\frac{1}{2}$"]
    assert q.explanation == r"$\frac{6}{11} \approx 0.545$"
    assert calls == [1]  # без ретрая
