from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.brand_profile import BrandProfile
from app.models.content_queue_item import ContentQueueItem
from app.schemas.carousel import CarouselConfig
from app.services.carousel import get_template_or_raise

logger = logging.getLogger(__name__)
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL)


class VideoCarouselGenerationError(Exception):
    pass


def _configured(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.strip().lower()
    return bool(normalized and normalized != "placeholder")


def _api_key() -> str:
    if _configured(settings.bandit_lm_api_key):
        return settings.bandit_lm_api_key
    if _configured(settings.deepseek_api_key):
        return settings.deepseek_api_key
    raise VideoCarouselGenerationError("DeepSeek is not configured")


def _compact(value: str | None, *, max_len: int) -> str:
    return " ".join((value or "").split())[:max_len].strip()


def _brand_voice_text(brand: BrandProfile | None) -> str:
    if not brand:
        return ""
    parts = [
        f"Display name: {brand.display_name}",
        f"Handle: {brand.handle}",
        f"Niche: {brand.niche}",
        f"Target audience: {brand.target_audience}",
        f"Tone: {brand.tone}",
    ]
    if brand.use_phrases:
        parts.append("Use phrases/styles: " + ", ".join(str(item) for item in brand.use_phrases if str(item).strip()))
    if brand.avoid_phrases:
        parts.append("Avoid: " + ", ".join(str(item) for item in brand.avoid_phrases if str(item).strip()))
    return "\n".join(part for part in parts if part.strip())


def build_video_carousel_prompt(*, transcript: str, brief: str, brand_voice: str) -> str:
    brand_section = f"\nBrand voice guidelines:\n{brand_voice}\n" if brand_voice else ""
    return f"""You are creating a social carousel from a video clip.

Video content brief:
{brief or "Not available. Use the transcript below."}

Transcript excerpt:
{transcript}
{brand_section}
Create a carousel that teaches or shares the key insights from this clip.
Choose the number of slides based on content depth: minimum 5, maximum 12.
Each slide should have one clear idea. Keep it punchy and grounded in the video.

Slide types:
- type "title": first slide only. A big hook that makes someone want to swipe.
- type "content": one key point per slide with a headline and 1-3 sentence body.
- type "quote": optional. A strong quote or paraphrased quote from the clip.
- type "cta": last slide only. One clear action.

Respond ONLY with valid JSON. No markdown fences. No preamble.

{{
  "carousel_title": "Short internal title",
  "slides": [
    {{
      "order": 1,
      "type": "title",
      "headline": "Big hook statement",
      "body": null
    }},
    {{
      "order": 2,
      "type": "content",
      "headline": "Key point headline",
      "body": "2-3 concise sentences expanding this point."
    }},
    {{
      "order": 3,
      "type": "quote",
      "headline": "Strong quote from the video",
      "body": null
    }},
    {{
      "order": 4,
      "type": "cta",
      "headline": "Follow for more",
      "body": null
    }}
  ]
}}

Rules:
- Return 5-12 slides.
- Headlines should be 4-8 words when possible.
- The first slide must be type "title".
- The final slide must be type "cta".
- Body text must be specific to the clip, not generic advice.
- Do not repeat the same point across slides.
- Use conversational language.
"""


def _extract_json_payload(raw: str) -> dict:
    content = (raw or "").strip()
    if not content:
        raise VideoCarouselGenerationError("AI returned an empty carousel response")
    if content.startswith("```"):
        match = _JSON_BLOCK_RE.search(content)
        if match:
            content = match.group(1).strip()
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise VideoCarouselGenerationError("AI returned invalid carousel JSON") from exc
    if not isinstance(parsed, dict):
        raise VideoCarouselGenerationError("AI returned an invalid carousel payload")
    return parsed


def parse_video_carousel_response(raw: str) -> dict:
    data = _extract_json_payload(raw)
    slides = data.get("slides")
    if not isinstance(slides, list):
        raise VideoCarouselGenerationError("AI response is missing slides")
    if not 5 <= len(slides) <= 12:
        raise VideoCarouselGenerationError("AI response must contain 5-12 slides")

    normalized: list[dict] = []
    for index, slide in enumerate(slides):
        if not isinstance(slide, dict):
            raise VideoCarouselGenerationError("AI returned an invalid slide")
        raw_type = str(slide.get("type") or "content").strip().lower()
        if raw_type not in {"title", "content", "quote", "cta"}:
            raw_type = "content"
        headline = _compact(str(slide.get("headline") or slide.get("title") or slide.get("text") or ""), max_len=140)
        body = _compact(str(slide.get("body") or slide.get("text") or ""), max_len=280)
        if not headline:
            raise VideoCarouselGenerationError("AI returned a slide without a headline")

        if index == 0:
            slide_type = "hook"
            normalized.append({"type": slide_type, "text": headline, "subtitle": body or None, "glow": "spread"})
        elif index == len(slides) - 1:
            slide_type = "cta"
            normalized.append({"type": slide_type, "text": headline, "cta_action": body or "Follow for more.", "glow": "bottom"})
        else:
            slide_type = "body"
            text = body or (headline if raw_type == "quote" else "")
            normalized.append({"type": slide_type, "title": headline, "text": text, "glow": "left" if index % 2 else "right"})

    return {
        "title": _compact(str(data.get("carousel_title") or data.get("title") or "Video Carousel"), max_len=120)
        or "Video Carousel",
        "slides": normalized,
    }


async def generate_video_carousel_config(
    *,
    transcript: str,
    content_brief: str,
    brand: BrandProfile | None,
    template_id: str = "viral-dark",
) -> tuple[dict, str]:
    template = get_template_or_raise(template_id)
    brand_voice = _brand_voice_text(brand)
    prompt = build_video_carousel_prompt(
        transcript=_compact(transcript, max_len=2200),
        brief=_compact(content_brief, max_len=900),
        brand_voice=brand_voice,
    )
    key = _api_key()
    endpoint = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": "You create high-performing social carousel drafts from video transcripts. Return strict JSON only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.72,
        "max_tokens": 2600,
    }
    async with httpx.AsyncClient(timeout=max(30, int(settings.deepseek_timeout_sec))) as client:
        response = await client.post(endpoint, headers={"Authorization": f"Bearer {key}"}, json=payload)
    if response.status_code >= 400:
        logger.warning("[video_carousel] deepseek failed status=%s body=%s", response.status_code, response.text[:300])
        raise VideoCarouselGenerationError("Carousel generation is temporarily unavailable")

    content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    generated = parse_video_carousel_response(content)
    display_name = brand.display_name if brand else "PostBandit Creator"
    handle = brand.handle if brand else "@postbandit"
    config = {
        "title": generated["title"],
        "profile": {"display_name": display_name, "handle": handle},
        "renderer": template_id,
        "template_id": template_id,
        "slides": generated["slides"],
    }
    CarouselConfig.model_validate(config)
    return config, "deepseek"


async def create_video_carousel_queue_item(
    *,
    user_id: uuid.UUID,
    clip_id: uuid.UUID,
    transcript: str,
    content_brief: str,
    db: AsyncSession,
    template_id: str = "viral-dark",
) -> tuple[ContentQueueItem, str]:
    brand = await db.scalar(select(BrandProfile).where(BrandProfile.user_id == user_id))
    config, provider_used = await generate_video_carousel_config(
        transcript=transcript,
        content_brief=content_brief,
        brand=brand,
        template_id=template_id,
    )
    cleanup_at = datetime.now(timezone.utc) + timedelta(days=max(1, int(settings.content_queue_ready_asset_retention_days)))
    metadata = {
        "source_clip_id": str(clip_id),
        "source": "clip_generate_carousel",
        "provider_used": provider_used,
    }
    config["source"] = metadata
    item = ContentQueueItem(
        user_id=user_id,
        content_type="carousel",
        config=config,
        slide_urls=[],
        slide_keys_json=[],
        zip_key=None,
        preview_key=None,
        asset_cleanup_at=cleanup_at,
        status="draft",
        platforms=list(brand.preferred_platforms or []) if brand else [],
        generation_topic=f"Clip carousel: {config.get('title', 'Video Carousel')}",
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item, provider_used
