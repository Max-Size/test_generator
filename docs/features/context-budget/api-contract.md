---
slug: context-budget
status: approved
---

# API contract: context-budget

## `POST /api/generate`

Существующий эндпоинт, контракт запроса не меняется. Меняется поведение
валидации и форма ответа.

### Новая ошибка при загрузке

Если размер какого-либо файла превышает `settings.max_file_size_mb` (МБ):

Ответ `422`:
```json
{ "detail": "файл \"<имя файла>\" превышает максимальный размер 20 МБ" }
```
Проверяется сразу после чтения файла, до вызова `extract_text` — для файлов,
превышающих лимит, извлечение текста и vision-распознавание не выполняются.

### Изменённый ответ `200`

`backend/app/schemas.py::GenerateResponse`:

```python
class TruncatedFile(BaseModel):
    filename: str
    reason: Literal["partial", "dropped"]


class GenerateResponse(BaseModel):
    quiz: Quiz
    source_chars: int
    truncated: bool
    truncated_files: list[TruncatedFile] = Field(default_factory=list)
    analysis: SourceAnalysis | None = None
```

- `truncated` — `True`, если `truncated_files` непустой (сохраняется для
  обратной совместимости с текущим использованием на фронте).
- `truncated_files` — по одной записи на каждый файл, который либо обрезан
  (`"partial"` — попал в промпт частично, обрезка по границе абзаца), либо не
  попал в промпт вовсе (`"dropped"` — лимит контекста закончился раньше, чем
  дошла очередь до этого файла). Файлы, полностью поместившиеся в лимит, в
  списке не фигурируют. Порядок — как в списке загруженных файлов.

Пример (второй из трёх файлов частично обрезан, третий выпал целиком):
```json
{
  "quiz": { "title": "...", "questions": [] },
  "source_chars": 87345,
  "truncated": true,
  "truncated_files": [
    { "filename": "lecture2.pdf", "reason": "partial" },
    { "filename": "appendix.pdf", "reason": "dropped" }
  ],
  "analysis": null
}
```

### Новые настройки backend (`config.py`)

- `max_file_size_mb: int = 20` — максимальный размер одного загружаемого файла.
- `polza_model_context_tokens: int` — контекстное окно модели, заданной в
  `polza_model`, в токенах; без дефолта, обязательна в `.env`. При смене
  `polza_model` обновляется вручную вместе с ним.
- `max_context_chars` перестаёт быть настройкой из `.env` — вычисляется один раз
  при старте бэкенда из `polza_model_context_tokens` (см. `spec.md`, раздел
  "Solution", п. 2) и логируется в `_startup()` вместо текущего значения из
  `settings`.

## Frontend touchpoints

- `frontend/src/types.ts`: добавить тип `TruncatedFile = { filename: string;
  reason: "partial" | "dropped" }` и поле `truncated_files: TruncatedFile[]` в
  тип ответа `GenerateResponse`, зеркаля новую pydantic-модель.
- `frontend/src/App.tsx:49-53`: вместо общей фразы про "первую часть" — перечислить
  файлы из `result.truncated_files` с указанием `reason` (например: "lecture2.pdf
  — обрезан, не поместился целиком"; "appendix.pdf — не поместился, не включён в
  тест"). Условие рендера блока предупреждения — по-прежнему `result.truncated`.
- `frontend/src/api.test.ts`: существующий мок `responseBody` (`truncated: false`)
  остаётся валидным (поле `truncated_files` с дефолтом `[]` на бэкенде, опционально
  на фронте/в моках), новый тест-кейс добавляется для непустого `truncated_files`.
