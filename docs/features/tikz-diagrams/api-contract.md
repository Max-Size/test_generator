---
slug: tikz-diagrams
status: approved
---

# API contract: tikz-diagrams

## `POST /api/generate`

Запрос не меняется (`multipart/form-data`: `files`, `num_questions`,
`question_types`, `topics`, `source_kinds`).

Ответ — тот же SSE-поток из `generation-progress`. Изменения:

### 1. Новый stage прогресса `diagrams`

```ts
type DiagramsDetail = {
  processed: number;  // рисунков обработано (успешно или вопрос удалён)
  total: number;      // вопросов с tikz в сгенерированном тесте, ≥ 1
};

type ProgressEvent =
  | { type: "progress"; stage: "extract"; detail: ExtractDetail }
  | { type: "progress"; stage: "generate"; detail: string | null }
  | { type: "progress"; stage: "diagrams"; detail: DiagramsDetail };
```

Пример:

```
data: {"type": "progress", "stage": "generate", "detail": null}

data: {"type": "progress", "stage": "diagrams", "detail": {"processed": 0, "total": 2}}

data: {"type": "progress", "stage": "diagrams", "detail": {"processed": 1, "total": 2}}

data: {"type": "progress", "stage": "diagrams", "detail": {"processed": 2, "total": 2}}

data: {"type": "result", "data": { ...GenerateResponse... }}
```

Порядок: `extract*` → `generate*` → `diagrams*` → ровно одно `result` или
`error`. Событий `diagrams` нет вообще, если ни у одного вопроса нет `tikz`.
Если они есть — первое всегда `processed: 0`, последнее перед `result` —
`processed == total`.

### 2. Новая ошибка в потоке

| Условие | `status` | `detail` |
|---|---|---|
| после этапа `diagrams` не осталось ни одного вопроса | 502 | `Не удалось построить рисунки ни для одного вопроса` |

### 3. `GenerateResponse` / `Question` — форма не меняется, меняется содержимое `diagram`

```json
{
  "id": 3,
  "type": "single",
  "text": "Одно из чисел $\\frac{6}{11}$; … отмечено на числовой прямой точкой $A$. Какое это число?",
  "options": ["$\\frac{6}{11}$", "…"],
  "correct_indexes": [0],
  "correct_text": null,
  "explanation": "…",
  "diagram": {
    "image_base64": "data:image/svg+xml;base64,PHN2ZyB4bWxucz0i…",
    "alt_text": ""
  }
}
```

- `diagram` — `null` или объект `Diagram` (как сегодня).
- `diagram.image_base64` — **всегда** `data:image/svg+xml;base64,…`
  (PNG из PDF больше не бывает).
- `diagram.alt_text` — **всегда** `""` для сгенерированных рисунков.
- `id` вопросов — всегда подряд `1..n` (после удаления вопросов с
  непостроенными рисунками перенумеровываются).
- Число вопросов может быть меньше запрошенного/определённого LLM (вопросы
  с непостроенными рисунками удаляются) — отдельного поля об этом нет.
- Во внешнем JSON **нет** полей `tikz` и `diagram_id`.

## Internal contract (backend)

### `backend/app/schemas.py`

```python
class Question(BaseModel):
    ...
    # исходник рисунка от LLM; наружу в API не отдаётся
    tikz: str | None = Field(default=None, exclude=True)
    # заполняется бэкендом после компиляции tikz
    diagram: Diagram | None = None
    # поле diagram_id — удалено
```

`QUIZ_JSON_SCHEMA` (`llm.py`) по-прежнему строится из модели и убирает
`diagram` (его LLM не заполняет); `tikz` в схеме **остаётся** (`string | null`).

### `backend/app/llm.py`

```python
class PageTranscription(BaseModel):
    markdown: str          # PageDiagram и diagrams — удалены

async def fix_tikz(question_text: str, tikz: str, error_log: str) -> str:
    """Один LLM-вызов: вернуть исправленное тело TikZ.
    response_format — json_schema {"tikz": string}.
    Ошибки сети/валидации — пробрасываются (вызывающий считает их неудачной попыткой)."""
```

### `backend/app/diagrams.py` (новый)

```python
class TikzError(Exception):
    def __init__(self, log: str): ...
    log: str   # выжимка ошибки; номера строк — относительно тела, не файла

async def render_tikz(body: str) -> bytes: ...   # SVG (utf-8) или TikzError
async def warmup() -> None: ...                  # вызывается в lifespan
```

### `backend/app/text_extract.py`

```python
async def extract_text(filename: str, data: bytes, emit: ProgressEmit) -> str
# раньше: -> tuple[str, dict[str, bytes]]
```

### `backend/app/main.py`

```python
class DiagramsDetail(TypedDict):
    processed: int
    total: int

ProgressEmit = Callable[[str, "ExtractDetail | DiagramsDetail | str | None"], None]
```

`emit("diagrams", DiagramsDetail)` — только с `DiagramsDetail`.

### `backend/app/config.py`

```python
tikz_bin: str = "tectonic"
tikz_timeout_s: float = 20
tikz_concurrency: int = 4
tikz_fix_attempts: int = 2      # исправлений; компиляций максимум fix_attempts + 1
tikz_max_chars: int = 8000
# vision_max_diagrams_per_page — удалено
```

## Frontend touchpoints

### `frontend/src/types.ts`

```ts
export type ProgressStage = "extract" | "generate" | "diagrams";

export interface DiagramsDetail {
  processed: number;
  total: number;
}

export type ProgressState =
  | { stage: "extract"; detail: ExtractDetail }
  | { stage: "generate"; detail: string | null }
  | { stage: "diagrams"; detail: DiagramsDetail };
```

`Diagram` не меняется (`image_base64: string; alt_text: string`).

### `frontend/src/api.ts`

`onProgress` принимает новый stage `"diagrams"` и его detail (сигнатура —
через `ProgressState`/`ProgressStage` из `types.ts`, без ручного перечисления
литералов).

### `frontend/src/components/GenerationProgress.tsx`

- Третий шаг «Рисуем схемы» (`stage: "diagrams"`), detail — `«{processed} из {total}»`.
- Шаг отображается в списке только после получения первого события
  `diagrams` (для тестов без рисунков список остаётся из двух шагов).
  Чтобы это знать, `App.tsx` / компонент запоминает, что `diagrams` уже был.

### `frontend/src/components/QuestionDiagram.tsx`

- `<figcaption>` рендерится только при непустом `alt_text`.
- `<img alt>` — `alt_text || "Рисунок к заданию"`.
- Обёртка `figure.paper.fig` остаётся (белая подложка под прозрачный SVG).
