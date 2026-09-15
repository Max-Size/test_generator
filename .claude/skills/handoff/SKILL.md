---
name: handoff
description: Hands an approved feature spec off to the unattended dev/QA pipeline (cloud routines). Use when the CEO has finished the analyst conversation for a feature and wants development to proceed without further supervision.
---

# /handoff <slug>

Wires up the cloud-routine pipeline for one feature so it runs to completion (backend → QA → wait for human merge → frontend → QA → wait for human merge) without the CEO needing to keep a session open. Takes one argument: the feature slug (matches `docs/features/<slug>/`).

## 0. Preconditions

1. `git fetch origin && git status` — working tree should be clean; if not, tell the CEO and stop (don't hand off with uncommitted local changes lying around).
2. Confirm `docs/features/<slug>/spec.md` and `docs/features/<slug>/api-contract.md` exist on `origin/main` (`git show origin/main:docs/features/<slug>/spec.md`) and both have `status: approved` in frontmatter. If either is missing or still `draft`, stop and tell the CEO to finish with the `analyst` agent first — never lower this bar yourself.
3. Confirm `gh auth status` works locally (needed later for you, not for the routines — they use the repo's connected GitHub App, not your local `gh`).
4. `ToolSearch select:RemoteTrigger` if it isn't loaded yet.

## 1. Known constraints (read before writing calls)

- Repo: `https://github.com/Max-Size/tutoroll`. Environment: `env_01BVPSdWMHaCAtryCx54oGWZ` (the only one configured so far — confirm with the CEO if a new one shows up in `RemoteTrigger{action:"list"}` output that looks more appropriate).
- `create` requires exactly one of `cron_expression` / `run_once_at` even for a routine you intend to drive purely by webhook — use a `run_once_at` far in the future (e.g. +1 year) as a placeholder for webhook-only routines, and a near-future one (+2 minutes from actual current time — fetch it with `date -u +%Y-%m-%dT%H:%M:%SZ`, don't guess) for the routine that should fire immediately.
- `create_webhook_trigger` body shape confirmed by testing (2026-09-15): `{"routine_trigger_id": "...", "source": "github", "hook_type": "app", "scope_id": "<owner>/<repo>", "events": ["pull_request"]}`. A `filter` object (tried with `action`, `merged`, `base` keys) is accepted (HTTP 200) but the API does **not** echo it back in the response — so its effect is unverified. Treat any filter as best-effort only; correctness must come from the agent's own precondition checks (already built into `backend-dev.md`/`frontend-dev.md`/`qa.md`), never from trusting the webhook payload.
- Confirmed broken in practice (2026-09-15, `context-budget` feature): the `pull_request`/`{"action":"opened"}` webhook that was meant to wake `qa-backend` never fired, even though GitHub recorded the PR-opened event and the installed GitHub App is subscribed to `pull_request`. Root cause unconfirmed (likely the filter silently dropping the event on the Anthropic side — see point above) but not worth re-litigating per feature. **Do not wire that webhook anymore.** Instead, `backend-dev`/`frontend-dev` call `RemoteTrigger{action:"run", trigger_id:"<qa-routine-id>"}` themselves right after opening (or updating) their PR — see step 2's `qa-trigger-id` prompt line and each agent's own "Kicking off QA" section. This means you must create the QA routines (R2, R4) *before* the dev routines (R1, R3), so you have their trigger_ids to embed. The `pull_request`/merged webhook that wakes `frontend-dev` (§3.3) stays as a webhook — a human merging a PR isn't an agent action there's anyone to call `RemoteTrigger` from.
- `qa.md` already de-dupes (checks its last `QA:` comment against the PR's latest commit) in case a stray webhook and a direct trigger both fire — you don't need to guard against that yourself.
- A `run_once_at` self-disables the routine once it fires (`enabled` flips to `false`, `ended_reason: "run_once_fired"`) — confirmed 2026-09-15 when R1 (backend-dev) went disabled right after its near-future fire. A disabled routine will not wake for its webhooks either (untested but assume the worst). **Immediately after R1's initial `run_once_at` has fired** (check with `RemoteTrigger{action:"get", trigger_id:"<R1>"}`), re-arm it with a new far-future `run_once_at` (same `update{run_once_at: "<+1 year>"}` pattern as R2/R4) so its `issue_comment` webhook (fix-mode wake) keeps working. `update{enabled:true}` alone does **not** work post-fire — the API rejects it (`ended_run_once_fired`) and requires a new `run_once_at`/`cron_expression` to re-arm.
- There is no delete/remove action for routines or webhook triggers in this API. Getting the config right before creating matters more than usual — double check `body` before calling `create`/`create_webhook_trigger`. If you create something wrong, `update{enabled:false}` it rather than leaving it live, and tell the CEO it's orphaned (they can delete routines at https://claude.ai/code/routines).
- Generate a fresh lowercase UUIDv4 per routine's `events[].data.uuid` (`python3 -c "import uuid; print(uuid.uuid4())"`), never reuse one.

## 2. Create the four routines

For each, `job_config.ccr.session_context.sources` is `[{"git_repository": {"url": "https://github.com/Max-Size/tutoroll"}}]` and `model` is `claude-sonnet-5`.

Create **R2 and R4 first** — R1 and R3's prompts need to embed their trigger_ids so the dev agents can call `RemoteTrigger{action:"run"}` on them directly instead of relying on a webhook (see §1).

| Routine | name | allowed_tools | run_once_at | Initial prompt |
|---|---|---|---|---|
| R2 qa-backend | `qa-backend:<slug>` | Bash, Read, Grep, Glob | now + 1year | see below |
| R4 qa-frontend | `qa-frontend:<slug>` | Bash, Read, Grep, Glob | now + 1year | see below |
| R1 backend-dev | `backend-dev:<slug>` | Bash, Read, Write, Edit, Glob, Grep, RemoteTrigger | now + 2min | see below |
| R3 frontend-dev | `frontend-dev:<slug>` | Bash, Read, Write, Edit, Glob, Grep, RemoteTrigger | now + 1year | see below |

Prompts (fill in `<slug>` and, for R1/R3, the trigger_id from creating R2/R4 — keep the rest verbatim; the routine reads its full instructions from the repo, this just points it there):

- **R2**: `You are acting as the .claude/agents/qa.md role for feature slug "<slug>", role "backend". Read that file in the repo and follow it exactly.`
- **R4**: `You are acting as the .claude/agents/qa.md role for feature slug "<slug>", role "frontend". Read that file in the repo and follow it exactly.`
- **R1**: `You are acting as the .claude/agents/backend-dev.md role for feature slug "<slug>". qa-trigger-id: <R2's trigger_id>. Read that file in the repo and follow it exactly.`
- **R3**: `You are acting as the .claude/agents/frontend-dev.md role for feature slug "<slug>". qa-trigger-id: <R4's trigger_id>. Read that file in the repo and follow it exactly.`

Create them with `RemoteTrigger{action:"create", body:{...}}` one at a time (need each `trigger_id` for the webhook step, and R2/R4's ids for R1/R3's prompts). Record the four `id`s.

## 3. Wire the webhooks

All `source: "github"`, `hook_type: "app"`, `scope_id: "Max-Size/tutoroll"`, `events: ["pull_request"]` unless noted. There is no webhook for "backend/frontend PR opened" anymore — `backend-dev`/`frontend-dev` call `RemoteTrigger{action:"run"}` on `qa-backend`/`qa-frontend` themselves right after opening the PR (see §1), which is what actually starts QA.

1. On R1 (backend-dev) — fires when QA leaves a fix-request comment: `events: ["issue_comment"]`, no filter (agent-side self-check decides relevance, see §1).
2. On R3 (frontend-dev) — fires when the backend PR merges: `events: ["pull_request"]`, `filter: {"action": "closed", "merged": true, "base": "main"}`.
3. On R3 (frontend-dev) again — fires when QA leaves a fix-request comment on the frontend PR: `events: ["issue_comment"]`, no filter.

(These three still depend on a webhook because no agent action triggers them — a human merging a PR, or QA leaving a comment, isn't something `backend-dev`/`frontend-dev` can call `RemoteTrigger` for themselves. Their own precondition checks in `backend-dev.md`/`frontend-dev.md`/`qa.md` still guard against a misdirected or duplicate wake-up.)

## 4. Re-arm R1 after its first fire

R1's `run_once_at` (+2min) will fire on its own shortly after you finish §3. Wait for it (`RemoteTrigger{action:"list_runs", trigger_id:"<R1>"}` shows a run), then `RemoteTrigger{action:"get", trigger_id:"<R1>"}` — once `enabled` is `false` / `ended_reason` is `run_once_fired`, immediately `update{run_once_at: "<+1 year>"}` it (see §1). Skipping this leaves R1 unable to wake for fix-mode requests later.

## 5. Report to the CEO

Give them:
- The four routine IDs and their `https://claude.ai/code/routines/{id}` links.
- A one-line reminder: backend PR will show up on GitHub for review; once they merge it, frontend starts on its own; they'll need to merge that one too.
- That QA comments (not approvals) land on each PR, and after 2 failed fix rounds a PR gets a `needs-human`-style comment instead of looping forever.

Do not run anything else automatically after this — the routines take it from here.
