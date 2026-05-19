#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib import request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download a blocked YouTube video locally and upload it to PostBandit using "
            "a one-time helper session."
        )
    )
    parser.add_argument("--source-url", required=True, help="Original YouTube URL")
    parser.add_argument("--upload-url", required=True, help="Presigned upload URL from PostBandit")
    parser.add_argument("--complete-url", required=True, help="Completion endpoint URL from PostBandit")
    parser.add_argument("--session-token", required=True, help="One-time helper session token")
    parser.add_argument("--upload-key", required=True, help="Storage key from helper session")
    parser.add_argument(
        "--upload-fields-json",
        default="{}",
        help="JSON object of upload form fields returned by helper session",
    )
    parser.add_argument(
        "--use-local",
        default="false",
        choices=("true", "false"),
        help="Whether upload target is local-storage adapter",
    )
    parser.add_argument(
        "--yt-dlp-bin",
        default="yt-dlp",
        help="yt-dlp executable (default: yt-dlp)",
    )
    return parser.parse_args()


def require_binary(name: str) -> None:
    if shutil.which(name):
        return
    raise RuntimeError(f"Required binary not found: {name}")


def parse_upload_fields(raw_json: str) -> dict[str, str]:
    try:
        parsed = json.loads(raw_json or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError("Invalid --upload-fields-json payload") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("--upload-fields-json must be a JSON object")
    return {str(key): str(value) for key, value in parsed.items()}


def run_download(*, ytdlp_bin: str, source_url: str, output_template: str) -> None:
    cmd = [
        ytdlp_bin,
        "--no-playlist",
        "--merge-output-format",
        "mp4",
        "-f",
        "bestvideo[height<=1080]+bestaudio/best[height<=1080]/bestvideo+bestaudio/best",
        "-o",
        output_template,
        source_url,
    ]
    print("[local-helper] Downloading on local machine...")
    subprocess.run(cmd, check=True)


def find_downloaded_video(workdir: Path) -> Path:
    candidates = sorted(path for path in workdir.iterdir() if path.is_file())
    if not candidates:
        raise RuntimeError("No downloaded file was produced by yt-dlp")
    mp4_candidates = [path for path in candidates if path.suffix.lower() == ".mp4"]
    if mp4_candidates:
        return mp4_candidates[0]
    return max(candidates, key=lambda item: item.stat().st_size)


def run_upload_with_curl(
    *,
    upload_url: str,
    upload_key: str,
    upload_fields: dict[str, str],
    use_local: bool,
    file_path: Path,
) -> None:
    cmd = ["curl", "-sS", "-f", "-X", "POST", upload_url]
    if use_local:
        cmd.extend(["-F", f"key={upload_key}"])
    else:
        for field, value in upload_fields.items():
            cmd.extend(["-F", f"{field}={value}"])
        if "key" not in upload_fields:
            cmd.extend(["-F", f"key={upload_key}"])
    cmd.extend(["-F", f"file=@{file_path}"])

    print("[local-helper] Uploading to PostBandit...")
    subprocess.run(cmd, check=True)


def call_complete(
    *,
    complete_url: str,
    session_token: str,
    upload_key: str,
    file_path: Path,
) -> dict[str, Any]:
    payload = {
        "helper_session_token": session_token,
        "upload_key": upload_key,
        "filename": file_path.name,
        "content_type": mimetypes.guess_type(file_path.name)[0] or "video/mp4",
        "size_bytes": file_path.stat().st_size,
    }

    req = request.Request(
        complete_url,
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with request.urlopen(req, timeout=60) as response:
        raw_body = response.read().decode("utf-8")
    try:
        return json.loads(raw_body)
    except json.JSONDecodeError:
        return {"raw": raw_body}


def main() -> int:
    args = parse_args()
    upload_fields = parse_upload_fields(args.upload_fields_json)

    try:
        require_binary(args.yt_dlp_bin)
        require_binary("curl")
    except RuntimeError as exc:
        print(f"[local-helper] {exc}", file=sys.stderr)
        return 2

    use_local = args.use_local.lower() == "true"

    with tempfile.TemporaryDirectory(prefix="postbandit-local-helper-") as tmp:
        tmp_dir = Path(tmp)
        output_template = str(tmp_dir / "download.%(ext)s")

        try:
            run_download(ytdlp_bin=args.yt_dlp_bin, source_url=args.source_url, output_template=output_template)
        except subprocess.CalledProcessError as exc:
            print(
                "[local-helper] Local download failed. This source may still require sign-in on your machine.",
                file=sys.stderr,
            )
            return exc.returncode or 3

        try:
            local_video = find_downloaded_video(tmp_dir)
        except RuntimeError as exc:
            print(f"[local-helper] {exc}", file=sys.stderr)
            return 3

        try:
            run_upload_with_curl(
                upload_url=args.upload_url,
                upload_key=args.upload_key,
                upload_fields=upload_fields,
                use_local=use_local,
                file_path=local_video,
            )
        except subprocess.CalledProcessError as exc:
            print(f"[local-helper] Upload failed with exit code {exc.returncode}", file=sys.stderr)
            return exc.returncode or 4

        try:
            result = call_complete(
                complete_url=args.complete_url,
                session_token=args.session_token,
                upload_key=args.upload_key,
                file_path=local_video,
            )
        except Exception as exc:
            print(f"[local-helper] Completion call failed: {exc}", file=sys.stderr)
            return 5

    print("[local-helper] Completed successfully.")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
