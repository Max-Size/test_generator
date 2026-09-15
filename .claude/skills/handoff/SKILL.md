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
- There is no delete/remove action for routines or webhook triggers in this API. Getting the config right before creating matters more than usual — double check `body` before calling `create`/`create_webhook_trigger`. If you create something wrong, `update{enabled:false}` it rather than leaving it live, and tell the CEO it's orphaned (they can delete routines at https://claude.ai/code/routines).
- Generate a fresh lowercase UUIDv4 per routine's `events[].data.uuid` (`python3 -c "import uuid; print(uuid.uuid4())"`), never reuse one.

## 2. Create the four routines

For each, `job_config.ccr.session_context.sources` is `[{"git_repository": {"url": "https://github.com/Max-Size/tutoroll"}}]` and `model` is `claude-sonnet-5`.

| Routine | name | allowed_tools | run_once_at | Initial prompt |
|---|---|---|---|---|
| R1 backend-dev | `backend-dev:<slug>` | Bash, Read, Write, Edit, Glob, Grep | now + 2min | see below |
| R2 qa-backend | `qa-backend:<slug>` | Bash, Read, Grep, Glob | now + 1year | see below |
| R3 frontend-dev | `frontend-dev:<slug>` | Bash, Read, Write, Edit, Glob, Grep | now + 1year | see below |
| R4 qa-frontend | `qa-frontend:<slug>` | Bash, Read, Grep, Glob | now + 1year | see below |

Prompts (fill in `<slug>`, keep the rest verbatim — the routine reads its full instructions from the repo, this just points it there):

- **R1**: `You are acting as the .claude/agents/backend-dev.md role for feature slug "<slug>". Read that file in the repo and follow it exactly.`
- **R2**: `You are acting as the .claude/agents/qa.md role for feature slug "<slug>", role "backend". Read that file in the repo and follow it exactly.`
- **R3**: `You are acting as the .claude/agents/frontend-dev.md role for feature slug "<slug>". Read that file in the repo and follow it exactly.`
- **R4**: `You are acting as the .claude/agents/qa.md role for feature slug "<slug>", role "frontend". Read that file in the repo and follow it exactly.`

Create them with `RemoteTrigger{action:"create", body:{...}}` one at a time (need each `trigger_id` for the webhook step). Record the four `id`s.

## 3. Wire the webhooks

All `source: "github"`, `hook_type: "app"`, `scope_id: "Max-Size/tutoroll"`, `events: ["pull_request"]` unless noted.

1. On R1 (backend-dev) — fires when QA leaves a fix-request comment: `events: ["issue_comment"]`, no filter (agent-side self-check decides relevance, see §1).
2. On R2 (qa-backend) — fires when the backend PR opens: `events: ["pull_request"]`, `filter: {"action": "opened"}`.
3. On R3 (frontend-dev) — fires when the backend PR merges: `events: ["pull_request"]`, `filter: {"action": "closed", "merged": true, "base": "main"}`.
4. On R4 (qa-frontend) — fires when the frontend PR opens: `events: ["pull_request"]`, `filter: {"action": "opened"}`.
5. On R3 (frontend-dev) again — fires when QA leaves a fix-request comment on the frontend PR: `events: ["issue_comment"]`, no filter.

(R2/R4 firing on *every* PR opened in the repo, not just this feature's, is expected given the unverified filter — their own precondition in `qa.md` resolves the right PR by branch name and does nothing if it doesn't find one for its own slug/role.)

## 4. Report to the CEO

Give them:
- The four routine IDs and their `https://claude.ai/code/routines/{id}` links.
- A one-line reminder: backend PR will show up on GitHub for review; once they merge it, frontend starts on its own; they'll need to merge that one too.
- That QA comments (not approvals) land on each PR, and after 2 failed fix rounds a PR gets a `needs-human`-style comment instead of looping forever.

Do not run anything else automatically after this — the routines take it from here.
