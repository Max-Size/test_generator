import asyncio
import base64
import shutil

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app import diagrams, text_extract
from app.config import settings
from app.diagrams import TikzError, render_tikz, warmup
from app.llm import QUIZ_JSON_SCHEMA, VISION_SYSTEM_PROMPT, PageTranscription
from app.main import app
from app.schemas import Question, QuestionType, Quiz

from .conftest import parse_sse, sse_result

client = TestClient(app)

needs_tectonic = pytest.mark.skipif(
    shutil.which("tectonic") is None, reason="tectonic не установлен"
)


@pytest.fixture(scope="module")
def warm_tectonic():
    if shutil.which("tectonic") is not None:
        asyncio.run(warmup())


# --- render_tikz на реальном tectonic ---

NUMBER_LINE = r"""\begin{tikzpicture}
\draw[-{Stealth}] (0,0) -- (10.5,0);
\foreach \i in {0,...,11} \draw (\i*10/11,0.1) -- (\i*10/11,-0.1);
\node[below] at (0,-0.1) {$0$};
\node[below] at (10,-0.1) {$1$};
\fill (60/11,0) circle (2pt) node[above] {$A$};
\end{tikzpicture}"""

TRIANGLE = r"""\begin{tikzpicture}
\coordinate (A) at (0,0); \coordinate (B) at (4,0); \coordinate (C) at (1,3);
\draw (A) -- node[below] {$6$} (B) -- (C) -- cycle;
\pic[draw, "$30^\circ$", angle eccentricity=1.8] {angle = B--A--C};
\node[left] at (A) {$A$}; \node[right] at (B) {$B$}; \node[above] at (C) {$C$};
\end{tikzpicture}"""

PARABOLA = r"""\begin{tikzpicture}
\begin{axis}[axis lines=middle, xmin=-3, xmax=3, ymin=-1, ymax=9, width=8cm]
\addplot[domain=-3:3, samples=50] {x^2};
\node at (axis cs:2,4) [right] {$y=x^2$};
\end{axis}
\end{tikzpicture}"""

CIRCUIT = r"""\begin{circuitikz}
\draw (0,0) to[battery1, l=$\mathcal{E}$] (0,3) to[R, l=$R_1$] (4,3)
  to[lamp, l=Лампа] (4,0) -- (0,0);
\end{circuitikz}"""


@needs_tectonic
@pytest.mark.parametrize("body", [NUMBER_LINE, TRIANGLE, PARABOLA, CIRCUIT])
def test_render_valid_bodies_gives_svg(body, warm_tectonic) -> None:
    svg = asyncio.run(render_tikz(body))
    assert svg.startswith(b"<svg")


@needs_tectonic
def test_compile_error_reports_body_line(warm_tectonic) -> None:
    body = "\\begin{tikzpicture}\n\\draw (0,0) -- (1,0);\n\\drwa (0,0) -- (1,1);\n\\end{tikzpicture}"
    with pytest.raises(TikzError) as exc:
        asyncio.run(render_tikz(body))
    log = exc.value.log
    assert "строка 3:" in log
    assert f"строка {3 + diagrams._PREAMBLE_LINES}:" not in log
    assert "fig.tex:" not in log


# --- проверки до компиляции: компилятор не запускается ---


@pytest.fixture
def no_compiler(monkeypatch):
    async def boom(*a, **kw):
        raise AssertionError("компилятор не должен запускаться")

    monkeypatch.setattr(diagrams.asyncio, "create_subprocess_exec", boom)


@pytest.mark.parametrize(
    "inner, needle",
    [
        (r"\input{/etc/passwd}", "input"),
        (r"\immediate\write18{rm -rf /}", "immediate"),
        (r"\write18{ls}", "write"),
        (r"\usepackage{hyperref}", "usepackage"),
    ],
)
def test_forbidden_commands_rejected(no_compiler, inner, needle) -> None:
    body = f"\\begin{{tikzpicture}}\n{inner}\n\\draw (0,0) -- (1,1);\n\\end{{tikzpicture}}"
    with pytest.raises(TikzError) as exc:
        asyncio.run(render_tikz(body))
    assert needle in exc.value.log


def test_two_environments_rejected(no_compiler) -> None:
    one = "\\begin{tikzpicture}\\draw (0,0) -- (1,1);\\end{tikzpicture}"
    with pytest.raises(TikzError):
        asyncio.run(render_tikz(one + "\n" + one))


def test_no_environment_rejected(no_compiler) -> None:
    with pytest.raises(TikzError):
        asyncio.run(render_tikz("\\draw (0,0) -- (1,1);"))


def test_too_long_rejected(no_compiler, monkeypatch) -> None:
    monkeypatch.setattr(settings, "tikz_max_chars", 50)
    body = "\\begin{tikzpicture}\n" + "\\draw (0,0) -- (1,1);\n" * 5 + "\\end{tikzpicture}"
    with pytest.raises(TikzError) as exc:
        asyncio.run(render_tikz(body))
    assert "50" in exc.value.log


def test_timeout_kills_compiler(monkeypatch, tmp_path) -> None:
    fake_bin = tmp_path / "slow-tectonic"
    fake_bin.write_text("#!/bin/sh\nsleep 10\n")
    fake_bin.chmod(0o755)
    monkeypatch.setattr(settings, "tikz_bin", str(fake_bin))
    monkeypatch.setattr(settings, "tikz_timeout_s", 0.3)
    body = "\\begin{tikzpicture}\\draw (0,0) -- (1,1);\\end{tikzpicture}"
    with pytest.raises(TikzError) as exc:
        asyncio.run(render_tikz(body))
    assert exc.value.log == "превышено время компиляции"


# --- warmup / старт приложения ---


def test_missing_binary_fails_startup(monkeypatch) -> None:
    monkeypatch.setattr(settings, "tikz_bin", "no-such-tectonic-binary")
    with pytest.raises(RuntimeError, match="tectonic не найден"), TestClient(app):
        pass


def test_warmup_compile_error_is_logged_not_raised(monkeypatch, tmp_path) -> None:
    fake_bin = tmp_path / "bad-tectonic"
    fake_bin.write_text("#!/bin/sh\necho 'error: fig.tex:1: boom'\nexit 1\n")
    fake_bin.chmod(0o755)
    monkeypatch.setattr(settings, "tikz_bin", str(fake_bin))
    asyncio.run(warmup())  # не бросает


# --- схема, промпты, извлечение ---


def test_llm_schema_has_tikz_and_hides_diagram() -> None:
    props = QUIZ_JSON_SCHEMA["$defs"]["Question"]["properties"]
    assert "tikz" in props and "diagram" not in props
    assert "tikz" in QUIZ_JSON_SCHEMA["$defs"]["Question"]["required"]


def test_vision_prompt_asks_detailed_description_without_id() -> None:
    assert "[Рисунок: <подробное описание>]" in VISION_SYSTEM_PROMPT
    assert "id=" not in VISION_SYSTEM_PROMPT and "diagrams" not in VISION_SYSTEM_PROMPT


def _pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Text")
    page.draw_line((72, 100), (300, 100))
    return doc.tobytes()


def test_extract_returns_text_and_caches_versioned(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "ingest_cache_dir", str(tmp_path))
    calls = []

    async def fake(png, n):
        calls.append(n)
        return PageTranscription(markdown="A [Рисунок: числовая прямая от 0 до 1]")

    monkeypatch.setattr(text_extract, "transcribe_page", fake)
    data = _pdf()
    noop = lambda *a: None
    text = asyncio.run(text_extract.extract_text("a.pdf", data, noop))
    assert text == "A [Рисунок: числовая прямая от 0 до 1]"
    text2 = asyncio.run(text_extract.extract_text("a.pdf", data, noop))
    assert text2 == text and calls == [1]
    assert [p.name.endswith(".v2.md") for p in tmp_path.iterdir()] == [True]


def test_pre_feature_cache_is_ignored(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "ingest_cache_dir", str(tmp_path))
    data = b"fresh text"
    (tmp_path / f"{text_extract._digest(data)}.md").write_text(
        "[Рисунок: old]", encoding="utf-8"
    )
    text = asyncio.run(text_extract.extract_text("a.txt", data, lambda *a: None))
    assert text == "fresh text"


# --- оркестрация этапа diagrams (render_tikz / fix_tikz замоканы) ---

SVG = b"<svg xmlns='http://www.w3.org/2000/svg'/>"


def _q(qid: int, tikz: str | None) -> Question:
    return Question(id=qid, type=QuestionType.short, text=f"q{qid}", correct_text="a", tikz=tikz)


def _run(monkeypatch, questions, render, fix=None):
    async def gen(context, n, types, topics, kinds, emit):
        return Quiz(title="t", questions=questions)

    async def no_fix(text, tikz, err):
        raise AssertionError("fix_tikz не ожидался")

    monkeypatch.setattr("app.main.generate_quiz", gen)
    monkeypatch.setattr("app.main.render_tikz", render)
    monkeypatch.setattr("app.main.fix_tikz", fix or no_fix)
    r = client.post(
        "/api/generate",
        files={"files": ("a.txt", b"material", "text/plain")},
        data={"num_questions": len(questions)},
    )
    assert r.status_code == 200
    return parse_sse(r), r


def _diagrams_events(events):
    return [e["detail"] for e in events if e.get("stage") == "diagrams"]


def test_render_first_try(monkeypatch) -> None:
    calls = []

    async def render(body):
        calls.append(body)
        return SVG

    events, r = _run(monkeypatch, [_q(1, "T1")], render)
    q = sse_result(r)["quiz"]["questions"][0]
    assert q["diagram"]["image_base64"] == (
        "data:image/svg+xml;base64," + base64.b64encode(SVG).decode()
    )
    assert q["diagram"]["alt_text"] == ""
    assert "tikz" not in q
    assert calls == ["T1"]
    assert _diagrams_events(events) == [
        {"processed": 0, "total": 1},
        {"processed": 1, "total": 1},
    ]
    stages = [e["stage"] for e in events if e["type"] == "progress"]
    assert stages.index("diagrams") > max(i for i, s in enumerate(stages) if s != "diagrams")
    assert events[-1]["type"] == "result"


def test_render_after_one_fix(monkeypatch) -> None:
    fixes = []

    async def render(body):
        if body == "bad":
            raise TikzError("строка 1: Undefined control sequence")
        return SVG

    async def fix(text, tikz, err):
        fixes.append((text, tikz, err))
        return "good"

    _, r = _run(monkeypatch, [_q(1, "bad")], render, fix)
    q = sse_result(r)["quiz"]["questions"][0]
    assert q["diagram"]["image_base64"].startswith("data:image/svg+xml;base64,")
    assert fixes == [("q1", "bad", "строка 1: Undefined control sequence")]


def test_failed_question_removed_and_renumbered(monkeypatch) -> None:
    renders = []
    fixes = []

    async def render(body):
        renders.append(body)
        if body.startswith("bad"):
            raise TikzError("err")
        return SVG

    async def fix(text, tikz, err):
        fixes.append(tikz)
        return tikz + "!"

    questions = [_q(1, None), _q(2, "bad"), _q(3, "ok")]
    events, r = _run(monkeypatch, questions, render, fix)
    qs = sse_result(r)["quiz"]["questions"]
    assert [q["id"] for q in qs] == [1, 2]
    assert [q["text"] for q in qs] == ["q1", "q3"]
    assert qs[0]["diagram"] is None  # вопрос без tikz не тронут
    assert qs[1]["diagram"] is not None
    assert renders.count("ok") == 1
    assert len([b for b in renders if b.startswith("bad")]) == settings.tikz_fix_attempts + 1
    assert len(fixes) == settings.tikz_fix_attempts
    ev = _diagrams_events(events)
    assert ev[0] == {"processed": 0, "total": 2} and ev[-1] == {"processed": 2, "total": 2}
    assert [e["processed"] for e in ev] == [0, 1, 2]


def test_fix_llm_error_counts_as_attempt(monkeypatch) -> None:
    renders = []
    fixes = []

    async def render(body):
        renders.append(body)
        raise TikzError("err")

    async def fix(text, tikz, err):
        fixes.append(tikz)
        raise ValueError("invalid JSON")

    questions = [_q(1, "bad"), _q(2, None)]
    _, r = _run(monkeypatch, questions, render, fix)
    qs = sse_result(r)["quiz"]["questions"]
    assert [(q["id"], q["text"]) for q in qs] == [(1, "q2")]
    assert renders == ["bad"]
    assert len(fixes) == settings.tikz_fix_attempts


def test_all_removed_gives_error(monkeypatch) -> None:
    async def render(body):
        raise TikzError("err")

    async def fix(text, tikz, err):
        return tikz

    events, _ = _run(monkeypatch, [_q(1, "a"), _q(2, "b")], render, fix)
    assert events[-1] == {
        "type": "error",
        "status": 502,
        "detail": "Не удалось построить рисунки ни для одного вопроса",
    }
    assert not any(e["type"] == "result" for e in events)
    assert _diagrams_events(events)[-1] == {"processed": 2, "total": 2}


def test_no_tikz_no_diagrams_stage(monkeypatch) -> None:
    async def render(body):
        raise AssertionError("render_tikz не ожидался")

    events, r = _run(monkeypatch, [_q(1, None), _q(2, None)], render)
    assert _diagrams_events(events) == []
    qs = sse_result(r)["quiz"]["questions"]
    assert [q["diagram"] for q in qs] == [None, None]
