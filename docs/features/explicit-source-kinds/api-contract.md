---
slug: explicit-source-kinds
status: approved
---

# API contract: explicit-source-kinds

## `POST /api/generate`

Request (multipart form):
```
files: list[UploadFile]
num_questions: int                                  # без изменений
question_types: str = "single,multiple,true_false"  # без изменений
topics: str | None = None                           # без изменений
source_kinds: str = "material"                      # НОВОЕ: список через запятую из material|specification|sample
# source_mode — УДАЛЁН
```

Логика в `main.py` (по образцу `question_types`):
```python
kinds = [SourceKind(k) for k in dict.fromkeys(s.strip() for s in source_kinds.split(","))
         if k in SourceKind._value2member_map_]
if not kinds:
    raise HTTPException(422, "не указаны корректные типы источника")
```
Блок `analyze_sources`/`source_mode` из `main.py` удаляется целиком; `kinds`
напрямую передаются в `generate_quiz`.

Сигнатуры (`backend/app/llm.py`):
```python
def build_user_prompt(
    context: str,
    num_questions: int,
    types: list[str],
    topics: str | None,
    source_kinds: list[SourceKind],
) -> str: ...

async def generate_quiz(
    context: str,
    num_questions: int,
    types: list[str],
    topics: str | None,
    source_kinds: list[SourceKind],
) -> Quiz: ...
```
`spec_like = SourceKind.specification in source_kinds or SourceKind.sample in
source_kinds`; `has_material = SourceKind.material in source_kinds`.

Удаляется: `analyze_sources`, `ANALYZE_SYSTEM_PROMPT`, `ANALYSIS_JSON_SCHEMA`,
`_format_analysis`, `SourceAnalysis`. `SourceKind` остаётся в `schemas.py`.

Response `200` (`GenerateResponse`): поле `analysis` удалено.
```python
class GenerateResponse(BaseModel):
    quiz: Quiz
    source_chars: int
    truncated: bool
    truncated_files: list[TruncatedFile] = Field(default_factory=list)
```

Errors:
- `422` `не указаны корректные типы источника` — `source_kinds` не содержит ни
  одного значения из `material|specification|sample`.
- Остальные ошибки без изменений.

## Frontend touchpoints

- `frontend/src/types.ts`: удалить `SourceAnalysis` и поле `analysis` из
  `GenerateResponse`; `SourceKind` оставить.
- `frontend/src/api.ts`: параметр `sourceMode: string` заменить на
  `sourceKinds: string[]`; `fd.append("source_kinds", params.sourceKinds.join(","))`;
  строку `source_mode` убрать.
- `frontend/src/components/UploadForm.tsx`: вместо `select` "Что за документ" —
  мультивыбор-чипы (по образцу "Типы вопросов": `SOURCE_KIND_OPTIONS` с
  `material` "Теория / конспект", `specification` "Спецификация / темы экзамена",
  `sample` "Образец варианта / примеры заданий"); состояние
  `sourceKinds: string[]` (дефолт `["material"]`); `FormValues.sourceMode` →
  `sourceKinds: string[]`; `canSubmit` требует `sourceKinds.length > 0`.
- `frontend/src/App.tsx`: удалить плашку по `result.analysis`.
- Тесты: `backend/tests/test_generate.py` (мок `generate_quiz` без `analysis`,
  в формах `source_mode` → `source_kinds`), `frontend/src/api.test.ts`
  (`sourceMode: "auto"` → `sourceKinds: ["material"]`).
