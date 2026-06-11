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

Last reviewed: 2026-06-10
Current local base commit: `55dfab0`

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

Status: `IN_PROGRESS`
Current owner: Codex

Active task: Implement durable social scheduling/history, caption cadence and
no-caption exports, dashboard calendar management, and platform-aware DeepSeek
copy generation.

Starting commit: `a788f35a6b5f441075262475960958563f0556e0`
Feature branch: `feat/publishing-calendar-caption-copy-20260610`

Current ownership:

- `backend/alembic/versions/0014_add_editor_projects_assets_renders_usage.py`
- `backend/alembic/versions/0015_add_clip_overlay_assets.py`
- new migrations after `0015`
- editor/overlay backend and frontend files required by migrations `0014/0015`
- social publish models, schemas, routes, workers, and tests
- export caption models, schemas, rendering, routes, workers, and tests
- dashboard schedule calendar and social publish frontend components
- shared frontend social types and platform metadata
- `docker-compose.yml`
- `HANDOFF_CONTEXT.md`

Do not overlap these files until this task reaches `READY_FOR_REVIEW`.

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

Task started. No new implementation files changed yet.

Preflight:

- Existing working tree contains uncommitted editor, clip overlay, social
  filtering/calendar, connection UI, and retention work.
- Migrations `0014` and `0015` are present locally but uncommitted.
- Host Docker and host pytest are unavailable; backend compile runs locally,
  while migration/tests will run in the VPS backend container before deploy.
- Existing unrelated video-detail size work remains preserved.

## Risks And Unknowns

- The uncommitted editor and overlay changes may be incomplete or overlap with
  another agent's active work.
- The dirty working tree makes broad staging dangerous; deployment commits must
  use an explicit reviewed file list.
- A calendar-only commit that omits the untracked calendar component will break
  the frontend build because `VideosDashboard.tsx` imports it.
- Two agents in separate clones cannot communicate through this file until it
  has been committed and pushed.
- The VPS still contains unrelated live uncommitted work. The carousel release
  was fast-forwarded without resetting those files.
- Production `ANTHROPIC_API_KEY` currently returns HTTP 401. Carousel generation
  remains operational through the configured DeepSeek fallback.
- Production R2 settings are placeholders, so carousel render storage currently
  falls back to container-local `/tmp/clipbandit-storage`. Configure valid R2
  credentials before relying on generated carousel URLs as durable artifacts.
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

The video detail size control is deployed. The next agent should preserve this
behavior while working in `VideoDetailPanel.tsx`.

## Deployment Record

Status: Deployed.

- Reviewed commit SHA: `36ea6cfdd305b8844b3a20403a29610a9f6d6f1c`
- Deployed commit SHA: `36ea6cfdd305b8844b3a20403a29610a9f6d6f1c`
- Deployment time: 2026-06-10 06:22 UTC
- Services rebuilt/restarted: `frontend`, `backend`
- `tools/deploy_guard.sh`: PASS
- Public route smoke: protected video route returned expected `307` to `/login`
- Feature source smoke: deployed component contains the player-size state,
  slider, 25% default, and responsive width clamp
- Backup branch: `backup/pre-video-size-20260610T062108Z`
- Component backup:
  `/opt/clipbandit_backups/VideoDetailPanel-20260610T062108Z.tsx`
- Rollback commit: `55dfab0d4d210346671355ea096c81a653315cdc`
