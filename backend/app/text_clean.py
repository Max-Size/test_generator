"""Алгоритмическая нормализация текста PDF — без LLM.

Главная проблема школьных/экзаменационных PDF: математика набрана шрифтом Symbol,
глифы которого лежат в Private Use Area (U+F020…U+F0FF). Обычный экстрактор их
выбрасывает, и `4 · x − 3 = 0,8` превращается в `4   x   3   0,8`.

Здесь:
* `SYMBOL_MAP` — фиксированная таблица кодировки Adobe Symbol → Unicode;
* `page_text_from_dict` — сборка текста страницы из `page.get_text("dict")` с
  ремапом Symbol-глифов и восстановлением верхних/нижних индексов (`x^2`, `a_n`);
* `clean_markdown` — чистка разметочного мусора `pymupdf4llm` (`<br>`, `<sup>`, `_i_`).
"""
import re

import pymupdf

# Adobe Symbol encoding: код глифа (0x20–0xFF) → символ Unicode.
# Покрывает операторы, отношения, стрелки, теоретико-множественные знаки и
# греческий алфавит (Symbol отображает латинскую букву в созвучную греческую).
SYMBOL_MAP: dict[int, str] = {
    0x22: "∀", 0x24: "∃", 0x27: "∋", 0x2A: "∗", 0x2B: "+", 0x2D: "−",
    0x3C: "<", 0x3D: "=", 0x3E: ">", 0x40: "≅", 0x5C: "∴",
    # греческие заглавные
    0x41: "Α", 0x42: "Β", 0x43: "Χ", 0x44: "Δ", 0x45: "Ε", 0x46: "Φ", 0x47: "Γ",
    0x48: "Η", 0x49: "Ι", 0x4A: "ϑ", 0x4B: "Κ", 0x4C: "Λ", 0x4D: "Μ", 0x4E: "Ν",
    0x4F: "Ο", 0x50: "Π", 0x51: "Θ", 0x52: "Ρ", 0x53: "Σ", 0x54: "Τ", 0x55: "Υ",
    0x57: "Ω", 0x58: "Ξ", 0x59: "Ψ", 0x5A: "Ζ",
    # греческие строчные
    0x61: "α", 0x62: "β", 0x63: "χ", 0x64: "δ", 0x65: "ε", 0x66: "φ", 0x67: "γ",
    0x68: "η", 0x69: "ι", 0x6A: "ϕ", 0x6B: "κ", 0x6C: "λ", 0x6D: "μ", 0x6E: "ν",
    0x6F: "ο", 0x70: "π", 0x71: "θ", 0x72: "ρ", 0x73: "σ", 0x74: "τ", 0x75: "υ",
    0x76: "ϖ", 0x77: "ω", 0x78: "ξ", 0x79: "ψ", 0x7A: "ζ", 0x7E: "∼",
    # отношения, операторы, единицы
    0xA2: "′", 0xA3: "≤", 0xA5: "∞", 0xAB: "↔", 0xAC: "←", 0xAD: "↑", 0xAE: "→",
    0xAF: "↓", 0xB0: "°", 0xB1: "±", 0xB2: "″", 0xB3: "≥", 0xB4: "×", 0xB5: "∝",
    0xB6: "∂", 0xB7: "•", 0xB8: "÷", 0xB9: "≠", 0xBA: "≡", 0xBB: "≈", 0xBC: "…",
    # теоретико-множественные и логические
    0xC6: "∅", 0xC7: "∩", 0xC8: "∪", 0xC9: "⊃", 0xCA: "⊇", 0xCC: "⊂", 0xCD: "⊆",
    0xCE: "∈", 0xCF: "∉", 0xD1: "∇", 0xD6: "√", 0xD7: "⋅", 0xD8: "¬", 0xD9: "∧",
    0xDA: "∨", 0xDE: "⇒", 0xDF: "⇔",
    0xE5: "∑", 0xF2: "∫",
}

_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_SUP = re.compile(r"<sup>(.+?)</sup>", re.DOTALL)
_SUB = re.compile(r"<sub>(.+?)</sub>", re.DOTALL)
_TAG = re.compile(r"</?(?:u|b|i|strong|em)>")
_BR = re.compile(r"<br\s*/?>")
# _x_ / _AB_ — курсивные обозначения переменных от pymupdf4llm; подчёркивания убираем
_ITALIC_VAR = re.compile(r"(?<![\w(])_([A-Za-zА-Яа-я0-9][^_\n]{0,24}?)_(?![\w)])")
_MULTISPACE = re.compile(r"[ \t]{2,}")
_MULTINL = re.compile(r"\n{3,}")


def _wrap(sym: str, core: str) -> str:
    return f"{sym}{core}" if len(core) == 1 else f"{sym}({core})"


def remap_symbol_chars(text: str, font: str) -> str:
    """Заменить Symbol-глифы (в т. ч. смещённые в PUA) на настоящие символы."""
    is_symbol = "Symbol" in font
    if not is_symbol and not any(0xF020 <= ord(c) <= 0xF0FF for c in text):
        return text
    out: list[str] = []
    for ch in text:
        cp = ord(ch)
        code = cp - 0xF000 if 0xF000 <= cp <= 0xF0FF else (cp if is_symbol and cp <= 0xFF else None)
        if code is None:
            out.append(ch)
        elif code in SYMBOL_MAP:
            out.append(SYMBOL_MAP[code])
        elif 0x20 <= code <= 0x7E:  # незнакомый глиф, но это печатный ASCII — берём как есть
            out.append(chr(code))
        # иначе — служебный глиф (куски скобок/радикалов), выбрасываем
    return "".join(out)


def page_has_symbol_font(page: "pymupdf.Page") -> bool:
    for font in page.get_fonts(full=False):
        if "Symbol" in (font[3] or "") or "Symbol" in (font[4] or ""):
            return True
    return False


def _span_text(spans: list[dict]) -> str:
    spans = sorted(spans, key=lambda s: s["bbox"][0])
    return " ".join(
        t for t in (remap_symbol_chars(s.get("text", ""), s.get("font", "")).strip() for s in spans) if t
    )


def _find_fractions(page: "pymupdf.Page", lines: list[dict]) -> list[tuple[dict, str, list[dict]]]:
    """Найти дроби по горизонтальным векторным чертам.

    Возвращает (линия-якорь, "$\\frac{..}{..}$", потреблённые span'ы). Неоднозначные
    случаи (близкие черты, нет строки-якоря, пустой числитель/знаменатель) пропускаются.
    """
    bars = []
    for d in page.get_drawings():
        r = d["rect"]
        if r.height <= 1.5 and r.width >= 5:
            bars.append(r)
    if not bars:
        return []
    all_spans = [s for ln in lines for s in ln.get("spans", []) if s.get("text", "").strip()]
    result: list[tuple[dict, str, list[dict]]] = []
    resolved: set[int] = set()
    # внутренние (узкие) черты обрабатываются первыми; готовая дробь становится синтетическим span'ом
    for bar in sorted(bars, key=lambda r: r.width):
        y = (bar.y0 + bar.y1) / 2
        others = [
            b for b in bars
            if b is not bar and id(b) not in resolved and b.x0 < bar.x1 and b.x1 > bar.x0
            and not (b.x0 <= bar.x0 and b.x1 >= bar.x1 and b.width > bar.width + 4)
        ]
        if any(abs((b.y0 + b.y1) / 2 - y) < 40 for b in others):
            continue  # несколько близких черт — неоднозначно
        in_x = [s for s in all_spans if bar.x0 - 1 <= (s["bbox"][0] + s["bbox"][2]) / 2 <= bar.x1 + 1]
        above = [s for s in in_x if s["bbox"][3] <= y + 1 and y - s["bbox"][3] < 1.5 * s["size"]]
        below = [s for s in in_x if s["bbox"][1] >= y - 1 and s["bbox"][1] - y < 1.5 * s["size"]]
        for side in (above, below):
            synth = [s for s in side if "_real" in s]
            if synth:  # знак между вложенными дробями лежит на уровне их черты
                lo = min(s["bbox"][1] for s in synth)
                hi = max(s["bbox"][3] for s in synth)
                for s in in_x:
                    if s not in side and lo <= (s["bbox"][1] + s["bbox"][3]) / 2 <= hi:
                        side.append(s)
        if not above or not below:
            continue
        plain_a = [s for s in above if "_real" not in s]
        plain_b = [s for s in below if "_real" not in s]
        # каждая сторона — одна текстовая строка (вложенные дроби не сравниваем)
        if len(plain_a) == len(above) and (
            max(s["bbox"][3] for s in above) - min(s["bbox"][3] for s in above) > 0.5 * above[0]["size"]
        ):
            continue
        if len(plain_b) == len(below) and (
            max(s["bbox"][1] for s in below) - min(s["bbox"][1] for s in below) > 0.5 * below[0]["size"]
        ):
            continue
        num, den = _span_text(above).replace("$", ""), _span_text(below).replace("$", "")  # $ вложенных дробей
        real = [r for s in above + below for r in s.get("_real", [s])]
        consumed = {id(s) for s in real}
        anchors = [
            ln for ln in lines
            if ln["bbox"][1] < y < ln["bbox"][3]
            and not any(id(s) in consumed for s in ln.get("spans", []))
        ]
        if not num or not den:
            continue
        latex = f"$\\frac{{{num}}}{{{den}}}$"
        # вложенные дроби поглощаются внешней
        for s in above + below:
            if "_res" in s:
                result.remove(s["_res"])
                if s["_anchor"] is not None:
                    s["_anchor"]["_fracs"].remove(s["_fx"])
        all_spans = [s for s in all_spans if s not in above and s not in below]
        anchor = anchors[0] if len(anchors) == 1 else None  # у вложенной дроби якоря может не быть
        entry = (anchor, latex, real)
        result.append(entry)
        fx = ((bar.x0 + bar.x1) / 2, latex)
        if anchor is not None:
            anchor.setdefault("_fracs", []).append(fx)
        resolved.add(id(bar))
        boxes = [s["bbox"] for s in above + below]
        all_spans.append({
            "bbox": (min(b[0] for b in boxes), min(b[1] for b in boxes),
                     max(b[2] for b in boxes), max(b[3] for b in boxes)),
            "size": max(s["size"] for s in above + below), "text": latex, "font": "",
            "_real": real, "_res": entry, "_anchor": anchors[0], "_fx": fx,
        })
    return [r for r in result if r[0] is not None]


def page_text_from_dict(page: "pymupdf.Page") -> str:
    """Собрать текст страницы с ремапом Symbol, восстановлением индексов и дробей."""
    data = page.get_text("dict")
    all_lines = [ln for b in data.get("blocks", []) if b.get("type") == 0 for ln in b.get("lines", [])]
    consumed_ids = {id(s) for _, _, sp in _find_fractions(page, all_lines) for s in sp}
    paragraphs: list[str] = []
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        lines: list[str] = []
        for line in block.get("lines", []):
            all_spans = line.get("spans", [])
            fracs = line.get("_fracs", [])
            spans = [s for s in all_spans if id(s) not in consumed_ids]
            if not spans and not fracs:
                continue
            if not spans:
                lines.append(" ".join(f for _, f in fracs))
                continue
            body = max(s["size"] for s in spans)
            baseline = max(s["bbox"][3] for s in spans if s["size"] >= 0.9 * body)
            parts: list[str] = []
            pending = sorted(fracs)
            for s in spans:
                while pending and pending[0][0] < (s["bbox"][0] + s["bbox"][2]) / 2:
                    parts.append(f" {pending.pop(0)[1]} ")
                raw = remap_symbol_chars(s.get("text", ""), s.get("font", ""))
                core = raw.strip()
                if not core:
                    parts.append(raw)
                    continue
                small = s["size"] < 0.8 * body
                sup = bool(s.get("flags", 0) & 1) or (small and s["bbox"][3] < baseline - 0.12 * body)
                sub = not sup and small and s["bbox"][1] > line["bbox"][1] + 0.18 * body
                if sup:
                    parts.append(_wrap("^", core) + (" " if raw.endswith(" ") else ""))
                elif sub:
                    parts.append(_wrap("_", core) + (" " if raw.endswith(" ") else ""))
                else:
                    parts.append(raw)
            parts.extend(f" {f} " for _, f in pending)
            lines.append("".join(parts))
        para = " ".join(x.strip() for x in lines if x.strip())
        if para:
            paragraphs.append(para)
    return _MULTISPACE.sub(" ", "\n\n".join(paragraphs))


def clean_markdown(md: str) -> str:
    """Убрать разметочный шум pymupdf4llm и нормализовать любые уцелевшие Symbol-глифы."""
    md = _HTML_COMMENT.sub("", md)
    md = _SUP.sub(lambda m: _wrap("^", m.group(1).strip()), md)
    md = _SUB.sub(lambda m: _wrap("_", m.group(1).strip()), md)
    md = _BR.sub("\n", md)
    md = _TAG.sub("", md)
    md = _ITALIC_VAR.sub(r"\1", md)
    md = remap_symbol_chars(md, "")
    md = _MULTISPACE.sub(" ", md)
    return _MULTINL.sub("\n\n", md).strip()
