# PostBandit

PostBandit takes long-form videos (podcasts, sermons, YouTube videos) and automatically generates short viral clips with captions. Built for churches and solo creators who want OpusClip-quality output at a fraction of the cost.

## Prerequisites

- Docker & Docker Compose
- Node.js 18+
- Python 3.11+

## Setup

```bash
git clone <repo>
cd clipbandit
cp .env.example .env
docker-compose up --build
```

## Access

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3001 |
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Health Check | http://localhost:8000/health |

Default login: `admin@clipbandit.com` / `changeme123`

## Public Entry + Signup

- Root path `/` is the public landing page.
- Primary CTA routes to `/signup`.
- `/signup` supports:
  - Google OAuth signup/signin via NextAuth.
  - Email/password signup via `POST /api/auth/signup`.
- Successful email signup redirects to `/login` with a success message.

## Google OAuth Login Config

To enable Google sign-in on `/login` and `/signup`:

- Set `GOOGLE_CLIENT_ID`
- Set `GOOGLE_CLIENT_SECRET`

Required Google Console OAuth redirect URIs:

- `https://postbandit.com/api/auth/callback/google`
- `http://localhost:3001/api/auth/callback/google`

Notes:

- Google login exchanges the Google `id_token` for a backend JWT via `/api/auth/google/login`.
- New Google users are auto-created as `starter` tier.
- Existing email/password login stays unchanged.

## Email/Password Signup API

Backend endpoint:

- `POST /api/auth/signup`
- Request body: `{ "email": "user@example.com", "password": "min-8-chars" }`
- Responses:
  - `201` account created
  - `409` email already exists
  - `400/422` validation error

## YouTube OAuth Provider Config

To enable real YouTube social connection flow:

- Set `YOUTUBE_CLIENT_ID`
- Set `YOUTUBE_CLIENT_SECRET`
- Set `SOCIAL_TOKEN_ENCRYPTION_KEY` (required for encrypted token storage)
- Set `BACKEND_PUBLIC_URL` to your externally reachable backend URL

Google Cloud OAuth redirect URI must match:

- `{BACKEND_PUBLIC_URL}/api/social/youtube/callback`

If any required field is missing/invalid, `/api/social/providers` returns YouTube as `provider_not_configured` with missing-field diagnostics.

## YouTube Import (Single + Playlist + Fallback)

Server-side YouTube import supports:

- Single links (`watch`, `youtu.be`, `shorts`)
- Playlist links (`list=...`)

Import behavior is honest by design:

- Public/easy videos use server download (`yt-dlp`)
- Blocked videos can still be kept as embed metadata
- Users can upload replacement media manually when server download is blocked
- Blocked single-video rows also support a one-time local-helper session (`Use Local Helper`) that runs `yt-dlp` on the user machine and uploads back to the same row
- Repeated blocked single-video links are short-circuited for 24 hours into recovery mode (no repeated failing server attempt)
- Retry is disabled for non-retryable blocked codes (`YT_SIGNIN_REQUIRED`, `YT_BOT_VERIFICATION`, `YT_PO_TOKEN_REQUIRED`, `YT_NO_FORMATS`)

Local helper notes:

- Requires local `yt-dlp` and `curl`
- Helper sessions are one-time and short-lived (default 15 minutes)
- UI now provides a `Download helper launcher` flow first (no token copy/paste required)
- CLI copy/paste remains available as a fallback
- See `docs/local-import-helper.md` for full usage

YouTube import env settings:

- `YOUTUBE_IMPORT_MAX_PLAYLIST_ITEMS` (default `50`)
- `YOUTUBE_IMPORT_CONCURRENCY` (default `3`)
- `YTDLP_TIMEOUT_SECONDS` (default `60`)
- `ENABLE_YOUTUBE_API_METADATA` (default `false`)
- `YOUTUBE_API_KEY` (optional metadata enrichment only)
- `YOUTUBE_LOCAL_HELPER_TTL_MINUTES` (default `15`)
- `YOUTUBE_IMPORT_ADMISSION_MODE` (`off|warn|enforce`, default `warn`)
- `YOUTUBE_IMPORT_MIN_FREE_DISK_GB` (default `20`)
- `YOUTUBE_IMPORT_MAX_INGEST_QUEUE_DEPTH` (default `100`)
- `YOUTUBE_IMPORT_MAX_ACTIVE_PER_USER` (default `3`)
- `YOUTUBE_IMPORT_MAX_ACTIVE_GLOBAL` (default `12`)
- `YOUTUBE_IMPORT_RATE_LIMIT_PER_HOUR` (default `25`)
- `YOUTUBE_HELPER_SESSION_RATE_LIMIT_PER_HOUR` (default `20`)
- `WORKSPACE_CLEANUP_ENABLED` (default `true`)
- `WORKSPACE_CLEANUP_DRY_RUN` (default `true`; set `false` to enable deletion)
- `WORKSPACE_CLEANUP_RETENTION_HOURS` (default `24`)
- `WORKSPACE_CLEANUP_ORPHAN_GRACE_MINUTES` (default `45`)

## Facebook Pages Provider Config

To enable real Facebook Pages connection + publishing:

- Set `FACEBOOK_APP_ID` and `FACEBOOK_APP_SECRET`
  - or use shared fallback `META_APP_ID` and `META_APP_SECRET`
- Set `SOCIAL_TOKEN_ENCRYPTION_KEY` (required for encrypted token storage)
- Set `BACKEND_PUBLIC_URL` to your externally reachable backend URL
- Optional: set `META_GRAPH_API_VERSION` (default `v21.0`)

Facebook callback URI must match:

- `{BACKEND_PUBLIC_URL}/api/social/facebook/callback`

Notes:

- Facebook integration targets **Pages only** (not personal profiles).
- One OAuth connection may create multiple connected destinations (one per Page).

## Instagram OAuth Provider Config (`instagram_business_basic`)

To enable real Instagram professional-account connection + publishing:

- Set `INSTAGRAM_APP_ID` and `INSTAGRAM_APP_SECRET`
  - or use shared fallback `META_APP_ID` and `META_APP_SECRET`
- Set `SOCIAL_TOKEN_ENCRYPTION_KEY` (required for encrypted token storage)
- Set `BACKEND_PUBLIC_URL` to your externally reachable backend URL
- Ensure your Meta app has **Instagram Login** enabled for this provider flow

Instagram callback URI must match:

- `{BACKEND_PUBLIC_URL}/api/social/instagram/callback`

Notes:

- Instagram provider now uses the Instagram Login model directly (not Facebook `/me/accounts` Page discovery).
- Instagram integration targets **Business/Creator** accounts only.
- Instagram and Facebook are separate provider paths: Facebook handles Pages; Instagram handles Instagram professional account connect/publish.
- If OAuth succeeds but no professional Instagram account is returned, PostBandit fails honestly and asks for reconnect with the correct account.

## Threads Provider Config

To enable real Threads connection + publishing:

- Set `THREADS_APP_ID` and `THREADS_APP_SECRET`
  - or use shared fallback `META_APP_ID` and `META_APP_SECRET`
- Set `SOCIAL_TOKEN_ENCRYPTION_KEY` (required for encrypted token storage)
- Set `BACKEND_PUBLIC_URL` to your externally reachable backend URL
- Optional: set `THREADS_GRAPH_API_VERSION` (default `v1.0`)

Threads callback URI must match:

- `{BACKEND_PUBLIC_URL}/api/social/threads/callback`

Notes:

- Threads integration is real for connect + text posting.
- Threads video posting is enabled through the same publish job flow when export media is available.
- OAuth callback performs short-lived code exchange followed by long-lived token exchange; publish attempts refresh long-lived tokens near expiry.
- If Threads app permissions/tester/review state block publishing, jobs return honest actionable status (for example `waiting_user_action`) instead of fake success.

## TikTok Provider Config

To enable real TikTok connection + publishing:

- Set `TIKTOK_CLIENT_KEY`
- Set `TIKTOK_CLIENT_SECRET`
- Set `SOCIAL_TOKEN_ENCRYPTION_KEY` (required for encrypted token storage)
- Set `BACKEND_PUBLIC_URL` to your externally reachable backend URL
- Optional poll tuning:
  - `TIKTOK_PUBLISH_POLL_INTERVAL_SECONDS` (default `5`)
  - `TIKTOK_PUBLISH_POLL_TIMEOUT_SECONDS` (default `720`)

TikTok callback URI must match:

- `{BACKEND_PUBLIC_URL}/api/social/tiktok/callback`

Notes:

- TikTok uses Login Kit for Web OAuth and Content Posting APIs.
- Provider diagnostics include callback URL, required scopes, mode support, and readiness.
- Publish flow attempts direct post first; if direct post is blocked and upload scope is available, it falls back to inbox upload.
- `SEND_TO_USER_INBOX` is treated as `waiting_user_action` (user must complete posting in TikTok).
- TikTok privacy is required and must match creator options returned by TikTok (`privacy_level_options`).

## X (Twitter) OAuth Provider Config

To enable real X connection + text posting flow:

- Set `X_CLIENT_ID`
- Set `X_CLIENT_SECRET`
- Set `SOCIAL_TOKEN_ENCRYPTION_KEY` (required for encrypted token storage)
- Set `BACKEND_PUBLIC_URL` to your externally reachable backend URL

X developer app callback URI must match:

- `{BACKEND_PUBLIC_URL}/api/social/x/callback`

Notes:

- X posting is text-only in this pass (media/video upload is deferred).
- If X does not return a usable refresh token, connection/publish fails honestly and requires reconnect.

## 10-Prompt Build Plan

1. **Foundation** — Docker, DB schema, auth, skeleton UI (this prompt)
2. **Video Ingestion** — Upload endpoint, yt-dlp download, R2 storage
3. **Transcription** — faster-whisper integration, word-level timestamps
4. **Clip Scoring** — AI scoring engine, hook/energy detection
5. **Clip Management** — Clip browser UI, score display, filtering
6. **Caption Engine** — FFmpeg burn-in, SRT export, caption styles
7. **Export Pipeline** — Render queue, aspect ratio cropping, download URLs
8. **Dashboard & Analytics** — Stats, usage tracking, tier limits
9. **Payments** — Stripe integration, tier upgrades, usage billing
10. **Production Hardening** — Error handling, monitoring, rate limiting, deploy
