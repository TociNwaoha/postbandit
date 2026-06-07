# Agent Handoff Context

This file is the shared continuity record for agents working on PostBandit.
Read it before changing code and update it before handing work to another agent.

## Handoff Rules

- Keep this file concise and current; replace stale task details instead of appending a long diary.
- Record only verified facts. Mark assumptions and unverified runtime behavior clearly.
- Record the starting commit SHA before editing.
- Declare the files or modules owned by the active task before editing them.
- List files changed for the current task, including migrations and environment variables.
- Record validation commands and their results.
- Do not claim a feature is production-ready until its real runtime path has been verified.
- Preserve unrelated uncommitted changes and note any overlapping work.
- Do not deploy an uncommitted or partially reviewed working tree.
- Put durable human guidance in `AGENTS.md` only when the user explicitly requests it.
- Use `WORKLOG.md` for longer historical notes when needed.

## Two-Agent Workflow

The default roles are:

- Implementing agent: owns the requested change, focused tests, and an initial
  handoff update.
- Reviewing/deploying agent: reviews the exact diff, improves it when needed,
  reruns validation, commits the intended files, deploys the exact commit, and
  records production verification.

Task lifecycle:

1. `PLANNED`: Record the task, base commit, intended behavior, and owned files.
2. `IN_PROGRESS`: Implement only within the declared ownership area. Add newly
   discovered files to this handoff before editing them.
3. `READY_FOR_REVIEW`: Record every changed file, known limitation, and exact
   validation result. Do not deploy at this stage.
4. `REVIEWING`: The second agent checks the diff against the recorded base SHA,
   verifies no unrelated changes are included, and records any follow-up edits.
5. `APPROVED_FOR_DEPLOY`: Build/tests pass and the user has approved deployment
   when approval is required by `AGENTS.md`.
6. `DEPLOYED`: Record the deployed commit SHA, services rebuilt, deploy time,
   deploy-guard result, and feature-specific smoke test.

Coordination rules:

- Work sequentially in a shared folder. The reviewing agent starts only after
  the implementing agent stops editing and marks the task `READY_FOR_REVIEW`.
- Only one agent owns a file at a time.
- A reviewing agent may improve owned files after changing the status to
  `REVIEWING` and documenting the additional edits.
- Do not use broad staging such as `git add .` in this dirty repository. Stage
  an explicit reviewed file list.
- Untracked files needed by tracked imports must be included in the same commit.
- If `HEAD` changed since the recorded base SHA, inspect the intervening commits
  and revalidate before deployment.
- The handoff file must be committed to be visible in another clone or on the
  VPS. An untracked handoff is visible only to agents sharing this local folder.

## Project Summary

PostBandit is a video repurposing and social distribution platform. Its main
workflow is:

1. Upload or import source media.
2. Transcribe and generate scored clip candidates.
3. Edit, preview, and export content.
4. Connect social accounts and publish to supported destinations.

The public product name is PostBandit. Some repository, service, and legacy
identifiers still use ClipBandit.

## Architecture

- Frontend: Next.js and React in `frontend/`
- API: FastAPI in `backend/app/`
- Background jobs: Celery-style workers with Redis
- Database: PostgreSQL with Alembic migrations
- Media processing: FFmpeg-backed services and worker tasks
- Deployment: Docker Compose behind Nginx
- Public domains: `postbandit.com` and `api.postbandit.com`

## Current Repository State

Last reviewed: 2026-06-07
Current local base commit: `243ab24`

- The working tree contains substantial uncommitted changes. Do not reset,
  discard, or overwrite them.
- A new editor subsystem is present but uncommitted.
- New editor work includes API routes, project/assets/render models, services,
  worker tasks, frontend components, types, and migration `0014`.
- Additional uncommitted clip overlay work includes migration `0015`, overlay
  models/services, rendering integration, frontend changes, and tests.
- Social publishing, video import, export, rendering, dashboard, and connection
  files also have local modifications.
- `WORKLOG.md` currently describes older Prompt 7 work and should not be treated
  as the authoritative current-task status.

## Current Objective

Status: `APPROVED_FOR_DEPLOY`
Current owner: Reviewing agent

Active task: Add eight researched carousel template designs and production renderers.

Current ownership:

- `backend/app/services/carousel.py`
- `backend/app/services/carousel_renderer/render_modern.py`
- `backend/tests/test_carousel_service.py`
- `frontend/public/template-previews/`
- `HANDOFF_CONTEXT.md`

The calendar task remains planned but is not owned or modified by this task.

Before starting new work:

1. Run `git status --short`.
2. Inspect diffs for files that overlap the requested task.
3. Identify which changes already exist and which agent/user owns them.
4. Make the smallest compatible change.
5. Run focused tests, then broader checks when the change affects shared paths.

## Active Work Areas

- Editor project creation, preview, assets, duplication, and rendering
- Clip overlay assets and overlay-aware export rendering
- Social provider capability and publish filtering behavior
- Dashboard scheduling/calendar UI
- Video import and cleanup behavior

These areas are inferred from the current working tree. Their completeness and
production runtime status have not been fully verified in this handoff.

## Decisions And Guardrails

- Direct upload is the baseline path and must not regress.
- YouTube import is best-effort and must expose honest recovery options.
- Facebook automated publishing targets Pages; personal-profile sharing is manual.
- Instagram uses Instagram Login for professional accounts.
- TikTok is media-first and must report direct-post versus upload/draft behavior honestly.
- Provider capabilities must be explicit rather than assumed to be universal.
- Runtime URLs and OAuth callbacks must come from production configuration.
- Prefer compatibility changes over destructive migrations for existing data.
- Keep Nginx as the public entry point and internal services private.

## Current Task Changes

Task: Add eight more carousel designs based on current editorial, scrapbook,
brutalist, data-card, glass, retro-futurist, luxury, and case-study patterns.

Files changed:

- `HANDOFF_CONTEXT.md` (created)
- `AGENTS.md` (contains an existing local handoff-guidance edit, but is outside
  the declared carousel ownership and is not part of this reviewed commit)
- `backend/app/services/carousel.py` (registered eight templates and persisted
  `template_id` in normalized render config)
- `backend/app/services/carousel_renderer/render_modern.py` (shared themed
  renderer for hook, body, and CTA slides)
- `backend/tests/test_carousel_service.py` (template registry and theme tests)
- `frontend/public/template-previews/editorial-sun.png`
- `frontend/public/template-previews/paper-notes.png`
- `frontend/public/template-previews/signal-brutalist.png`
- `frontend/public/template-previews/data-mint.png`
- `frontend/public/template-previews/aurora-glass.png`
- `frontend/public/template-previews/retro-future.png`
- `frontend/public/template-previews/luxe-mono.png`
- `frontend/public/template-previews/case-study.png`

Validation:

- Confirmed the file follows the repository guidance in `AGENTS.md`.
- Confirmed the repository is on `main` at `243ab24`, matching `origin/main`.
- Confirmed `HANDOFF_CONTEXT.md` is currently untracked and therefore local-only.
- Confirmed the calendar component is currently untracked while its dashboard
  import is a tracked-file modification.
- Confirmed `tools/deploy_guard.sh` validates containers, frontend runtime URLs,
  backend health, CORS, and unauthenticated API behavior after deployment.
- `PYTHONPATH=backend pytest -q backend/tests/test_carousel_service.py` was
  attempted on the host and failed because `pytest` is not installed locally.
- `python3 -m py_compile` passed for carousel service, renderer, and tests.
- The same focused test suite was run in the project backend Docker image using
  an isolated reviewed bundle: `21 passed, 1 warning in 6.00s`.
- Rendered all six slide positions for all eight modern themes: 48 output PNGs
  completed without errors.
- Visually reviewed all eight regenerated 1080x1350 template preview PNGs.
- Review fix applied: the patterned footer area is now cleared before footer
  text so `signal-brutalist` and `retro-future` keep readable handles/counters.
- `npm run build` passed in `frontend/`, including lint and TypeScript checks.
- `git diff --check` passed for the reviewed carousel and handoff files.

## Risks And Unknowns

- The uncommitted editor and overlay changes may be incomplete or overlap with
  another agent's active work.
- The dirty working tree makes broad staging dangerous; deployment commits must
  use an explicit reviewed file list.
- A calendar-only commit that omits the untracked calendar component will break
  the frontend build because `VideosDashboard.tsx` imports it.
- Two agents in separate clones cannot communicate through this file until it
  has been committed and pushed.
- Production deployment status has not yet been established for this commit.
- Exact-SHA deployment must account for the dirty VPS tree. A hard reset to a
  carousel-only commit could discard currently deployed uncommitted production
  work unless that work is already represented in the release SHA.
- Provider integrations still require real OAuth and publish-path verification
  in the configured production environment.

## Next Agent Checklist

- Confirm the current task status and base SHA before editing.
- Confirm ownership before touching calendar or dashboard files.
- Update `Current Task Changes` as implementation proceeds.
- Record test/build/deployment results, including failures.
- Note new environment variables, migrations, API contracts, or compatibility concerns.
- Leave the next agent one concrete starting point.

## Next Starting Point

Commit the reviewed carousel files plus this handoff file with an explicit
file list. Before deploying, verify whether the VPS can safely reset to the
exact release SHA without dropping unrelated uncommitted production changes.

## Deployment Record

Status: Approved for deploy, not deployed yet.

- Reviewed commit SHA: Pending commit
- Deployed commit SHA: Not set
- Services rebuilt: Not set
- `tools/deploy_guard.sh`: Not run
- Feature smoke test: Not run
- Rollback commit: `243ab24` unless a newer verified production commit is recorded
