# PostBandit

AI-powered content workflow platform — import video, generate clips, publish everywhere.

[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Next.js 14](https://img.shields.io/badge/Next.js-14-000000?style=for-the-badge&logo=nextdotjs&logoColor=white)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Stripe](https://img.shields.io/badge/Stripe-635BFF?style=for-the-badge&logo=stripe&logoColor=white)](https://stripe.com/)

PostBandit is a production-oriented content operations platform for creators, teams, agencies, and brands. It turns source videos and social posts into publish-ready clips, carousel drafts, captions, platform-specific copy, scheduled publish jobs, and analytics.

## Product Screenshots

![Official API workflow builder](docs/screenshots/workflow-builder.png)

*Official API workflow setup for repurposing source posts from Instagram, YouTube, or Facebook into selected destination accounts.*

![Developer API dashboard](docs/screenshots/developer-api.png)

*Developer API dashboard with usage limits, API key management, and quick-start snippets for automation and agent workflows.*

![Carousel studio](docs/screenshots/carousel-studio.png)

*Carousel creation studio with template selection, editable slide structure, cached previews, and export-ready rendering.*

![Dashboard calendar and connections](docs/screenshots/dashboard-calendar.png)

*Main dashboard with connected account status, publishing calendar, platform filters, and schedule visibility.*

![Video URL import modal](docs/screenshots/video-url-import.png)

*Video import flow supporting direct uploads and URL imports from YouTube, Instagram, TikTok, Facebook, X, Twitch, and more.*

![Login screen](docs/screenshots/login.png)

*PostBandit authentication screen with product positioning around clipping, exporting, and multi-platform publishing.*

## Features

- Import videos by file upload or URL from YouTube, Instagram, TikTok, Facebook, X, Twitch, and other supported sources.
- Generate clips from long-form videos with transcription, scoring, captions, thumbnails, and export-ready assets.
- Build social repurpose workflows that detect source posts through official APIs and route them into publish destinations.
- Schedule and track publishing jobs across Instagram, YouTube, TikTok, Facebook, Threads, X, and LinkedIn-oriented workflows.
- Manage connected social accounts with platform logos, reconnect states, destination selection, and publishing readiness.
- Generate AI-assisted platform copy with reusable title, caption, description, hashtag, and per-platform override fields.
- Create carousel posts from AI CMO queue items, templates, source text, and rendered preview/export flows.
- Use the dashboard calendar to view scheduled posts, published history, failed jobs, and platform-specific status.
- Access a developer API for programmatic imports, exports, publishing workflows, and automation integrations.
- Handle billing and access tiers through Stripe-powered subscription infrastructure.

## Tech Stack

| Area | Stack |
|---|---|
| Frontend | Next.js 14 App Router, React 18, TypeScript, Tailwind CSS, NextAuth, Recharts |
| Backend | FastAPI, Python 3.11, SQLAlchemy, Alembic, Pydantic, httpx |
| AI/ML | faster-whisper, Claude Haiku, FFmpeg, yt-dlp, Pillow |
| Infrastructure | Docker Compose, Celery, Celery Beat, Redis, PostgreSQL 15, Backblaze B2, Sentry, Nginx, Contabo VPS |
| Payments | Stripe Checkout, Stripe Billing Portal, Stripe subscriptions, webhook idempotency |

## Local Development Setup

### Prerequisites

- Docker and Docker Compose
- Git
- Node.js 20+ if running the frontend outside Docker
- Python 3.11+ if running backend tools outside Docker

### Clone and configure

```bash
git clone https://github.com/TociNwaoha/clipbandit.git
cd clipbandit
cp .env.example .env
```

Fill in the required values in `.env`, including database credentials, Redis password, auth secrets, AI provider keys, storage credentials, Stripe values, and social OAuth app credentials as needed for the features you want to test.

### Run the stack

```bash
docker compose up -d --build
```

### Useful local URLs

| Service | URL |
|---|---|
| Frontend | http://localhost:3001 |
| Backend API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |

### Common commands

```bash
# View running services
docker compose ps

# Tail backend logs
docker compose logs -f backend

# Tail worker logs
docker compose logs -f worker

# Run backend migrations
docker compose exec backend alembic upgrade head

# Rebuild only the frontend
docker compose up -d --build frontend
```

## Architecture

PostBandit is built around two primary workflows: clip-first and publish-first.

### Clip-first workflow

A user uploads or imports a long-form video. The backend stores the source media, queues transcription through Celery, extracts word-level transcript data with faster-whisper, scores potential short-form moments, generates clip records, creates thumbnails, and renders final MP4 exports with FFmpeg. Those exports can then be downloaded, scheduled, or published to connected social accounts.

```text
Video upload/import → object storage → transcription → clip scoring → clip review → FFmpeg export → publish/download
```

### Publish-first workflow

A user connects source and destination accounts, then creates an official API workflow. PostBandit polls supported source platforms, detects new source posts, imports reusable media when the official API permits it, processes the content, creates or reuses exports, and creates platform-specific publish jobs. Publish jobs remain the source of truth for scheduling, retry state, published URLs, and analytics.

```text
Connected source account → source post detection → media import/recovery → export creation → publish jobs → calendar + analytics
```

The application is deployed as Docker Compose services: a Next.js frontend, FastAPI backend, PostgreSQL database, Redis broker, Celery workers, Celery Beat scheduler, and Nginx reverse proxy on a Contabo VPS. Durable media and backups are handled through Backblaze B2, while local volumes support thumbnails, temporary processing, and service runtime state.

## License

MIT
