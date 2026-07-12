import mimetypes
from pathlib import Path
from typing import Iterator

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from app.services.object_storage import object_storage_client

router = APIRouter()
CHUNK_SIZE_BYTES = 1024 * 1024


def _parse_range_header(range_header: str, file_size: int) -> tuple[int, int]:
    if file_size <= 0:
        raise ValueError("empty file")

    if not range_header.lower().startswith("bytes="):
        raise ValueError("unsupported range unit")

    requested_range = range_header.split("=", 1)[1].split(",", 1)[0].strip()
    if "-" not in requested_range:
        raise ValueError("malformed range")

    start_text, end_text = requested_range.split("-", 1)
    if not start_text and not end_text:
        raise ValueError("empty range")

    if not start_text:
        suffix_length = int(end_text)
        if suffix_length <= 0:
            raise ValueError("invalid suffix length")
        start = max(file_size - suffix_length, 0)
        end = file_size - 1
    else:
        start = int(start_text)
        if start < 0:
            raise ValueError("negative start")
        end = int(end_text) if end_text else file_size - 1

    if start >= file_size:
        raise IndexError("range start beyond file size")
    if end < start:
        raise ValueError("range end before start")

    end = min(end, file_size - 1)
    return start, end


def _iter_file_range(file_path: Path, start: int, end: int) -> Iterator[bytes]:
    remaining = (end - start) + 1
    with file_path.open("rb") as file_obj:
        file_obj.seek(start)
        while remaining > 0:
            chunk = file_obj.read(min(CHUNK_SIZE_BYTES, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


@router.post("/storage/local-upload")
async def local_upload(
    key: str = Form(...),
    file: UploadFile = File(...),
):
    await file.close()
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Local upload is disabled. Permanent uploads must use Backblaze B2.",
    )


@router.api_route("/storage/local/{key:path}", methods=["GET", "HEAD"])
async def local_download(key: str, request: Request):
    try:
        file_path = object_storage_client.local_fallback_path(key)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    file_size = file_path.stat().st_size
    guessed_type, _ = mimetypes.guess_type(str(file_path))
    media_type = guessed_type or "application/octet-stream"
    common_headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": media_type,
        "Content-Disposition": f'inline; filename="{file_path.name}"',
    }

    range_header = request.headers.get("range")
    if range_header:
        try:
            start, end = _parse_range_header(range_header, file_size)
        except (ValueError, IndexError):
            raise HTTPException(
                status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                detail="Requested range is not satisfiable",
                headers={"Content-Range": f"bytes */{file_size}"},
            )

        content_length = (end - start) + 1
        headers = {
            **common_headers,
            "Content-Length": str(content_length),
            "Content-Range": f"bytes {start}-{end}/{file_size}",
        }
        if request.method == "HEAD":
            return Response(status_code=status.HTTP_206_PARTIAL_CONTENT, headers=headers)
        return StreamingResponse(
            _iter_file_range(file_path, start, end),
            status_code=status.HTTP_206_PARTIAL_CONTENT,
            headers=headers,
            media_type=media_type,
        )

    full_headers = {
        **common_headers,
        "Content-Length": str(file_size),
    }
    if request.method == "HEAD":
        return Response(status_code=status.HTTP_200_OK, headers=full_headers)
    return StreamingResponse(
        _iter_file_range(file_path, 0, max(file_size - 1, 0)),
        status_code=status.HTTP_200_OK,
        headers=full_headers,
        media_type=media_type,
    )
