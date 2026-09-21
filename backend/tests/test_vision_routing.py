import asyncio

import pymupdf
import pytest

from app import text_extract
from app.text_extract import _page_needs_vision

LONG = "x" * 500


class FakePage:
    def __init__(self, images=(), drawings=(), symbol=False):
        self._images, self._drawings, self.symbol = images, drawings, symbol

    def get_images(self):
        return list(self._images)

    def get_drawings(self):
        return list(self._drawings)


@pytest.fixture(autouse=True)
def _vision_on(monkeypatch):
    monkeypatch.setattr(text_extract.settings, "vision_enabled", True)
    monkeypatch.setattr(text_extract.settings, "vision_min_text_chars", 200)
    monkeypatch.setattr(text_extract, "page_has_symbol_font", lambda p: getattr(p, "symbol", False))


def test_pure_text_page_stays_local() -> None:
    assert _page_needs_vision(FakePage(), LONG) is False


def test_image_page_goes_to_vision() -> None:
    assert _page_needs_vision(FakePage(images=[1]), LONG) is True


def test_symbol_font_page_goes_to_vision() -> None:
    assert _page_needs_vision(FakePage(symbol=True), LONG) is True


def test_drawings_page_goes_to_vision() -> None:
    assert _page_needs_vision(FakePage(drawings=[{}]), LONG) is True


def test_short_text_goes_to_vision() -> None:
    assert _page_needs_vision(FakePage(), "short") is True


def test_vision_disabled(monkeypatch) -> None:
    monkeypatch.setattr(text_extract.settings, "vision_enabled", False)
    assert _page_needs_vision(FakePage(images=[1], drawings=[{}], symbol=True), "") is False


def test_vision_failure_falls_back_to_local_text(monkeypatch) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Local fallback text")
    page.draw_line((72, 100), (300, 100))
    data = doc.tobytes()

    async def fake_transcribe(png, n):
        return ""

    monkeypatch.setattr(text_extract, "transcribe_page", fake_transcribe)
    out = asyncio.run(text_extract._from_pdf(data))
    assert "Local fallback text" in out


def test_system_prompt_requires_latex() -> None:
    from app.llm import SYSTEM_PROMPT

    assert "\\frac" in SYSTEM_PROMPT
    assert "$$" in SYSTEM_PROMPT
