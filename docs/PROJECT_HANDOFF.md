# PostBandit Project Handoff

Last updated: 2026-07-22

## Product Scope

PostBandit is an AI-powered content workflow platform for creators, churches, agencies, and teams. The core workflow is: import video, transcribe it, generate clips, edit/export clips, and publish or schedule posts across connected social platforms.

The app also includes:

- Social repurpose workflows that poll official source platforms and help repost content to selected destinations.
- Carousel generation through Bandit LM / DeepSeek-backed content generation.
- Content Queue for AI CMO daily carousel drafts.
- Developer API keys and public API v1.
- Stripe Billing V1 with plan limits.
- Post analytics dashboard.
- Backblaze B2 object storage for durable media.

## Current Repository

Local repo:

```bash
cd /Users/tocinwaoha/Projects/clipbandit
```

Primary branch:

```bash
main
```

GitHub remote:

```bash
git@github.com:TociNwaoha/clipbandit.git
```

Because normal SSH can be blocked on some networks, GitHub pushes often use SSH over port 443:

```bash
GIT_SSH_COMMAND='ssh -p 443 -o HostName=ssh.github.com -o StrictHostKeyChecking=accept-new' git push origin main
```

Use explicit staging only. Do not use `git add .` unless the tree has been reviewed and intentionally scoped.

```bash
git status --short
git diff --name-only
git add path/to/file1 path/to/file2
git diff --cached --name-only
git diff --cached
git commit -m "type: concise summary" -m "Detailed engineering context."
```

## VPS / Production

Production VPS:

```text
Host: 147.93.6.2
Path: /opt/clipbandit
User: root
SSH key: ~/.ssh/iqbandit_deploy
```

Production app URLs:

```text
Frontend: https://postbandit.com
Backend public: https://api.postbandit.com
Backend internal health: http://127.0.0.1:8000/health
```

SSH command:

```bash
ssh -i ~/.ssh/iqbandit_deploy root@147.93.6.2
```

Deploy an exact commit:

```bash
RELEASE_SHA=<commit_sha>
ssh -i ~/.ssh/iqbandit_deploy root@147.93.6.2 "set -e
cd /opt/clipbandit
git fetch origin main
git checkout main
git reset --hard $RELEASE_SHA
docker compose up --build -d backend worker worker-beat frontend
sleep 25
docker compose ps
curl -s http://127.0.0.1:8000/health
bash tools/deploy_guard.sh
"
```

For frontend-only deploys:

```bash
ssh -i ~/.ssh/iqbandit_deploy root@147.93.6.2 "set -e
cd /opt/clipbandit
git fetch origin main
git checkout main
git reset --hard <commit_sha>
docker compose up --build -d frontend
sleep 12
docker compose ps frontend
curl -s -o /dev/null -w 'postbandit.com: %{http_code}\n' https://postbandit.com
"
```

For backend migrations, run Alembic inside Docker on the VPS:

```bash
ssh -i ~/.ssh/iqbandit_deploy root@147.93.6.2 "set -e
cd /opt/clipbandit
docker compose exec -T backend alembic upgrade head
docker compose exec -T postgres psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -tAc 'select version_num from alembic_version;'
"
```

Hard stops:

- Do not force-push.
- Do not run `docker compose up -d --force-recreate -V` because it can destroy volumes.
- Do not run migrations locally for production validation; run them in the backend container on the VPS.
- Do not print secrets from `.env`.
- If a migration fails, stop and report before rebuilding more services.

## Runtime Services

Docker Compose services commonly used:

- `frontend`: Next.js 14 production app.
- `backend`: FastAPI app.
- `worker`: Celery workers for ingest, transcribe, score, render, publish, analytics, cleanup.
- `worker-beat`: Celery Beat scheduler.
- `postgres`: PostgreSQL 15.
- `redis`: Celery broker/cache/rate-limit backend.
- `nginx` / reverse proxy path in production compose.

Common checks:

```bash
docker compose ps
curl -s http://127.0.0.1:8000/health
bash tools/deploy_guard.sh
docker compose logs --tail=160 backend
docker compose logs --tail=160 worker
docker compose logs --tail=120 worker-beat
```

## Stack Decisions

Frontend:

- Next.js 14 App Router with client components where dashboard interaction requires browser state.
- Shared API helper in `frontend/src/lib/api.ts`.
- Dashboard pages use `DashboardLayout`, `Sidebar`, and route-specific panels.

Backend:

- FastAPI with SQLAlchemy models and Alembic migrations.
- PostgreSQL stores users, videos, clips, exports, publish jobs, workflow source posts, content queue items, analytics snapshots, and billing metadata.
- Celery + Redis handle long-running jobs instead of blocking web requests.

AI / Media:

- `faster-whisper` runs transcription locally so the platform does not depend on a cloud transcription API for every upload.
- DeepSeek powers copy/platform draft generation. Older code may still contain Anthropic fallback names, but DeepSeek is the current preferred LLM path.
- FFmpeg handles audio extraction, thumbnails, clip rendering, captions, overlays, and social-ready exports.

Storage:

- Backblaze B2 is the durable object store using the S3-compatible boto3 API.
- Object keys are stored in the database. B2 bucket is private; access uses app-generated presigned URLs or backend reads.
- `/tmp/clipbandit-storage` remains a temporary/local fallback area and hot workspace, not the long-term source of truth.
- Thumbnails currently use local cache under `/data/thumbnails`.

Payments:

- Stripe Billing V1 exists with hosted Checkout, Billing Portal, webhook idempotency, and connected-platform limits.
- Never commit live Stripe keys or webhook secrets.

Observability / Ops:

- Sentry is wired for error monitoring.
- Deploy guard script validates core production health.
- Backups and cleanup tasks are scheduled through Celery Beat.

## Important Data Retention Rules

Current media retention policy:

- Raw uploaded/imported source videos: retained for 45 days, then removed from durable storage when safe.
- Exported files: retained for 30 days, then deleted unless attached to active publish jobs.
- Content Queue / AI CMO draft media:
  - ready or unused draft media: retained for 30 days.
  - rejected draft media: retained for 14 days.
  - approved, scheduled, or posted content is retained.
  - database rows are kept for history after media cleanup.

The retention jobs run through Celery Beat.

## Recent Storage Fixes

The app hit Backblaze daily download bandwidth limits, which caused B2 to return `403 Forbidden` for object reads. That manifested as raw messages like:

```text
An error occurred (403) when calling the HeadObject operation: Forbidden
```

The storage layer now converts B2 403 read failures into a user-safe message:

```text
Source video is temporarily unavailable from storage. Try again after the storage download limit resets.
```

Workers persist the safe message instead of raw provider exceptions, and API schemas sanitize older saved raw messages before returning them to the frontend.

## Content Queue Draft Asset Tracking

Generated carousel drafts used to store slide URLs only. That was not enough for safe cleanup because signed URLs expire and are brittle to parse.

The current design stores exact B2 keys on `content_queue` rows:

- `slide_keys_json`
- `zip_key`
- `preview_key`
- `asset_cleanup_at`
- `assets_deleted_at`

Cleanup deletes only tracked keys and only when the item is eligible. It skips any key referenced by saved carousel exports.

## Common Validation Commands

Backend compile:

```bash
PYTHONPYCACHEPREFIX=/tmp/pycache_clipbandit python3 -m compileall backend/app
```

Frontend build:

```bash
cd frontend && npm run build
```

Whitespace check:

```bash
git diff --check
```

Migration status locally:

```bash
cd backend && alembic heads
```

Migration status on VPS:

```bash
ssh -i ~/.ssh/iqbandit_deploy root@147.93.6.2 "cd /opt/clipbandit && docker compose exec -T postgres psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -tAc 'select version_num from alembic_version;'"
```

Manual cleanup dry-runs on VPS:

```bash
ssh -i ~/.ssh/iqbandit_deploy root@147.93.6.2 "cd /opt/clipbandit && docker compose exec -T backend python3 - <<'PY'
from app.worker.tasks.cleanup import sweep_export_retention_impl, sweep_content_queue_asset_retention_impl
print(sweep_export_retention_impl(dry_run=True))
print(sweep_content_queue_asset_retention_impl(dry_run=True))
PY"
```

Manual analytics task:

```bash
ssh -i ~/.ssh/iqbandit_deploy root@147.93.6.2 "cd /opt/clipbandit && docker compose exec -T backend python3 - <<'PY'
from app.worker.tasks.analytics import refresh_post_analytics
print(refresh_post_analytics.run(batch_size=50, lookback_days=30))
PY"
```

## Security Rules

- Do not print or commit `.env` values.
- Do not expose OAuth tokens, B2 keys, Stripe keys, JWT secrets, or private keys in logs or docs.
- API keys are hash-only in the database; plaintext key values should only appear once at creation time.
- Connected social tokens are encrypted with the app crypto service.
- Provider errors shown to users should be sanitized and action-oriented.

## Current Engineering Priorities

High priority:

1. Keep upload/import/transcribe/score stable under B2 limits.
2. Keep retention jobs conservative and auditable.
3. Make workflow recovery user-friendly when official APIs cannot provide reusable source video files.
4. Keep social publishing errors non-technical and actionable.
5. Avoid duplicate queue work for uploads/imports/workflows.

Medium priority:

1. Move thumbnail storage from local cache to a more durable/cache-aware design if launch needs consistent thumbnails across deploys.
2. Add better storage usage visibility per user and plan.
3. Continue improving Content Queue scheduling and carousel publishing UX.
4. Add more provider analytics once permissions are approved and tokens are stable.

## Notes for Future Engineers

This codebase has a lot of production-driven patches. Before changing large systems, inspect the current path and preserve working behavior. Many systems are intentionally additive because production stability matters more than large rewrites.

Always start with:

```bash
git status --short
git diff --name-only
git log --oneline -5
```

Then validate the exact area you are changing, stage only intended files, commit with clear context, push, and deploy the exact SHA.
