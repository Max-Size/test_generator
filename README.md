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
`.claude/agents/`, оркестрация — в `.claude/skills/implement/SKILL.md`). Всё происходит в одной
сессии Claude Code (локально или в claude.ai/code, в том числе с телефона) через субагентов; облачные
routine и вебхуки GitHub не используются — они работали нестабильно.

### 1. Обсудить фичу с analyst-агентом

Явно попросите использовать нужного subagent'а, например:

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
этого `analyst` сам проставляет `status: approved` в обоих файлах и коммитит их в `main`.

### 4. Запустить реализацию

```
/implement <slug>
```

Скилл проверяет, что working tree чистый и спека одобрена на `origin/main`, создаёт ветку
`feature/<slug>` и дальше в этой же сессии:
- `backend-dev` и `frontend-dev` параллельно реализуют свои части по одобренному контракту и гоняют
  `ruff`/`pytest` и `lint`/`test`/`build` соответственно;
- два независимых `qa` (backend и frontend) проверяют ветку по спеке и контракту в чистом
  worktree и возвращают вердикт `PASS` или `FAIL`;
- при `FAIL` соответствующий dev чинит по списку замечаний, QA проверяет снова (максимум 2 круга
  на сторону, затем PR помечается `needs-human`);
- когда оба code-QA прошли, `qa-e2e` поднимает бэкенд и фронтенд ветки (порты 8001/5174),
  прогоняет каждый файл из `test_samples/` через настоящий UI в headless Chromium (Playwright),
  смотрит скриншоты и выносит вердикт; замечания уходят нужному dev'у (максимум 2 круга);
- оркестратор открывает **один** PR и оставляет в нём три вердикта QA комментариями.

### E2E-проверка вручную

Делает реальные вызовы LLM (платно, ~1–2 мин на файл):
```bash
cd frontend && npx playwright install chromium        # один раз
cd backend && INGEST_CACHE_DIR=$(mktemp -d) uv run uvicorn app.main:app --port 8001 &
cd frontend && API_PROXY_TARGET=http://localhost:8001 npx vite --port 5174 --strictPort &
cd frontend && node e2e/run.mjs --sample ../test_samples/<file> --out /tmp/e2e
```
Результат — `/tmp/e2e/result.json` и скриншоты. Новый сценарий = новый файл в `test_samples/`
плюс, при необходимости, `<имя>.e2e.json` рядом с ним (настройки формы и ожидания к тесту).
Для облачных сессий среда должна пускать в сеть к CDN Playwright и `polza.ai`, а
`POLZA_API_KEY` задаётся переменной окружения.

### 5. Смёржить PR вручную

Прочитайте вердикты QA и код и, если всё устраивает, смёржите сами (`gh pr merge <n>` или
кнопкой на GitHub). Ни один агент не мёржит и не апрувит PR.

Подробности ролей и защит — в `CLAUDE.md` и `.claude/agents/*.md`.
