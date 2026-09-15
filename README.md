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

## Тестирование и линт

Backend:
```bash
cd backend
uv run ruff check .
uv run pytest -q
```

Frontend:
```bash
cd frontend
npm run lint
npm run test
npm run build
```

## Процесс разработки фич: от идеи до мёржа

Новые фичи не пишутся вручную с нуля — они проходят через агентный пайплайн (роли описаны в
`.claude/agents/`, оркестрация — в `.claude/skills/handoff/SKILL.md`). Конкретная
последовательность действий в Claude Code:

### 1. Обсудить фичу с analyst-агентом

В обычной локальной сессии Claude Code явно попросите использовать нужного subagent'а, например:

```
Используй subagent analyst, чтобы обсудить со мной новую фичу: <опишите идею своими словами>
```

Отвечайте на уточняющие вопросы агента (проблема, happy path, что вне скоупа, edge cases).
Ничего не пишется в репозиторий, пока вы не подтвердите формулировку явно в чате.

### 2. Подтвердить и получить черновик спеки

После вашего подтверждения агент создаёт на диске (пока не в git):
- `docs/features/<slug>/spec.md` — описание фичи, пользовательские сценарии, критерии приёмки.
- `docs/features/<slug>/api-contract.md` — конкретный контракт эндпоинтов (request/response).

Просмотрите оба файла. Если что-то не так — попросите агента исправить, это ещё черновик
(`status: draft`).

### 3. Одобрить спеку

Когда спека устраивает, скажите агенту явно: **"подтверждаю"** / **"одобряю"**. Только после
этого `analyst` сам:
- проставляет `status: approved` в обоих файлах,
- коммитит и пушит их в `main`:
  ```bash
  git add docs/features/<slug>/
  git commit -m "docs: approve <slug> spec + API contract"
  git push
  ```

### 4. Запустить пайплайн

В той же (или новой) сессии Claude Code:

```
/handoff <slug>
```

Скилл проверяет, что working tree чистый и спека одобрена на `origin/main`, затем через
`RemoteTrigger` поднимает 4 облачные routine (`backend-dev`, `qa-backend`, `frontend-dev`,
`qa-frontend`) и вебхуки между ними. В конце вы получите ссылки вида
`https://claude.ai/code/routines/<id>` — на этом ваше участие в сессии Claude Code
заканчивается, можно закрывать ноутбук.

### 5. Backend: PR и ревью QA

Дальше без вашего участия:
- `backend-dev` реализует фичу, гоняет `ruff`/`pytest`, открывает PR `[backend] <slug>: ...` в
  `Max-Size/tutoroll`.
- `qa` сверяет PR с `api-contract.md` как чёрный ящик (реальные запросы к поднятому серверу) и
  оставляет комментарий-вердикт в PR — не апрувит и не мержит.
- Если QA нашёл несоответствия — `backend-dev` просыпается по её комментарию и чинит (максимум
  2 захода); после 2-й неудачи PR получает комментарий `needs-human` и лейбл — дальше только вы.

### 6. Смёржить backend-PR вручную

Откройте PR на GitHub (или `gh pr list`, `gh pr view <n>`), прочитайте вердикт QA и код, и если
всё устраивает — смёржите сами (`gh pr merge <n>` или кнопкой на GitHub). Это единственный
ручной шаг между backend и frontend: мёрж запускает следующий вебхук автоматически.

### 7. Frontend: PR и ревью QA

Мёрж backend-PR будит `frontend-dev`: он читает уже смёрженный `api-contract.md`, реализует UI,
гоняет `lint`/`test`/`build`, открывает PR `[frontend] <slug>: ...`. `qa` проверяет его так же,
как backend, тем же циклом (до 2 фиксов, иначе `needs-human`).

### 8. Смёржить frontend-PR вручную

Так же вручную ревьюите и мёржите — это финальный шаг, фича доехала до `main`.

Полное описание условий и защит от ложных срабатываний вебхуков — в `CLAUDE.md` и в самих
`.claude/agents/*.md`.
