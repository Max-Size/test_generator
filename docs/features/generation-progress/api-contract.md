---
slug: generation-progress
status: approved
---

# API contract: generation-progress

## `POST /api/generate`

Запрос (`multipart/form-data`) не меняется: `files`, `num_questions`,
`question_types`, `topics`, `source_kinds` — как сегодня.

### Ответ меняется с разового JSON на SSE-поток

**Синхронная валидация запроса** (не требует чтения байтов файлов) остаётся
обычной HTTP-ошибкой, отправленной **до** открытия потока:

| Условие | Код | Тело |
|---|---|---|
| `num_questions` вне `1..max_questions` | 422 | `{"detail": "num_questions должен быть 1..N"}` |
| файлов больше `max_files` | 422 | `{"detail": "максимум N файлов"}` |
| нет валидных `question_types` | 422 | `{"detail": "не указаны корректные типы вопросов"}` |
| нет валидных `source_kinds` | 422 | `{"detail": "не указаны корректные типы источника"}` |

Во всех остальных случаях ответ — `200 OK`, `Content-Type: text/event-stream`,
`Cache-Control: no-cache`, и тело — последовательность SSE-фреймов вида:

```
data: {"type": "progress", "stage": "extract", "detail": {"filename": "demo.pdf", "processed": 0, "total": 20}}

data: {"type": "progress", "stage": "extract", "detail": {"filename": "demo.pdf", "processed": 14, "total": 20}}

data: {"type": "progress", "stage": "extract", "detail": {"filename": "demo.pdf", "processed": 15, "total": 20}}

data: {"type": "progress", "stage": "generate", "detail": null}

data: {"type": "result", "data": { ...GenerateResponse как сегодня... }}

```

(каждый `data: <json>` заканчивается пустой строкой — стандартный формат SSE;
без `event:`/`id:` — не нужны).

### Типы событий

```ts
type ExtractDetail = {
  filename: string;
  processed: number;  // страниц файла уже обработано
  total: number;       // всего страниц в файле; 0 — не постраничный формат
                        // (docx/txt/md) или прогресс не считается
};

type ProgressEvent =
  | { type: "progress"; stage: "extract"; detail: ExtractDetail }
  | { type: "progress"; stage: "generate"; detail: string | null };

type ResultEvent = {
  type: "result";
  data: GenerateResponse;  // без изменений, см. schemas.py::GenerateResponse
};

type ErrorEvent = {
  type: "error";
  status: number;   // тот же HTTP-код, который вернулся бы синхронно сегодня (422/502)
  detail: string;    // тот же текст, что сегодня в HTTPException.detail
};
```

Поток всегда заканчивается ровно одним `result` ИЛИ ровно одним `error`
событием (после него бэкенд закрывает соединение). Между `progress`-событиями
порядок такой: ноль или больше событий со `stage: "extract"`, затем ноль или
больше со `stage: "generate"` — переходов назад с `generate` на `extract` не
бывает.

Для `stage: "extract"` — `detail` всегда структурированный объект
`ExtractDetail`, не строка: `filename` — имя текущего обрабатываемого файла,
`processed`/`total` — прогресс по страницам **этого** файла (для PDF — все
страницы документа, не только уходящие в vision; для docx/txt/md, где нет
понятия страницы, — `processed: 0, total: 0`). Формат числовой и
языконезависимый специально — чтобы фронтенд сам формировал текст на нужном
языке, а не парсил русские фразы.

Для `stage: "generate"` — `detail` остаётся строкой на русском либо `null`:
там нет числового прогресса, только качественная пометка (например, что идёт
повторная попытка после невалидного ответа модели).

### Ошибки в потоке (`error`-событие) — что переехало из HTTP-статусов

Раньше — HTTP-статус синхронного ответа, теперь — SSE-событие `error` с тем же
`status`/`detail`, но HTTP-статус самого ответа уже `200`:

| Условие | `status` | `detail` (как сегодня) |
|---|---|---|
| файл превышает `max_file_size_mb` | 422 | `файл "X" превышает максимальный размер N МБ` |
| неподдерживаемый формат файла | 415 | `неподдерживаемый формат: X (нужен pdf/docx/txt/md)` |
| файл не удалось прочитать | 422 | `не удалось прочитать X: ...` |
| из файлов не удалось извлечь текст | 422 | `из файлов не удалось извлечь текст` |
| Polza.ai HTTP-ошибка / недоступен | 502 | как сегодня (`_call_llm`) |
| LLM вернул невалидный JSON после ретрая | 502 | `LLM вернул невалидный тест после ретрая: ...` |
| `POLZA_API_KEY` не задан | 500 | `POLZA_API_KEY не задан` |

Любое необработанное исключение внутри фоновой задачи (не `HTTPException`) —
тоже `error`-событие, `status: 500`, `detail`: сообщение исключения (лучше не
приводить к бесконечному молчанию потока — фронтенд должен получить хоть
какую-то ошибку и снять спиннер).

## Internal contract (backend)

### `backend/app/main.py`

```python
from typing import Callable, TypedDict


class ExtractDetail(TypedDict):
    filename: str
    processed: int
    total: int


ProgressEmit = Callable[[str, "ExtractDetail | str | None"], None]
```

`emit(stage, detail)`: при `stage="extract"` вызывается только с `ExtractDetail`;
при `stage="generate"` — только с `str | None`.

`generate()` до открытия потока делает всю сегодняшнюю синхронную валидацию
(диапазон `num_questions`, `max_files`, `question_types`, `source_kinds`) как
и сейчас — при ошибке поднимает `HTTPException` обычным образом (FastAPI сам
превратит её в JSON-ответ с нужным статусом, пока поток ещё не начат).

Дальше возвращает `StreamingResponse(event_stream(), media_type="text/event-stream")`,
где `event_stream()` — async-генератор:

```python
async def event_stream():
    queue: asyncio.Queue = asyncio.Queue()

    def emit(stage: str, detail: str | None = None) -> None:
        queue.put_nowait({"type": "progress", "stage": stage, "detail": detail})

    async def run() -> None:
        try:
            # тело сегодняшней функции generate() после валидации:
            # чтение файлов, extract_text(..., emit), combine(), generate_quiz(..., emit),
            # разрешение diagram_id
            response = ...  # GenerateResponse
            await queue.put({"type": "result", "data": response.model_dump()})
        except HTTPException as e:
            await queue.put({"type": "error", "status": e.status_code, "detail": e.detail})
        except Exception as e:  # noqa: BLE001
            await queue.put({"type": "error", "status": 500, "detail": str(e)})
        finally:
            await queue.put(None)  # сигнал конца потока

    task = asyncio.create_task(run())
    try:
        while (item := await queue.get()) is not None:
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
    finally:
        await task
```

### `backend/app/text_extract.py`

Сигнатуры меняются — добавляется обязательный параметр `emit`:

```python
async def extract_text(filename: str, data: bytes, emit: ProgressEmit) -> tuple[str, dict[str, bytes]]
async def _from_pdf(data: bytes, filename: str, emit: ProgressEmit) -> tuple[str, dict[str, bytes]]
```

- `extract_text()`: сразу после входа (до чтения кэша) —
  `emit("extract", {"filename": filename, "processed": 0, "total": 0})`. Для
  не-PDF (`.docx`/`.txt`/`.md`) и для кэш-хита PDF (`cache.exists()`) это
  единственное событие для файла — `total` остаётся `0`.
- `_from_pdf()` (только "живой", не кэшированный путь):
  1. Сразу после локального прохода по всем страницам (`pages_md`
     заполнен, `heavy` посчитан) — `emit("extract", {"filename": filename,
     "processed": len(pages_md) - len(heavy), "total": len(pages_md)})`.
  2. Если `heavy` не пуст — при распознавании, после каждого завершившегося
     `transcribe_page()` (внутри `_recognize`, после `async with sem:` блока)
     увеличивает локальный счётчик завершённых страниц `done` (начиная с
     `len(pages_md) - len(heavy)`) и вызывает
     `emit("extract", {"filename": filename, "processed": done, "total":
     len(pages_md)})`. Порядок событий соответствует порядку завершения
     страниц (не обязательно по возрастанию номера страницы — распознавание
     идёт параллельно, ограничено `vision_concurrency`); к концу `processed`
     всегда достигает `total`.
  `_from_pdf()` получает `filename` и `emit` дополнительными параметрами.

### `backend/app/llm.py`

```python
async def generate_quiz(
    context: str,
    num_questions: int | None,
    types: list[str],
    topics: str | None,
    source_kinds: list[SourceKind],
    emit: ProgressEmit,
) -> Quiz
```

- Перед первым вызовом `_call_llm()` в цикле (`attempt == 1`):
  `emit("generate", None)`.
- Перед повторной попыткой (`attempt == 2`, после невалидного JSON):
  `emit("generate", "ответ модели не прошёл проверку — генерируем заново")`.

`transcribe_page()` не меняется — `emit` ему не нужен, инкремент счётчика
страниц делает вызывающий код в `_from_pdf()`.

## Frontend touchpoints

### `frontend/src/api.ts`

```ts
export async function generateQuiz(
  params: {
    files: File[];
    numQuestions: number | null;
    questionTypes: string[];
    topics: string;
    sourceKinds: string[];
  },
  onProgress: (stage: "extract" | "generate", detail: string | null) => void,
): Promise<GenerateResponse> {
  const fd = new FormData();
  // ...как сегодня...

  const resp = await fetch("/api/generate", { method: "POST", body: fd });
  if (!resp.ok) {
    // синхронная валидация (422 до открытия потока) — как сегодня
    const detail = await resp.json().catch(() => null);
    throw new Error(detail?.detail ?? `Ошибка ${resp.status}`);
  }

  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const frame = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      if (!frame.startsWith("data: ")) continue;
      const evt = JSON.parse(frame.slice(6));
      if (evt.type === "progress") onProgress(evt.stage, evt.detail);
      else if (evt.type === "result") return evt.data as GenerateResponse;
      else if (evt.type === "error") throw new Error(evt.detail);
    }
  }
  throw new Error("поток завершился без результата");
}
```

### `frontend/src/types.ts`

Добавить:

```ts
export type ProgressStage = "extract" | "generate";

export interface ExtractDetail {
  filename: string;
  processed: number;
  total: number;
}

export type ProgressState =
  | { stage: "extract"; detail: ExtractDetail }
  | { stage: "generate"; detail: string | null };
```

`GenerateResponse` не меняется.

### `frontend/src/App.tsx`

`loading: boolean` заменяется на `progress: ProgressState | null` (`null` —
генерация не идёт). `handleSubmit` вызывает
`generateQuiz(v, (stage, detail) => setProgress({ stage, detail } as ProgressState))`,
сбрасывает `progress` в `null` в `finally`.

### Новый компонент — чек-лист прогресса

Например `frontend/src/components/GenerationProgress.tsx`:

```tsx
const STEPS: { stage: ProgressStage; label: string }[] = [
  { stage: "extract", label: "Извлекаем текст из документов" },
  { stage: "generate", label: "Составляем тест" },
];

function extractDetailText(d: ExtractDetail): string | null {
  if (d.total === 0) return d.filename;
  return `${d.filename}: страница ${d.processed} из ${d.total}`;
}

export default function GenerationProgress({ progress }: { progress: ProgressState | null }) {
  if (!progress) return null;
  const currentIdx = STEPS.findIndex((s) => s.stage === progress.stage);
  const detailText = progress.stage === "extract" ? extractDetailText(progress.detail) : progress.detail;
  return (
    <ul className="mt-4 space-y-1 text-sm">
      {STEPS.map((s, i) => (
        <li key={s.stage} className={i > currentIdx ? "text-slate-400" : "text-slate-900"}>
          {i < currentIdx ? "✓" : i === currentIdx ? "⋯" : "○"} {s.label}
          {i === currentIdx && detailText && (
            <div className="ml-4 text-xs text-slate-500">{detailText}</div>
          )}
        </li>
      ))}
    </ul>
  );
}
```

Русский текст для `extract` (`"страница N из M"`) формируется на фронтенде из
числовых `processed`/`total` — бэкенд отдаёт только числа, языка в протоколе
нет.

`App.tsx` рендерит `<GenerationProgress progress={progress} />` вместо
сегодняшнего текста «Генерируем…» в `UploadForm` (кнопка сама может по-прежнему
показывать «Генерируем…» / быть задизейблена, пока `progress !== null`).

Точная вёрстка/классы — на усмотрение `frontend-dev`, обязательное: порядок
шагов фиксирован (`extract` → `generate`), пройденные шаги визуально отличаются
от текущего и от ещё не начавшихся, `detail` показывается только у текущего
шага.
