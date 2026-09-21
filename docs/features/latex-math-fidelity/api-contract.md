---
slug: latex-math-fidelity
status: approved
---

# API contract: latex-math-fidelity

## `POST /api/generate`

Контракт запроса и ответа не меняется — ни `schemas.py`, ни `types.ts`. Все
изменения внутренние (маршрутизация страниц PDF в vision, удаление локальной
эвристики дробей). Наблюдаемый эффект: строковые поля `Question.text`/`options`/
`correct_text`/`explanation` для математических PDF содержат корректный LaTeX
(`$...$`/`$$...$$`), который фронтенд уже рендерит.

Побочный эффект: на PDF с математикой, картинками или векторной графикой растёт
число vision-вызовов (по одному на страницу, до `vision_max_pages`), а значит
время и стоимость извлечения. Ошибки vision по-прежнему не роняют запрос —
страница откатывается на обычный локальный текст.

## `backend/app/text_extract.py`

Сигнатура `_page_needs_vision(page, text) -> bool` не меняется; страница
считается "чисто текстовой" (False), только если нет ничего из перечисленного:

```python
def _page_needs_vision(page: "pymupdf.Page", text: str) -> bool:
    if not settings.vision_enabled:
        return False
    return (
        len(text.strip()) < settings.vision_min_text_chars
        or bool(page.get_images())
        or page_has_symbol_font(page)
        or bool(page.get_drawings())
    )
```

`_from_pdf` менять не обязательно: локальный текст Symbol-страниц
(`clean_markdown(page_text_from_dict(page))`) и остальных страниц
(`pymupdf4llm`) собирается до выбора страниц для vision и служит fallback'ом;
`pages_md[idx] = recognized.strip()` заменяет его только при непустом ответе.
Новые настройки в `config.py` не добавляются.

## `backend/app/text_clean.py` и `backend/tests/test_text_clean.py`

Удалить код PR #5: `_find_fractions` и всё, что она добавила в
`page_text_from_dict` (`_anchor`, `_fracs`, потребление span'ов, вставка
`$\frac{}{}$`), и соответствующие тесты. Публичные сигнатуры
`page_text_from_dict(page)`, `clean_markdown`, `remap_symbol_chars`,
`page_has_symbol_font` не меняются; поведение `page_text_from_dict` — как на
`main`. Ориентир: `git diff main...feature/latex-math-fidelity --
backend/app/text_clean.py backend/tests/test_text_clean.py` должен стать пустым.

## `backend/app/llm.py`

Без изменений относительно PR #5: `SYSTEM_PROMPT` сохраняет LaTeX-инструкцию.
`VISION_SYSTEM_PROMPT` не меняется (если проверка на демо-PDF не покажет
необходимость — см. spec.md, п. 4).

## Frontend touchpoints

Изменений нет. `frontend/src/components/RichText.tsx` уже поддерживает
`$...$`/`$$...$$`/`\(...\)`/`\[...\]`. `frontend-dev` для этого слага делать
нечего.
