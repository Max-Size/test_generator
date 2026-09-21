import pymupdf

from app.llm import SYSTEM_PROMPT
from app.text_clean import page_text_from_dict


def _page(bars):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((100, 90), "7", fontsize=11)
    page.insert_text((100, 115), "12", fontsize=11)
    page.insert_text((60, 105), "x =", fontsize=11)
    for y in bars:
        page.draw_line((95, y), (125, y))
    return page


def test_prompt_requires_latex():
    assert "\\frac" in SYSTEM_PROMPT and "$$" in SYSTEM_PROMPT


def test_fraction_reconstructed():
    text = page_text_from_dict(_page([100]))
    assert "$\\frac{7}{12}$" in text
    assert "x =" in text


def test_ambiguous_bars_left_flat():
    text = page_text_from_dict(_page([100, 103]))
    assert "frac" not in text
    assert "7" in text and "12" in text
