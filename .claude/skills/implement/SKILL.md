---
name: implement
description: Implements an approved feature spec end-to-end inside the current session — backend-dev and frontend-dev subagents write the code, two independent code-QA subagents verify it against the spec, an e2e QA subagent runs the real app in headless Chromium on test_samples/, and one PR is opened. Use when the CEO has approved a spec via the analyst and wants the feature built.
---

# /implement <slug>

Runs the whole dev + QA cycle for one feature in this session, with subagents, and ends with one PR for the CEO to merge. No cloud routines, no webhooks — every step is an explicit subagent call whose result you read directly. Takes one argument: the feature slug (matches `docs/features/<slug>/`).

You are the orchestrator. You do not write feature code yourself and you do not verify it yourself — that is what the subagents are for.

## 0. Preconditions

1. `git fetch origin && git status` — the working tree must be clean and `main` up to date with `origin/main`; otherwise tell the CEO and stop.
2. `git show origin/main:docs/features/<slug>/spec.md` and `.../api-contract.md` both exist and have `status: approved`. If not, stop and tell the CEO to finish with the `analyst` agent first — never lower this bar yourself.
3. No branch `feature/<slug>` exists locally or on `origin`. If one does, stop and ask the CEO (leftover work is theirs to decide about).
4. `gh auth status` works.

## 1. Branch and scope

`git checkout -b feature/<slug> origin/main`.

Read `api-contract.md` and decide which sides the feature touches: **backend** (anything in `backend/`) and/or **frontend** (see the contract's "Frontend touchpoints"). A side with no work gets neither a dev nor a QA subagent below. When in doubt, include it.

## 2. Implement

Launch `backend-dev` and `frontend-dev` subagents **in parallel** (one message, two Agent calls) — the approved contract is the only interface between them, and they write to disjoint directories. Prompt: only the slug, e.g. `Implement feature "<slug>".` Neither agent commits or pushes.

When both return, read their reports. If either reports failing checks it could not fix, do not hide it — carry it into the PR body.

Commit per side so the history reads cleanly:
```
git add backend/ && git commit -m "feat(backend): <slug> — <short description>"
git add frontend/ && git commit -m "feat(frontend): <slug> — <short description>"
git status --short   # anything left over? investigate before continuing
```
Docs, tests and other paths a dev agent legitimately touched go with the side they belong to.

## 3. QA — two independent subagents

Launch `qa` twice **in parallel**, once per touched side. Prompt: **exactly** `Feature slug "<slug>", role "backend".` (or `"frontend"`) plus the branch name `feature/<slug>`. Do not summarize the implementation, mention what the devs found tricky, or say what to focus on — QA must derive everything from `spec.md`, `api-contract.md` and the diff, otherwise it inherits your blind spots.

Each returns a verdict starting with `QA-VERDICT: PASS` or `QA-VERDICT: FAIL` and, on FAIL, an itemized list of discrepancies.

## 4. Fix loop (max 2 rounds per side)

On FAIL for a side: re-invoke that side's dev subagent with the slug **and** QA's itemized findings verbatim ("address only these"), commit the result (`fix(<side>): <slug> — address QA`), then re-run that side's QA. After the second failed round for a side stop looping; that side goes into the PR as unresolved.

## 4b. E2E QA — the real app in a browser

Run only when every touched side ended with code-QA PASS. If any side is unresolved, skip e2e (the PR will be a draft anyway) and say "e2e skipped: code QA unresolved" in the PR body.

No push is needed — `qa-e2e` works from a local worktree of `feature/<slug>`. Launch one `qa-e2e` subagent. Prompt: **exactly** `Feature slug "<slug>", branch "feature/<slug>".` — same rule as code QA: no summary of the implementation, no hints.

It returns `QA-VERDICT: PASS|FAIL`; each FAIL item is tagged `[backend]`, `[frontend]`, `[unclear]` or `[env]`.

On FAIL (max 2 rounds total):
- `[env]` items are not code problems — do not send them to devs. If the verdict is FAIL **only** because of `[env]`, stop the e2e loop and carry it into the PR as "e2e could not run: <reason>".
- `[backend]` items → `backend-dev`, `[frontend]` items → `frontend-dev`, `[unclear]` items → both, each with the slug and the items verbatim ("address only these"). Run the needed devs in parallel, commit per side (`fix(<side>): <slug> — address e2e QA`).
- Re-run code QA for every side that changed, then re-run `qa-e2e`. A code-QA FAIL here goes back to step 4 rules for that side.
- After the second failed e2e round, stop; e2e goes into the PR as unresolved.

## 5. Open the PR

```
git push -u origin feature/<slug>
gh pr create --base main --title "<slug>: <short description>" --body "..."
```
Body: one-paragraph summary; a checklist mapping every acceptance criterion in `spec.md` to what was done; the lint/test/build results per side; any dev "known failing checks"; any conservative choices the devs made on ambiguity.

Then post each QA verdict as its own PR comment starting with `QA (backend):` / `QA (frontend):` / `QA (e2e):`. For e2e, include the artifacts path from the verdict (screenshots stay on the machine that ran it).

If anything is unresolved (code QA or e2e still FAIL after 2 rounds, e2e skipped or could not run, or checks red), open the PR as `--draft`, add the `needs-human` label if possible, and say why at the top of the body.

Never merge. Never approve.

## 6. Report

Tell the CEO the PR URL, each QA verdict (backend, frontend, e2e), and anything unresolved — in a few sentences.
