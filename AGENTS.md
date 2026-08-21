# AGENTS.md

PostBandit — production software with real users, live Stripe subscriptions, and running
video processing jobs. Read this before doing anything.

## Roles

**You are a BUILDER agent unless the human explicitly tells you at the start of the
session that you are the DEPLOY agent.** Assume builder.

**Builder agents:**
- Write code, commit, push to `<name>/<task>` branches
- NEVER merge to `main`
- NEVER SSH to the VPS
- NEVER deploy, restart containers, or run migrations
- Your job ends at "pushed a branch"

**The deploy agent** (one session, designated explicitly) merges to `main`, deploys, and
is the only thing with VPS access.

If you are unsure which you are, you are a builder.

## Git rules — all agents

- Push immediately after committing: `git push origin HEAD:refs/heads/<name>/<task>`
- Never leave work unpushed
- Never force-push, `git clean`, `git reset --hard`, or rewrite pushed history
- If `git status` shows changes you didn't make, STOP and report — another agent may be
  working in this repo
- Never commit `.env.local`, secrets, or credentials

## Scope

- Touch only files needed for the stated task
- If an unrelated file needs changing, STOP and ask
- Investigation-first: for anything non-trivial, report findings and STOP before
  implementing. Do not silently adapt when reality conflicts with the task spec — say so
  and propose the alternative.

## Stack

- Frontend: Next.js 14.2.15, App Router, TypeScript, Tailwind — `frontend/`, app at
  `frontend/src/app`
- Backend: FastAPI (Python 3.11), Celery + Redis, PostgreSQL 15 — `backend/`
- Video: FFmpeg, faster-whisper, yt-dlp
- Deploy: Docker Compose on Contabo VPS, nginx, manual deployment
- Blog: MDX in `frontend/content/blog/`, `gray-matter` + `next-mdx-remote/rsc`

## Known constraints

- **The frontend builds at container startup**, not at image build time. Takes ~5
  minutes. Healthcheck `start_period` is `300s`. Do not lower it.
- `docker-compose.yml` bind-mounts `./frontend:/app` with anonymous volumes for
  `node_modules` and `.next` — the container serves VPS disk contents, not image contents
- `next/font/google` fetches at build time; the build needs network access
- `ImageResponse` (OG images) cannot use Tailwind classes or `next/font` — inline styles
  and system fonts only
- `localhost` inside a container is that container, not the VPS host
- `docker compose up -d` (not `restart`) is required to pick up env changes
- YouTube server-side download is blocked from the datacenter IP (PO Token requirement)

## Production safety — never override

- Never `docker compose down`, `system prune`, or `volume prune`
- Never delete `data/` or any `.env*` file on the VPS
- Never commit, branch, or stash on the VPS
- Never run Alembic migrations unless explicitly instructed
- Never touch a service the task didn't name

## Product accuracy

Blog and marketing content must not claim unshipped features. Currently NOT shipped:
auto speaker tracking/reframe, Zoom integration. Plan limits: Repurposer $9 (2 GiB,
3 platforms), Creator $18 (5 GiB, 5 platforms), Pro $49, Agency $99. Verify against
`backend/app/billing/plans.py` before writing any number publicly.
