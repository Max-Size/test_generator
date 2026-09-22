# CLAUDE.md

Guidance for Claude Code sessions (local or cloud) working in this repository.

## What this is

`test_generator` — MVP-сервис, который генерирует тест (квиз) по загруженным документам. Backend: FastAPI + Polza.ai (OpenAI-совместимый LLM API). Frontend: React + TypeScript + Vite. Подробности архитектуры — в `README.md`.

## Structure

- `backend/app/main.py` — HTTP-эндпоинты.
- `backend/app/text_extract.py`, `text_clean.py` — извлечение и очистка текста из pdf/docx/txt.
- `backend/app/llm.py` — клиент Polza.ai, промпты, ретраи.
- `backend/app/schemas.py` — pydantic-модели (`Quiz`, `Question`, ...).
- `backend/app/config.py` — настройки (`pydantic-settings`, читает `.env`).
- `backend/app/obs.py` — логирование и `stage()`-контекстменеджер для замера этапов запроса; используй его для новых долгих операций вместо голого `log.info`.
- `backend/tests/` — pytest.
- `frontend/src/api.ts` — вызовы backend (`fetch`-based, без библиотек вроде axios/react-query — сохраняй этот стиль).
- `frontend/src/types.ts` — типы, зеркалящие pydantic-схемы backend.
- `frontend/src/components/` — React-компоненты.
- `frontend/src/api.test.ts` — Vitest, паттерн для новых тестов.
- `frontend/e2e/run.mjs` — e2e-сценарий на Playwright (headless Chromium): загружает файл через UI, проходит тест, пишет `result.json` и скриншоты.
- `test_samples/` — файлы для e2e; рядом с файлом — `<имя>.e2e.json` с настройками формы и ожиданиями к результату.

## Conventions

- Не добавляй абстракции, флаги конфигурации или обработку ошибок сверх того, что реально нужно для текущей задачи — см. общий принцип "no speculative generality" в этом проекте.
- Backend и frontend не делят типы автоматически — при изменении контракта API обнови оба места (`schemas.py` и `types.ts`) вручную и согласованно.
- Зависимости backend — только через `uv` (`uv add`, `uv sync`), никогда `pip install` напрямую.

## Testing & linting — run before considering any change done

Backend (from `backend/`):
```bash
uv run ruff check .
uv run pytest -q
```

Frontend (from `frontend/`):
```bash
npm run lint
npm run test
npm run build
```

All four must be clean before opening or updating a PR.

E2E (real LLM calls, costs money, ~1–2 min per sample) — normally run by the `qa-e2e` agent, manually:
```bash
cd backend && INGEST_CACHE_DIR=$(mktemp -d) uv run uvicorn app.main:app --port 8001 &
cd frontend && API_PROXY_TARGET=http://localhost:8001 npx vite --port 5174 --strictPort &
cd frontend && node e2e/run.mjs --sample ../test_samples/<file> --out <dir>
```
First time: `npx playwright install chromium`.

## Feature pipeline (analyst → dev subagents → QA subagents)

Features go through a defined agent pipeline rather than ad hoc implementation — see `.claude/agents/analyst.md`, `backend-dev.md`, `frontend-dev.md`, `qa.md`, `qa-e2e.md`, and `.claude/skills/implement/SKILL.md` for the full roles. Everything runs as subagents inside ONE Claude Code session (local or claude.ai/code); we deliberately do not use cloud routines or GitHub webhooks, because event-triggered wake-ups proved unreliable.

Summary:
1. The CEO discusses a feature interactively with the `analyst` agent, which writes `docs/features/<slug>/spec.md` and `api-contract.md` (draft, then `status: approved` only after the CEO's own explicit sign-off, then committed to `main`).
2. `/implement <slug>` runs the rest in that session: `backend-dev` and `frontend-dev` subagents implement their sides in parallel against the approved contract (they don't commit) → two separate `qa` subagents, one per side, verify the branch against the spec/contract in a clean worktree and return `QA-VERDICT: PASS|FAIL` → on FAIL the dev fixes and QA re-checks (max 2 rounds per side, then `needs-human`) → once both code QAs pass, a `qa-e2e` subagent starts the real backend + frontend from the branch on ports 8001/5174, runs every file in `test_samples/` through the UI in headless Chromium (Playwright — so it works the same locally and in cloud sessions), looks at the screenshots and returns a verdict with findings tagged `[backend]`/`[frontend]`/`[unclear]`/`[env]`; findings are routed to the matching dev, max 2 rounds → the orchestrator opens ONE PR and posts the three QA verdicts as comments → the CEO merges manually. Nobody but the CEO merges.
3. QA (code and e2e) is given only the slug, role and branch — never a summary of how the code was written — so it verifies from the spec, not from the author's reasoning. Don't weaken that when editing prompts.
