---
slug: auto-question-count
status: approved
---

# API contract: auto-question-count

Зависит от `explicit-source-kinds` (поле `source_kinds`, удаление
`analyze_sources`/`SourceAnalysis`). Реализовывать после неё.

## `POST /api/generate`

Request:
```
files: list[UploadFile]              # без изменений
num_questions: int | None = None     # было обязательное Form(...); теперь Form(None)
question_types: str = "single,multiple,true_false"
topics: str | None = None
source_kinds: str = "material"       # из explicit-source-kinds
```

Логика в `main.py`:
```python
DEFAULT_NUM_QUESTIONS = 10

if num_questions is not None and not 1 <= num_questions <= settings.max_questions:
    raise HTTPException(422, f"num_questions должен быть 1..{settings.max_questions}")
# валидация остаётся на входе, как сегодня

auto_count = num_questions is None and SourceKind.sample in kinds
n = num_questions if num_questions is not None else (None if auto_count else DEFAULT_NUM_QUESTIONS)

quiz = await generate_quiz(context, n, types, topics, kinds)
if len(quiz.questions) > settings.max_questions:
    log.warning("модель вернула %d вопросов, обрезаем до %d", len(quiz.questions), settings.max_questions)
    quiz.questions = quiz.questions[: settings.max_questions]
```

Сигнатуры в `llm.py` (`num_questions` становится `int | None`; `None` = "по
образцу"):
```python
def build_user_prompt(context, num_questions: int | None, types, topics, source_kinds) -> str: ...
async def generate_quiz(context, num_questions: int | None, types, topics, source_kinds) -> Quiz: ...
```
При `num_questions is None` (возможно только вместе с `sample`) вместо
`"{num_questions} заданий"` в ветке `spec_like` подставляется: `"столько заданий,
сколько их в приведённом образце варианта (не более {settings.max_questions})"`.
`num_questions` — единственное место, где `settings.max_questions` попадает в
промпт.

Response `200`: схема `GenerateResponse` не меняется. Число вопросов —
`len(quiz.questions)`.

Errors:
- `422 num_questions должен быть 1..{max_questions}` — только если передан явно и
  вне диапазона (как сегодня).

## Frontend touchpoints

- `frontend/src/api.ts`: `numQuestions: number | null`; `num_questions` добавляется
  в `FormData` только если не `null`.
- `frontend/src/components/UploadForm.tsx`: состояние `autoCount` (дефолт `true`).
  Переключатель "Определить количество по образцу" отображается только когда в
  `sourceKinds` есть `"sample"`; при `autoCount && sourceKinds.includes("sample")`
  слайдер скрыт, `onSubmit` передаёт `numQuestions: null`; иначе — значение слайдера.
- `frontend/src/types.ts`: без изменений.
- Тесты: `backend/tests/test_generate.py` (кейсы без `num_questions`: с `sample` и
  без; обрезка сверх `max_questions`), `frontend/src/api.test.ts` (`numQuestions: null`
  не добавляет ключ в FormData).
