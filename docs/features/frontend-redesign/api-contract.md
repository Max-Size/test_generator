---
slug: frontend-redesign
status: approved
---

# API contract: frontend-redesign

## Backend changes

None. This feature does not add, remove or change any endpoint, request/response
shape, or SSE event format. `backend/app/schemas.py`, `backend/app/main.py` and
`backend/app/llm.py` are untouched.

`backend-dev` has nothing to implement for this feature — `/implement` should
only run `frontend-dev` (and frontend `qa`) for `frontend-redesign`.

## Frontend touchpoints

Existing types/calls reused as-is, no signature changes:

- `frontend/src/api.ts::generateQuiz()` — same params, same `onProgress`
  callback shape (`ProgressState` via `frontend/src/types.ts`), same
  `GenerateResponse` return type.
- `frontend/src/types.ts` — `Quiz`, `Question`, `QuestionType`, `Diagram`,
  `GenerateResponse`, `TruncatedFile`, `ProgressState`, `ExtractDetail` are
  all unchanged. Only additive, purely-local UI state (e.g. a `View` union
  type, per-question "answered" derivation) may be introduced in components —
  no new fields in these shared types.

Components rewritten (markup/styling and, where noted in `spec.md`,
client-side behavior — no new backend calls introduced by any of them):

- `frontend/src/App.tsx` — becomes the `form | loading | test | review`
  view-state owner.
- `frontend/src/components/UploadForm.tsx` — drag&drop, file list, tiles,
  same `FormValues` shape and `onSubmit` contract.
- `frontend/src/components/GenerationProgress.tsx` — new visuals over the
  same `ProgressState`/`ExtractDetail` props.
- `frontend/src/components/QuizView.tsx` — split into `test`/`review`
  rendering of the same `Quiz`/`Question` data, adds the unanswered-confirm
  step described in `spec.md`.
- `frontend/src/components/QuestionDiagram.tsx` — same `Diagram` prop, new
  `.paper`/`.fig` wrapper.
- `frontend/src/components/RichText.tsx` — gains an optional display-mode
  wrapper for block-level LaTeX (`$$...$$`/`\[...\]`); inline math parsing
  (`$...$`/`\(...\)`) and the `children: string` prop contract are unchanged.
- `frontend/src/index.css` — replaces Tailwind with the ported design-system
  CSS (tokens + component classes from the approved design).
- `frontend/index.html` — adds the Google Fonts `<link>` for Onest / STIX
  Two Text.
- `frontend/package.json`, `frontend/vite.config.ts` — remove `tailwindcss`
  and `@tailwindcss/vite`.

No new environment variables, no new files under `backend/`.
