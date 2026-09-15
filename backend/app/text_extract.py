"""Извлечение содержимого из загруженных файлов в Markdown: pdf / docx / txt / md.

PDF обрабатывается послойно:
1. `pymupdf4llm` вытаскивает текст, заголовки и таблицы в Markdown — быстро и без LLM;
2. «тяжёлые» страницы (картинки, графики, формулы, почти нет текстового слоя)
   дорисовываются vision-моделью: страница рендерится в PNG и распознаётся в Markdown
   с формулами в LaTeX и текстовым описанием иллюстраций. Распознавание идёт параллельно
   (по одной странице на запрос, не более `vision_concurrency` одновременно).

Результат извлечения кэшируется на диске по SHA-256 файла — повторная обработка того же
документа не тратит ни время, ни токены.
"""
import asyncio
import hashlib
import io
from pathlib import Path

import pymupdf
import pymupdf4llm
from docx import Document
from fastapi import HTTPException

from .config import settings
from .llm import transcribe_page
from .obs import log
from .text_clean import clean_markdown, page_has_symbol_font, page_text_from_dict


def _cache_file(data: bytes) -> Path:
    digest = hashlib.sha256(data).hexdigest()
    return Path(settings.ingest_cache_dir) / f"{digest}.md"


def _page_needs_vision(page: "pymupdf.Page", text: str) -> bool:
    if not settings.vision_enabled:
        return False
    low_text = len(text.strip()) < settings.vision_min_text_chars
    has_images = bool(page.get_images())
    return low_text or has_images


async def _from_pdf(data: bytes) -> str:
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        chunks = pymupdf4llm.to_markdown(doc, page_chunks=True, show_progress=False)
        log.info("pdf: %d страниц", len(chunks))

        # Текстовый слой: страницы с математикой (шрифт Symbol) собираем сами —
        # с ремапом Symbol-глифов и восстановлением индексов; остальные берём из
        # pymupdf4llm (его таблицы/заголовки лучше). Всё чистим от разметочного шума.
        pages_md: list[str] = []
        symbol_pages = 0
        for i, chunk in enumerate(chunks):
            if page_has_symbol_font(doc[i]):
                symbol_pages += 1
                pages_md.append(clean_markdown(page_text_from_dict(doc[i])))
            else:
                pages_md.append(clean_markdown(chunk.get("text") or ""))
        if symbol_pages:
            log.info("pdf: %d страниц с математикой нормализованы без LLM", symbol_pages)

        # какие страницы отдаём в vision-модель (с учётом бюджета на файл)
        heavy: list[int] = []
        for i, md_text in enumerate(pages_md):
            if len(heavy) >= settings.vision_max_pages:
                break
            if _page_needs_vision(doc[i], md_text):
                heavy.append(i)

        if heavy:
            sem = asyncio.Semaphore(settings.vision_concurrency)

            async def _recognize(idx: int) -> tuple[int, str]:
                png = doc[idx].get_pixmap(dpi=settings.vision_dpi).tobytes("png")
                async with sem:
                    return idx, await transcribe_page(png, idx + 1)

            log.info("pdf: %d страниц в vision (параллельно по %d)",
                     len(heavy), settings.vision_concurrency)
            for idx, recognized in await asyncio.gather(*(_recognize(i) for i in heavy)):
                if recognized.strip():
                    log.info("pdf стр. %d: распознана vision-моделью (%d симв.)",
                             idx + 1, len(recognized))
                    pages_md[idx] = recognized.strip()

        return "\n\n".join(p for p in pages_md if p)
    finally:
        doc.close()


def _from_docx(data: bytes) -> str:
    doc = Document(io.BytesIO(data))
    log.info("docx: %d абзацев", len(doc.paragraphs))
    return "\n".join(p.text for p in doc.paragraphs)


def _from_text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


async def extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()

    cache = _cache_file(data)
    if cache.exists():
        log.info("извлечение %s взято из кэша (%s)", filename, cache.name)
        return cache.read_text(encoding="utf-8")

    try:
        if name.endswith(".pdf"):
            text = await _from_pdf(data)
        elif name.endswith(".docx"):
            text = _from_docx(data)
        elif name.endswith((".txt", ".md")):
            text = _from_text(data)
        else:
            raise HTTPException(415, f"неподдерживаемый формат: {filename} (нужен pdf/docx/txt/md)")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(422, f"не удалось прочитать {filename}: {e}")

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(text, encoding="utf-8")
    return text


def combine(parts: list[tuple[str, str]], limit: int) -> tuple[str, bool]:
    """Склеить тексты файлов, обрезать до limit символов. Возвращает (текст, truncated)."""
    chunks = [f"### {name}\n{text.strip()}" for name, text in parts if text.strip()]
    full = "\n\n".join(chunks)
    if len(full) <= limit:
        return full, False
    return full[:limit], True
