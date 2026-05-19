# Local Helper for Blocked YouTube Singles (V1)

When server-side YouTube import is blocked (`Blocked on server`), PostBandit can issue a short-lived helper session so you can download on your own machine and upload the file back to the same video row.

This flow does **not** bypass anti-bot/sign-in checks on the server.

## Prerequisites

- Python 3
- `yt-dlp` installed on your machine
- `curl` installed
- A blocked single YouTube import row in the app

## UI Flow (No-Copy/Paste First)

1. Open the blocked video row.
2. Click `Use Local Helper`.
3. Click `Download helper launcher`.
4. Run the downloaded launcher on your machine.
5. Return to the app and refresh the row.

Fallback path:

- Use `Copy CLI fallback` if you prefer the raw command.
- Run from your repo root where `tools/youtube_local_helper.py` exists.

On success, the same video row transitions to `transcribing` and continues normal processing.

## Session Contract

`POST /api/videos/local-helper/session` (auth required):

- Input: `video_id`
- Allowed only for blocked single YouTube rows owned by the current user
- Returns:
  - `helper_session_token` (one-time, short-lived)
  - `upload_url`
  - `upload_fields`
  - `upload_key`
  - `use_local`
  - `source_url`
  - `complete_url`
  - `expires_at`

`POST /api/videos/local-helper/complete` (token-based, no JWT):

- Input:
  - `helper_session_token`
  - `upload_key`
  - `filename`
  - `content_type`
  - `size_bytes`
- Validates token + upload key, then switches the existing row into manual-upload processing.
- If the token is expired/used, API returns a specific message telling the UI to create a new helper session.

## Security Notes

- Helper session tokens are one-time and expire quickly (default 15 minutes).
- No browser cookies are collected or stored by PostBandit.
- Completion requires a valid one-time helper token and matching upload key.
