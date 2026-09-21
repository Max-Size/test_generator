---
slug: question-diagrams
status: approved
---

# API contract: question-diagrams

## `POST /api/generate`

Запрос не меняется. Меняется форма ответа: у каждого вопроса появляется
опциональное поле `diagram`.

### `backend/app/schemas.py`

```python
class Diagram(BaseModel):
    image_base64: str   # data URL, например "data:image/png;base64,iVBORw0KG..."
    alt_text: str


class Question(BaseModel):
    id: int
    type: QuestionType
    text: str
    options: list[str] = Field(default_factory=list)
    correct_indexes: list[int] = Field(default_factory=list)
    correct_text: str | None = None
    explanation: str | None = None
    diagram_id: str | None = None   # заполняется LLM при генерации; не публичное поле
    diagram: Diagram | None = None  # заполняется бэкендом после генерации
```

`diagram_id` — промежуточное поле, которое заполняет LLM при генерации теста,
ссылаясь на `diagram_id` из плейсхолдеров `[Рисунок: ... | diagram_id=...]` в
контексте. Бэкенд обязан **исключить** `diagram_id` из финального JSON-ответа
(например, `model_dump(exclude={"diagram_id"})` при сборке `GenerateResponse`
или отдельная response-модель без этого поля) — наружу уходит только `diagram`.

### Ответ `200` (пример вопроса с диаграммой)

```json
{
  "id": 3,
  "type": "single",
  "text": "Одно из чисел 5/9, 11/9, 13/9, 14/9 отмечено на числовой прямой точкой A. Какое это число?",
  "options": ["5/9", "11/9", "13/9", "14/9"],
  "correct_indexes": [1],
  "correct_text": null,
  "explanation": "Точка A находится между 0,5 и 0,6, значит A = 11/9.",
  "diagram": {
    "image_base64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
    "alt_text": "Числовая прямая от 0 до 1 с шагом 0,1, точка A отмечена между 0,5 и 0,6"
  }
}
```

Вопрос без диаграммы — `diagram: null` (как сегодня для всех вопросов).

### Ошибки

Без изменений — новых кодов ошибок не вводится. Некорректный/несуществующий
`diagram_id` от LLM не приводит к ошибке — просто `diagram: null` для этого
вопроса.

## Internal contract: vision transcription (`backend/app/llm.py`)

`transcribe_page` меняет формат ответа vision-модели с обычного текста на
JSON-схему (аналогично `analyze_sources`/`SourceAnalysis`):

```python
class PageDiagram(BaseModel):
    id: str
    alt_text: str
    bbox: list[float]  # [x0, y0, x1, y1], доли размеров страницы, 0..1

class PageTranscription(BaseModel):
    markdown: str
    diagrams: list[PageDiagram] = Field(default_factory=list)
```

`transcribe_page` возвращает `PageTranscription` вместо `str`. При сбое
(как и сегодня) — пустая транскрипция (`markdown=""`, `diagrams=[]`), вызывающий
код откатывается на текстовый слой без картинок.

`_from_pdf` (`text_extract.py`) после получения `PageTranscription`:
1. Подставляет `markdown` вместо текста страницы (как сегодня).
2. Для каждого `PageDiagram` вырезает прямоугольник `bbox` из уже
   отрендеренного пиксмапа страницы, кодирует в PNG.
3. Сохраняет PNG на диск: `{ingest_cache_dir}/{sha256}.diagrams/{diagram_id}.png`.
4. Возвращает из `extract_text` пару `(markdown_text, diagrams: dict[str, bytes])`
   — сигнатура `extract_text` меняется с `-> str` на `-> tuple[str, dict[str, bytes]]`.

`combine()` (`text_extract.py`) и `main.py` объединяют словари `diagrams` из всех
загруженных файлов в один `dict[str, bytes]` (ключи — `diagram_id`, уникальны в
рамках запроса, т.к. каждая страница генерирует свои id независимо от файла;
если два файла случайно дают одинаковый id — побеждает последний по порядку
загрузки, коллизия не считается ошибкой уровня API).

### Новая настройка (`config.py`)

- `vision_max_diagrams_per_page: int = 5` — максимум диаграмм, принимаемых с
  одной страницы (защита от чрезмерного размера ответа/кэша).

## Frontend touchpoints

- `frontend/src/types.ts`: добавить
  ```ts
  export interface Diagram {
    image_base64: string;
    alt_text: string;
  }
  ```
  и поле `diagram: Diagram | null` в `Question`.
- Новый компонент `frontend/src/components/QuestionDiagram.tsx`:
  ```tsx
  export default function QuestionDiagram({ diagram }: { diagram: Diagram | null }) {
    if (!diagram) return null;
    return <img src={diagram.image_base64} alt={diagram.alt_text} className="my-2 max-w-full rounded-md border border-slate-200" />;
  }
  ```
- `frontend/src/components/QuizView.tsx`: рендерить `<QuestionDiagram diagram={q.diagram} />`
  сразу после `<RichText>{q.text}</RichText>`, до блока вариантов ответа.
