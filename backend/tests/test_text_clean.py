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


def test_nested_fraction():
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((60, 105), "x =", fontsize=11)
    page.insert_text((150, 90), "1", fontsize=11)
    page.draw_line((100, 100), (240, 100))
    page.insert_text((105, 120), "1", fontsize=11)
    page.draw_line((100, 125), (120, 125))
    page.insert_text((104, 141), "30", fontsize=11)
    page.insert_text((150, 128), "+", fontsize=11)
    page.insert_text((185, 120), "1", fontsize=11)
    page.draw_line((180, 125), (200, 125))
    page.insert_text((184, 141), "42", fontsize=11)
    text = page_text_from_dict(page)
    assert "$\\frac{1}{\\frac{1}{30} + \\frac{1}{42}}$" in text
