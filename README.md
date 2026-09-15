# test_generator

MVP: генератор тестов по загруженным документам. FastAPI + Polza.ai (LLM API) + React (TS + Tailwind).

## Как это работает

```
React (upload файлов, N вопросов)
   │  multipart POST /api/generate
   ▼
FastAPI ──► извлечение текста (pdf/docx/txt)
        ──► сборка промпта
        ──► Polza.ai (OpenAI-совместимый LLM API) ──► JSON с вопросами
   ▲
   └── валидация схемы (Pydantic) + ретрай при кривом JSON
```

RAG на этом этапе нет: весь текст документа кладётся в промпт. Если документы большие —
резать по темам или подключать retrieval позже (см. `backend/app/llm.py`).

## Запуск

### 1. Ключ Polza.ai

Зарегистрироваться на https://polza.ai, создать API-ключ
(см. https://polza.ai/docs/glavnoe/quickstart) и вписать его в `.env` (`POLZA_API_KEY`).

### 2. Backend (uv)

```bash
cd backend
uv sync                 # создаёт .venv и ставит зависимости
cp .env.example .env    # вписать POLZA_API_KEY
uv run uvicorn app.main:app --reload --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173, проксирует /api на :8000
```

## Структура

- `backend/pyproject.toml` — зависимости (управляются через uv)
- `backend/app/main.py` — HTTP-эндпоинты
- `backend/app/text_extract.py` — pdf/docx/txt → текст
- `backend/app/llm.py` — клиент Polza.ai + промпт + ретрай
- `backend/app/schemas.py` — модель теста (Quiz/Question)
- `frontend/src/App.tsx` — форма загрузки + отображение теста
- `frontend/src/api.ts` — вызов бэка
