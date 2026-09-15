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

## Feature pipeline (analyst → dev agents → QA)

Features go through a defined agent pipeline rather than ad hoc implementation — see `.claude/agents/analyst.md`, `backend-dev.md`, `frontend-dev.md`, `qa.md`, and `.claude/skills/handoff/SKILL.md` for the full roles.

Summary:
1. The CEO discusses a feature interactively with the `analyst` agent, which writes `docs/features/<slug>/spec.md` and `api-contract.md` (draft, then `status: approved` only after explicit sign-off).
2. `/handoff <slug>` wires the approved feature to unattended cloud routines: `backend-dev` implements and opens a PR → `qa` verifies it against the contract as a black box and comments (never merges) → the CEO merges manually → `frontend-dev` wakes up, implements against the now-merged contract, opens a PR → `qa` verifies again → the CEO merges.
3. Every agent re-derives its own precondition from repo state (branch names, PR state, spec `status`) rather than trusting who/what woke it — webhook filtering in this pipeline is best-effort, not authoritative. Don't remove those checks when editing agent prompts.

If you are a `backend-dev`/`frontend-dev`/`qa` cloud routine reading this: your actual task instructions are in the corresponding `.claude/agents/*.md` file referenced in your prompt — read that file, not just this one.
