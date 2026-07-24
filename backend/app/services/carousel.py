from __future__ import annotations

import base64
import json
import logging
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import httpx

from app.config import settings
from app.schemas.carousel import CarouselConfig
from app.services.object_storage import object_storage_client

logger = logging.getLogger(__name__)

CAROUSEL_RENDERER_DIR = Path(__file__).resolve().parent / "carousel_renderer"
CAROUSEL_WORKSPACE_ROOT = Path("/tmp/clipbandit-carousels")
JSON_CODE_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL)
SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]")

CAROUSEL_TEMPLATES = [
    {
        "id": "viral-dark",
        "name": "Viral Dark",
        "renderer": "render_viral_with_green.py",
        "description": "Black background, teal glow, Inter Black — high-engagement format",
        "preview_url": "/template-previews/viral-dark.png",
        "default_slides": 6,
    },
    {
        "id": "navy-clean",
        "name": "Navy Clean",
        "renderer": "render.py",
        "description": "Dark navy, structured layout, good for educational content",
        "preview_url": "/template-previews/navy-clean.png",
        "default_slides": 6,
    },
    {
        "id": "editorial-sun",
        "name": "Editorial Sun",
        "renderer": "render_modern.py",
        "description": "Warm cream, oversized serif-style headlines, and magazine-inspired structure",
        "preview_url": "/template-previews/editorial-sun.png",
        "default_slides": 6,
    },
    {
        "id": "paper-notes",
        "name": "Paper Notes",
        "renderer": "render_modern.py",
        "description": "Torn-paper layers, marker accents, and a tactile creator-workbook feel",
        "preview_url": "/template-previews/paper-notes.png",
        "default_slides": 6,
    },
    {
        "id": "signal-brutalist",
        "name": "Signal Brutalist",
        "renderer": "render_modern.py",
        "description": "Electric yellow, hard borders, and bold type built to stop the scroll",
        "preview_url": "/template-previews/signal-brutalist.png",
        "default_slides": 6,
    },
    {
        "id": "data-mint",
        "name": "Data Mint",
        "renderer": "render_modern.py",
        "description": "Fresh mint cards, visual numbering, and polished layouts for tips and data",
        "preview_url": "/template-previews/data-mint.png",
        "default_slides": 6,
    },
    {
        "id": "aurora-glass",
        "name": "Aurora Glass",
        "renderer": "render_modern.py",
        "description": "Soft gradients and translucent cards for premium micro-learning content",
        "preview_url": "/template-previews/aurora-glass.png",
        "default_slides": 6,
    },
    {
        "id": "retro-future",
        "name": "Retro Future",
        "renderer": "render_modern.py",
        "description": "Saturated space-age graphics and playful type for trend-led creator posts",
        "preview_url": "/template-previews/retro-future.png",
        "default_slides": 6,
    },
    {
        "id": "luxe-mono",
        "name": "Luxe Mono",
        "renderer": "render_modern.py",
        "description": "High-contrast monochrome with restrained gold details for authority content",
        "preview_url": "/template-previews/luxe-mono.png",
        "default_slides": 6,
    },
    {
        "id": "case-study",
        "name": "Case Study",
        "renderer": "render_modern.py",
        "description": "Outcome-led cards and proof markers for problem, solution, and result stories",
        "preview_url": "/template-previews/case-study.png",
        "default_slides": 6,
    },
]
_TEMPLATE_BY_ID = {template["id"]: template for template in CAROUSEL_TEMPLATES}


class CarouselError(Exception):
    pass


def _is_placeholder(value: str | None) -> bool:
    if value is None:
        return True
    normalized = value.strip().lower()
    return normalized == "" or normalized == "placeholder"


def _configured(value: str | None) -> bool:
    return not _is_placeholder(value)


def list_templates() -> list[dict]:
    return [dict(item) for item in CAROUSEL_TEMPLATES]


def get_template_or_raise(template_id: str) -> dict:
    template = _TEMPLATE_BY_ID.get(template_id)
    if not template:
        raise CarouselError(f"Unknown carousel template: {template_id}")
    return template


def _clip_text(value: str | None, *, max_len: int = 120) -> str | None:
    if value is None:
        return None
    text = " ".join(value.strip().split())
    if not text:
        return None
    return text[:max_len].rstrip()


def _normalize_config(config: dict, template: dict) -> dict:
    parsed = CarouselConfig.model_validate(config)
    slides = list(parsed.slides)
    if len(slides) < 5:
        raise CarouselError("Generated carousel must include at least 5 slides")
    slides = slides[:12]

    normalized_slides: list[dict] = []
    default_cta = 'Comment *"GUIDE"* and I\'ll DM you the link'
    final_index = len(slides) - 1
    for index, slide in enumerate(slides):
        data = slide.model_dump(exclude_none=True)
        if index == 0:
            data["type"] = "hook"
        elif index == final_index:
            data["type"] = "cta"
        else:
            data["type"] = "body"

        for key in ("title", "text", "subtitle", "body", "cta_action", "button_text", "annotation", "label", "subheading"):
            if key in data:
                data[key] = _clip_text(data.get(key))
                if data[key] is None:
                    data.pop(key, None)

        bullets = data.get("bullets")
        if isinstance(bullets, list):
            cleaned = [_clip_text(str(item)) for item in bullets]
            data["bullets"] = [item for item in cleaned if item]
            if not data["bullets"]:
                data.pop("bullets", None)

        if "glow" in data:
            data["glow"] = _clip_text(str(data["glow"]), max_len=40)
        if "image" in data:
            data["image"] = _clip_text(str(data["image"]), max_len=200)
        if index == final_index:
            cta_action = _clip_text(str(data.get("cta_action") or ""), max_len=120)
            if not cta_action:
                data["cta_action"] = default_cta
            elif "comment" not in cta_action.lower() or "dm" not in cta_action.lower():
                data["cta_action"] = default_cta
        normalized_slides.append(data)

    output = parsed.model_dump()
    output["renderer"] = template["renderer"]
    output["template_id"] = template["id"]
    output["slides"] = normalized_slides
    return output


def _extract_json_payload(text: str) -> dict:
    content = (text or "").strip()
    if not content:
        raise CarouselError("AI returned empty response")
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = JSON_CODE_BLOCK_RE.search(content)
    if match:
        candidate = match.group(1).strip()
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError as exc:
            raise CarouselError("AI returned invalid JSON") from exc
    raise CarouselError("AI returned invalid JSON")


def _carousel_system_prompt() -> str:
    return (
        "You are a viral social media carousel copywriter. "
        "Given a topic, write a 6-slide Instagram carousel in valid JSON.\n"
        "Output schema:\n"
        "{\n"
        '  "title": "string",\n'
        '  "profile": {"display_name":"string","handle":"string"},\n'
        '  "slides": [\n'
        '    {"type":"hook|body|cta","title":"string?","text":"string?","subtitle":"string?","bullets":["string?"],"cta_action":"string?","glow":"corners|left|right|spread|top-right","image":"string?"}\n'
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        "- Exactly 6 slides.\n"
        "- Slide 1 is hook.\n"
        "- Slides 2-5 are body.\n"
        "- Slide 6 is cta.\n"
        '- Slide 6 includes cta_action: Comment *"[KEYWORD]"* and I\\\'ll DM you the link\n'
        "- Use *asterisks* around 1-3 key words per slide for accent color.\n"
        "- Keep every text field under 120 characters.\n"
        "- Return ONLY valid JSON with no explanation."
    )


def _build_topic_prompt(topic: str, *, display_name: str, handle: str) -> str:
    return f'Topic: {topic}\nProfile: {{ "display_name": "{display_name}", "handle": "{handle}" }}'


def _generate_with_claude(topic: str, *, display_name: str, handle: str) -> dict:
    if not _configured(settings.anthropic_api_key):
        raise CarouselError("Anthropic API key is not configured")

    payload = {
        "model": settings.carousel_claude_model,
        "max_tokens": 2400,
        "temperature": 0.7,
        "system": _carousel_system_prompt(),
        "messages": [{"role": "user", "content": _build_topic_prompt(topic, display_name=display_name, handle=handle)}],
    }
    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    with httpx.Client(timeout=max(30, settings.deepseek_timeout_sec)) as client:
        response = client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
    if response.status_code >= 400:
        raise CarouselError(f"Claude generation failed with HTTP {response.status_code}")
    data = response.json()
    content_items = data.get("content") if isinstance(data, dict) else None
    if not isinstance(content_items, list):
        raise CarouselError("Claude returned malformed response")
    text_parts: list[str] = []
    for item in content_items:
        if isinstance(item, dict) and item.get("type") == "text":
            text = item.get("text")
            if isinstance(text, str):
                text_parts.append(text)
    return _extract_json_payload("\n".join(text_parts).strip())


def _generate_with_deepseek(topic: str, *, display_name: str, handle: str) -> dict:
    if not _configured(settings.deepseek_api_key):
        raise CarouselError("DeepSeek API key is not configured")

    payload = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": _carousel_system_prompt()},
            {"role": "user", "content": _build_topic_prompt(topic, display_name=display_name, handle=handle)},
        ],
        "temperature": 0.7,
    }
    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }
    endpoint = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"

    with httpx.Client(timeout=max(30, settings.deepseek_timeout_sec)) as client:
        response = client.post(endpoint, headers=headers, json=payload)
    if response.status_code >= 400:
        raise CarouselError(f"DeepSeek generation failed with HTTP {response.status_code}")

    data = response.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return _extract_json_payload(content)


def _profile_for_user(user) -> tuple[str, str]:
    email = (getattr(user, "email", "") or "").strip().lower()
    handle_base = re.sub(r"[^a-z0-9_]", "", email.split("@")[0]) or "postbandit"
    return "PostBandit Creator", f"@{handle_base}"


def generate_config(template_id: str, topic: str, user) -> tuple[dict, str]:
    template = get_template_or_raise(template_id)
    display_name, handle = _profile_for_user(user)

    try:
        raw = _generate_with_claude(topic, display_name=display_name, handle=handle)
        return _normalize_config(raw, template), "claude"
    except Exception as claude_exc:
        logger.warning("[carousels] claude generate failed template=%s error=%s", template_id, claude_exc)

    raw = _generate_with_deepseek(topic, display_name=display_name, handle=handle)
    return _normalize_config(raw, template), "deepseek"


def _decode_reference_images(reference_images: dict[str, str] | None, reference_dir: Path) -> None:
    if not reference_images:
        return
    max_bytes = max(1, int(settings.carousel_reference_image_max_mb)) * 1024 * 1024
    total_written = 0
    for raw_name, raw_b64 in reference_images.items():
        if not isinstance(raw_name, str) or not isinstance(raw_b64, str):
            continue
        filename = SAFE_FILENAME_RE.sub("_", Path(raw_name).name)[:120]
        if not filename:
            continue
        data = raw_b64
        if data.startswith("data:") and "," in data:
            data = data.split(",", 1)[1]
        try:
            blob = base64.b64decode(data, validate=True)
        except Exception as exc:
            raise CarouselError(f"Invalid base64 image for {raw_name}") from exc
        total_written += len(blob)
        if total_written > max_bytes:
            raise CarouselError(f"Reference images exceed {settings.carousel_reference_image_max_mb}MB limit")
        (reference_dir / filename).write_bytes(blob)


def render_config(
    *,
    template_id: str,
    config: dict,
    user_id: uuid.UUID,
    reference_images: dict[str, str] | None = None,
) -> dict:
    template = get_template_or_raise(template_id)
    script_path = CAROUSEL_RENDERER_DIR / template["renderer"]
    if not script_path.exists():
        raise CarouselError(f"Renderer script missing: {template['renderer']}")

    workspace_id = uuid.uuid4().hex
    workspace_dir = CAROUSEL_WORKSPACE_ROOT / workspace_id
    reference_dir = workspace_dir / "reference"
    CAROUSEL_WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    reference_dir.mkdir(parents=True, exist_ok=True)

    normalized_config = _normalize_config(config, template)
    (workspace_dir / "config.json").write_text(json.dumps(normalized_config, indent=2), encoding="utf-8")
    _decode_reference_images(reference_images, reference_dir)

    try:
        result = subprocess.run(
            ["python3", str(script_path), str(workspace_dir)],
            cwd=str(CAROUSEL_RENDERER_DIR),
            capture_output=True,
            text=True,
            timeout=max(30, int(settings.carousel_render_timeout_seconds)),
            check=False,
        )
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or "Unknown renderer failure").strip()
            raise CarouselError(f"Carousel render failed: {stderr[:500]}")

        slide_paths = sorted(
            workspace_dir.glob("slide_*.png"),
            key=lambda p: int(p.stem.split("_")[1]) if "_" in p.stem and p.stem.split("_")[1].isdigit() else 9999,
        )
        if not slide_paths:
            raise CarouselError("Carousel renderer produced no slides")

        slides: list[dict] = []
        slide_keys: list[str] = []
        for idx, slide_path in enumerate(slide_paths, start=1):
            key = f"carousels/{user_id}/{workspace_id}/slides/{slide_path.name}"
            object_storage_client.upload_file(str(slide_path), key)
            url = object_storage_client.get_presigned_download_url(key)
            slide_keys.append(key)
            slides.append({"index": idx, "key": key, "url": url})

        zip_path = workspace_dir / "carousel.zip"
        with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
            for slide_path in slide_paths:
                archive.write(slide_path, arcname=slide_path.name)

        zip_key = f"carousels/{user_id}/{workspace_id}/carousel.zip"
        object_storage_client.upload_file(str(zip_path), zip_key)
        zip_url = object_storage_client.get_presigned_download_url(zip_key)

        return {
            "workspace_id": workspace_id,
            "config": normalized_config,
            "slides": slides,
            "slide_keys": slide_keys,
            "zip": {"key": zip_key, "url": zip_url},
            "preview_key": slide_keys[0],
        }
    finally:
        shutil.rmtree(workspace_dir, ignore_errors=True)
