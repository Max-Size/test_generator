"""Компиляция TikZ-рисунков, сгенерированных LLM, в SVG.

Тело рисунка вставляется в фиксированный шаблон standalone-документа, компилируется
внешним `tectonic` в PDF (во временной директории, без shell-escape и без сети),
первая страница PDF конвертируется в SVG через PyMuPDF с текстом в виде кривых —
SVG не зависит от шрифтов браузера. См. docs/features/tikz-diagrams/spec.md.
"""
import asyncio
import re
import shutil
import tempfile
from pathlib import Path

import pymupdf

from .config import settings
from .obs import log, stage

_PREAMBLE = (
    "\\documentclass[border=4pt]{standalone}\n"
    "\\usepackage{fontspec}\n"
    "\\setmainfont{cmunrm}[Extension=.otf, BoldFont=cmunbx, ItalicFont=cmunti, "
    "BoldItalicFont=cmunbi]\n"
    "\\usepackage{tikz}\n"
    "\\usepackage{pgfplots}\n"
    "\\usepackage[european]{circuitikz}\n"
    "\\usetikzlibrary{calc,angles,quotes,intersections,arrows.meta,patterns,"
    "decorations.markings}\n"
    "\\pgfplotsset{compat=1.18}\n"
    "\\begin{document}\n"
)
_POSTAMBLE = "\n\\end{document}\n"
# сколько строк файла идёт до первой строки тела — для пересчёта номеров строк в ошибках
_PREAMBLE_LINES = _PREAMBLE.count("\n")

_FORBIDDEN_RE = re.compile(
    r"\\(input|include|openin|openout|write|read|catcode|usepackage|documentclass"
    r"|immediate|newread|newwrite)(?![a-zA-Z])"
)
_BEGIN_RE = re.compile(r"\\begin\{(tikzpicture|circuitikz)\}")
_END_RE = re.compile(r"\\end\{(tikzpicture|circuitikz)\}")
# `error: fig.tex:<N>: …` и контекст TeX `l.<N> …` — номера строк собранного файла
_FILE_LINE_RE = re.compile(r"fig\.tex:(\d+):|^l\.(\d+)")
_MAX_LOG_LINES = 15

# эталонный рисунок для прогрева: задействует все пакеты/библиотеки шаблона и кириллицу
_WARMUP_BODY = r"""\begin{tikzpicture}
\draw[-{Stealth}] (0,0) -- (3,0) node[right] {$x$};
\coordinate (A) at (0,0); \coordinate (B) at (2,0); \coordinate (C) at (1,1.5);
\draw (A) -- (B) -- (C) -- cycle;
\pic[draw, "$\alpha$", angle radius=4mm] {angle = B--A--C};
\fill[pattern=north east lines] ($(A)!0.5!(B)$) circle (2pt);
\draw[postaction={decorate}, decoration={markings, mark=at position 0.5 with {\arrow{>}}}]
  (0,-1) -- (3,-1);
\node at (1.5,-1.5) {Рисунок \textbf{жирный} \textit{курсив}};
\begin{axis}[at={(4cm,0)}, width=4cm, xmin=-2, xmax=2]
\addplot[domain=-2:2] {x^2};
\end{axis}
\draw (0,-3) to[R, l=$R_1$] (2,-3) to[battery1] (2,-4) -- (0,-4) -- (0,-3);
\end{tikzpicture}"""


class TikzError(Exception):
    def __init__(self, log: str):
        super().__init__(log)
        self.log = log


def _check(body: str) -> None:
    if len(body) > settings.tikz_max_chars:
        raise TikzError(
            f"рисунок слишком длинный: {len(body)} символов (максимум {settings.tikz_max_chars})"
        )
    if m := _FORBIDDEN_RE.search(body):
        raise TikzError(f"запрещённая команда \\{m.group(1)}")
    begins, ends = len(_BEGIN_RE.findall(body)), len(_END_RE.findall(body))
    if begins != 1 or ends != 1:
        raise TikzError(
            "нужно ровно одно окружение tikzpicture или circuitikz, "
            f"найдено \\begin: {begins}, \\end: {ends}"
        )


def _error_log(output: str) -> str:
    """Строки ошибок из вывода tectonic; номера строк пересчитаны в строки тела."""
    lines = [
        _FILE_LINE_RE.sub(
            lambda m: f"строка {int(m.group(1) or m.group(2)) - _PREAMBLE_LINES}:",
            line.strip(),
        )
        for line in output.splitlines()
        if line.startswith(("error:", "!")) or re.match(r"l\.\d+", line)
    ]
    return "\n".join(lines[:_MAX_LOG_LINES]) or output.strip()[-2000:] or "ошибка компиляции"


async def _compile(body: str, *, only_cached: bool, timeout: float | None) -> bytes:
    with tempfile.TemporaryDirectory(prefix="tikz-") as tmp:
        tmp_dir = Path(tmp)
        (tmp_dir / "fig.tex").write_text(_PREAMBLE + body + _POSTAMBLE, encoding="utf-8")
        args = ["-X", "compile", "fig.tex", "--untrusted", "--outfmt", "pdf"]
        if only_cached:
            args.append("--only-cached")
        proc = await asyncio.create_subprocess_exec(
            settings.tikz_bin,
            *args,
            cwd=tmp_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise TikzError("превышено время компиляции")
        if proc.returncode != 0:
            raise TikzError(_error_log(out.decode("utf-8", errors="replace")))
        doc = pymupdf.open(tmp_dir / "fig.pdf")
        try:
            return doc[0].get_svg_image(text_as_path=True).encode("utf-8")
        finally:
            doc.close()


async def render_tikz(body: str) -> bytes:
    """Скомпилировать тело TikZ в SVG; при любой проблеме — TikzError с выжимкой для LLM."""
    _check(body)
    return await _compile(body, only_cached=True, timeout=settings.tikz_timeout_s)


async def warmup() -> None:
    """Проверить наличие tectonic и прогреть его кэш пакетов (при необходимости докачать)."""
    if shutil.which(settings.tikz_bin) is None:
        raise RuntimeError(
            f"tectonic не найден ({settings.tikz_bin!r}): установите его "
            "(macOS — brew install tectonic, Linux — официальный бинарник) "
            "или укажите путь в TIKZ_BIN"
        )
    try:
        with stage("tikz.warmup"):
            await _compile(_WARMUP_BODY, only_cached=False, timeout=None)
    except Exception as e:  # noqa: BLE001
        log.error("прогрев tectonic не удался, рисунки строиться не будут: %s", e)
