import json
import logging
import re
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

HASHTAG_RE = re.compile(r"[^A-Za-z0-9_]")


class AICopyError(Exception):
    pass


class AICopyUnavailableError(AICopyError):
    pass


@dataclass(frozen=True)
class AICopyResult:
    title_options: list[str]
    hashtag_options: list[list[str]]


@dataclass(frozen=True)
class PlatformCopyResult:
    results: dict[str, dict[str, object]]
    errors: dict[str, str]


@dataclass(frozen=True)
class CopyOptionsResult:
    titles: list[str]
    captions: list[str]
    descriptions: list[str]
    hashtag_sets: list[list[str]]
    platform: str | None = None


PLATFORM_COPY_LIMITS: dict[str, dict[str, int | bool]] = {
    "instagram": {"caption": 2200, "hashtags": 30},
    "threads": {"caption": 500, "hashtags": 5},
    "facebook": {"caption": 5000, "hashtags": 10},
    "youtube": {"title": 100, "description": 5000, "hashtags": 15},
    "x": {"caption": 280, "hashtags": 3},
    "tiktok": {"caption": 2200, "hashtags": 8},
    "linkedin": {"caption": 3000, "hashtags": 5},
}


def _is_placeholder(value: str | None) -> bool:
    if value is None:
        return True
    normalized = value.strip().lower()
    return normalized == "" or normalized == "placeholder"


def provider_configured() -> bool:
    return not _is_placeholder(settings.deepseek_api_key)


def _normalize_title(title: str) -> str:
    text = " ".join((title or "").strip().split())
    if len(text) > 120:
        text = text[:120].rstrip()
    return text


def _normalize_hashtag(tag: str) -> str | None:
    text = (tag or "").strip()
    if not text:
        return None
    if not text.startswith("#"):
        text = f"#{text}"
    head = "#"
    body = HASHTAG_RE.sub("", text[1:])
    if not body:
        return None
    return f"{head}{body.lower()}"


def _coerce_hashtag_set(raw_set: object, *, limit: int = 5) -> list[str]:
    if isinstance(raw_set, str):
        pieces = [item for item in re.split(r"[\s,]+", raw_set) if item]
    elif isinstance(raw_set, list):
        pieces = [str(item) for item in raw_set]
    else:
        pieces = []

    normalized: list[str] = []
    seen: set[str] = set()
    for piece in pieces:
        tag = _normalize_hashtag(piece)
        if not tag or tag in seen:
            continue
        seen.add(tag)
        normalized.append(tag)
    return normalized[:limit]


def _ensure_three_titles(raw_titles: object) -> list[str]:
    titles: list[str] = []
    if isinstance(raw_titles, list):
        for item in raw_titles:
            text = _normalize_title(str(item))
            if text and text not in titles:
                titles.append(text)

    if not titles:
        raise AICopyError("AI response missing title options")

    if len(titles) == 1:
        titles.extend([f"{titles[0]} | Clip 2", f"{titles[0]} | Clip 3"])
    elif len(titles) == 2:
        titles.append(f"{titles[0]} | Clip 3")

    return titles[:3]


def _ensure_three_hashtag_sets(raw_sets: object) -> list[list[str]]:
    sets: list[list[str]] = []
    if isinstance(raw_sets, list):
        for raw in raw_sets:
            normalized = _coerce_hashtag_set(raw)
            if 3 <= len(normalized) <= 5 and normalized not in sets:
                sets.append(normalized)

    if not sets:
        raise AICopyError("AI response missing hashtag options")

    fallback_cycle = sets[:]
    idx = 0
    while len(sets) < 3 and fallback_cycle:
        sets.append(fallback_cycle[idx % len(fallback_cycle)])
        idx += 1
    return sets[:3]


def _ensure_five_strings(raw_values: object, *, field_name: str, max_length: int | None = None) -> list[str]:
    values: list[str] = []
    if isinstance(raw_values, list):
        for item in raw_values:
            text = " ".join(str(item or "").split()).strip()
            if max_length and len(text) > max_length:
                text = text[:max_length].rstrip()
            if text and text not in values:
                values.append(text)

    if not values:
        raise AICopyError(f"AI response missing {field_name} options")

    while len(values) < 5:
        values.append(values[len(values) % len(values)])
    return values[:5]


def _words(value: str) -> list[str]:
    return [piece for piece in " ".join((value or "").split()).split(" ") if piece]


def _ensure_five_descriptions(raw_values: object) -> list[str]:
    values = _ensure_five_strings(raw_values, field_name="description", max_length=None)
    normalized: list[str] = []
    for value in values:
        words = _words(value)
        if len(words) > 250:
            value = " ".join(words[:250]).rstrip(" ,.;:") + "."
        normalized.append(value)
    return normalized[:5]


def _too_similar(a: str, b: str) -> bool:
    left = re.sub(r"[^a-z0-9]+", "", (a or "").lower())
    right = re.sub(r"[^a-z0-9]+", "", (b or "").lower())
    if not left or not right:
        return False
    return left == right or left in right[: max(len(left) + 8, 40)]


def _ensure_five_hashtag_sets(raw_sets: object, *, limit: int = 15, minimum: int = 1) -> list[list[str]]:
    sets: list[list[str]] = []
    if isinstance(raw_sets, list):
        for raw in raw_sets:
            normalized = _coerce_hashtag_set(raw, limit=limit)
            if len(normalized) >= minimum and normalized not in sets:
                sets.append(normalized)

    if not sets:
        raise AICopyError("AI response missing hashtag set options")

    while len(sets) < 5:
        sets.append(sets[len(sets) % len(sets)])
    return sets[:5]


def _extract_content_json(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        raise AICopyError("AI response was empty")

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Support fenced JSON output fallback.
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            candidate = part.strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            if not candidate:
                continue
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue

    raise AICopyError("AI response was not valid JSON")


def _truncate_field(value: object, limit: int) -> str | None:
    normalized = " ".join(str(value or "").split()).strip()
    if not normalized:
        return None
    return normalized[:limit].rstrip()


def _normalize_platform_copy(platform: str, value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AICopyError("Platform result must be a JSON object")
    limits = PLATFORM_COPY_LIMITS[platform]
    result: dict[str, object] = {
        "title": None,
        "caption": None,
        "description": None,
        "hashtags": [],
    }
    for field in ("title", "caption", "description"):
        limit = int(limits.get(field, 0) or 0)
        if limit:
            result[field] = _truncate_field(value.get(field), limit)

    raw_hashtags = value.get("hashtags")
    hashtag_limit = int(limits.get("hashtags", 0) or 0)
    hashtags = _coerce_hashtag_set(raw_hashtags)
    if isinstance(raw_hashtags, list) and hashtag_limit > 5:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in raw_hashtags:
            tag = _normalize_hashtag(str(item))
            if tag and tag not in seen:
                seen.add(tag)
                normalized.append(tag)
            if len(normalized) >= hashtag_limit:
                break
        hashtags = normalized
    result["hashtags"] = hashtags[:hashtag_limit]

    if not any(result[field] for field in ("title", "caption", "description")):
        raise AICopyError("Platform result contains no usable copy")
    return result


def generate_content_brief(transcript_text: str, *, video_title: str | None = None) -> str:
    transcript = " ".join((transcript_text or "").split())
    if not transcript:
        raise AICopyError("Clip transcript text is empty")

    system_prompt = (
        "You turn one video clip transcript into a compact creative brief for social copy. "
        "Return ONLY valid JSON with this exact shape: {\"brief\":\"...\"}. "
        "Do not include markdown or generic filler."
    )
    user_prompt = f"""Create one 80-110 word content brief from this clip.

The brief must capture:
- the real topic
- the strongest hook or key moment
- the intended audience
- the tone
- any useful context for title, caption, description, and hashtag writing

Video title context: {video_title or "Not provided"}

Transcript excerpt:
{transcript[:1500]}
"""
    parsed = _post_deepseek_json(system_prompt, user_prompt)
    brief = " ".join(str(parsed.get("brief") or "").split()).strip()
    if len(brief) < 40:
        raise AICopyError("AI response missing content brief")
    if len(brief) > 1200:
        brief = brief[:1200].rstrip()
    return brief


def _post_deepseek_json(system_prompt: str, user_prompt: str) -> dict:
    if not provider_configured():
        raise AICopyUnavailableError("DEEPSEEK_API_KEY is not configured")

    payload = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.7,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }
    endpoint = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"
    try:
        with httpx.Client(timeout=settings.deepseek_timeout_sec) as client:
            response = client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.warning("[ai_copy] DeepSeek HTTP failure status=%s", exc.response.status_code)
        raise AICopyUnavailableError(f"DeepSeek API error: HTTP {exc.response.status_code}") from exc
    except Exception as exc:
        logger.warning("[ai_copy] DeepSeek request failure error=%s", exc)
        raise AICopyUnavailableError(f"DeepSeek request failed: {exc}") from exc

    try:
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as exc:
        raise AICopyError("DeepSeek response payload was invalid") from exc
    return _extract_content_json(content)


PLATFORM_COPY_PROMPTS: dict[str, str] = {
    "youtube": (
        "Platform: YouTube\n"
        "- Titles: SEO-optimized, 60-70 characters, include searchable keywords\n"
        "- Captions/descriptions: 200-400 words, keyword-rich, useful context\n"
        "- Hashtags: 5-8 tags, mix broad and specific"
    ),
    "tiktok": (
        "Platform: TikTok\n"
        "- Titles: punchy, trend-aware, under 60 characters\n"
        "- Captions: under 200 characters, casual, direct, strong CTA\n"
        "- Hashtags: 3-6 tags, trending and niche mix"
    ),
    "instagram": (
        "Platform: Instagram\n"
        "- Titles: hook-forward, visual language, under 90 characters\n"
        "- Captions: 150-300 words, storytelling tone, end with a question\n"
        "- Hashtags: 15-25 tags, broad + niche + micro"
    ),
    "x": (
        "Platform: X\n"
        "- Titles: under 100 characters, opinionated, sparks discussion\n"
        "- Captions: under 240 characters, punchy, no filler\n"
        "- Hashtags: 1-3 tags maximum"
    ),
    "facebook": (
        "Platform: Facebook\n"
        "- Titles: friendly, community-oriented, 80-100 characters\n"
        "- Captions: 100-250 words, conversational, relatable story\n"
        "- Hashtags: 3-5 tags, broad only"
    ),
    "threads": (
        "Platform: Threads\n"
        "- Titles: casual, authentic, under 80 characters\n"
        "- Captions: under 300 characters, conversational\n"
        "- Hashtags: 2-4 tags"
    ),
}


def generate_copy_options(
    transcript_text: str | None = None,
    *,
    content_brief: str | None = None,
    video_title: str | None = None,
    platform: str | None = None,
) -> CopyOptionsResult:
    brief = " ".join((content_brief or transcript_text or "").split())
    if not brief:
        raise AICopyError("Clip content brief is empty")

    normalized_platform = (platform or "").strip().lower() or None
    if normalized_platform and normalized_platform not in PLATFORM_COPY_PROMPTS:
        raise AICopyError("Unsupported platform for copy generation")

    platform_constraints = f"\n\n{PLATFORM_COPY_PROMPTS[normalized_platform]}" if normalized_platform else ""
    hashtag_limit = (
        3
        if normalized_platform == "x"
        else 5
        if normalized_platform in {"threads", "facebook"}
        else 8
        if normalized_platform in {"youtube", "tiktok"}
        else 15
    )
    hashtag_minimum = 1 if normalized_platform == "x" else 3

    system_prompt = (
        "You are an expert social media copywriter for creators. Return ONLY valid JSON. "
        "Do not include markdown fences, explanations, or raw transcript excerpts as the answer. "
        "Write polished publish-ready copy based on the actual clip content."
    )
    user_prompt = f"""A creator has a video clip summarized by this content brief:

---CONTENT BRIEF---
{brief[:1200]}
---END CONTENT BRIEF---

Video title context: {video_title or "Not provided"}
{platform_constraints}

Generate 5 distinct variations for each field. Make them genuinely different in tone and angle:
- Variation 1: Bold hook, grabs attention immediately
- Variation 2: Storytelling, personal and relatable
- Variation 3: Educational, value-forward, positions creator as expert
- Variation 4: Question-based, drives comments and engagement
- Variation 5: Conversational, casual, like texting a friend

Respond ONLY with valid JSON in this exact shape:
{{
  "titles": ["title option 1", "title option 2", "title option 3", "title option 4", "title option 5"],
  "captions": ["caption option 1", "caption option 2", "caption option 3", "caption option 4", "caption option 5"],
  "descriptions": ["description option 1", "description option 2", "description option 3", "description option 4", "description option 5"],
  "hashtag_sets": [
    ["#tag1", "#tag2", "#tag3"],
    ["#tag1", "#tag2", "#tag3"],
    ["#tag1", "#tag2", "#tag3"],
    ["#tag1", "#tag2", "#tag3"],
    ["#tag1", "#tag2", "#tag3"]
  ]
}}

Rules:
- Titles: 50-100 characters, strong hook, no generic clickbait
- Captions: under 280 characters, specific to the video content, not the same text as the title
- Descriptions: 120-250 words, useful and specific, written for publish pages and YouTube-style descriptions
- Hashtags: relevant to the actual video content
- All 5 variations must be meaningfully different, not minor rewrites
- Base everything on the content brief; do not use generic filler"""

    parsed = _post_deepseek_json(system_prompt, user_prompt)
    titles = _ensure_five_strings(parsed.get("titles"), field_name="title", max_length=120)
    captions = _ensure_five_strings(parsed.get("captions"), field_name="caption", max_length=280)
    for title, caption in zip(titles, captions, strict=False):
        if _too_similar(title, caption):
            raise AICopyError("AI response returned a caption too similar to its title")
    descriptions = _ensure_five_descriptions(parsed.get("descriptions"))
    hashtag_sets = _ensure_five_hashtag_sets(
        parsed.get("hashtag_sets"),
        limit=hashtag_limit,
        minimum=hashtag_minimum,
    )
    logger.info(
        "[ai_copy] copy options generated platform=%s titles=%s captions=%s descriptions=%s hashtag_sets=%s",
        normalized_platform or "universal",
        len(titles),
        len(captions),
        len(descriptions),
        len(hashtag_sets),
    )
    return CopyOptionsResult(
        titles=titles,
        captions=captions,
        descriptions=descriptions,
        hashtag_sets=hashtag_sets,
        platform=normalized_platform,
    )


def generate_platform_copy(
    transcript_text: str,
    platforms: list[str],
    *,
    video_title: str | None = None,
    topic_hint: str | None = None,
) -> PlatformCopyResult:
    transcript = " ".join((transcript_text or "").split())
    if not transcript:
        raise AICopyError("Clip transcript text is empty")

    selected = list(dict.fromkeys(platform for platform in platforms if platform in PLATFORM_COPY_LIMITS))
    if not selected:
        raise AICopyError("No supported platforms were selected")

    constraints = {
        platform: PLATFORM_COPY_LIMITS[platform]
        for platform in selected
    }
    system_prompt = (
        "You write platform-native social copy for one video clip. Return ONLY a JSON object "
        'with a top-level "results" object keyed by every requested platform. Each platform '
        'may contain "title", "caption", "description", and "hashtags" (an array). '
        "Do not invent facts not present in the transcript. Use concise natural language and "
        f"respect these character/count limits: {json.dumps(constraints)}"
    )
    user_prompt = (
        f"Requested platforms: {', '.join(selected)}\n"
        f"Video title: {video_title or 'Untitled'}\n"
        f"Topic direction: {topic_hint or 'Use the strongest idea in the clip'}\n"
        f"Transcript:\n{transcript[:16000]}"
    )
    parsed = _post_deepseek_json(system_prompt, user_prompt)
    raw_results = parsed.get("results", parsed)
    if not isinstance(raw_results, dict):
        raise AICopyError("DeepSeek response missing platform results")

    results: dict[str, dict[str, object]] = {}
    errors: dict[str, str] = {}
    for platform in selected:
        try:
            results[platform] = _normalize_platform_copy(platform, raw_results.get(platform))
        except AICopyError as exc:
            errors[platform] = str(exc)

    if not results:
        raise AICopyError("No platform copy result could be parsed")
    return PlatformCopyResult(results=results, errors=errors)


def generate_clip_copy(
    transcript_text: str,
    video_title: str | None = None,
    clip_start: float | None = None,
    clip_end: float | None = None,
) -> AICopyResult:
    if not provider_configured():
        raise AICopyUnavailableError("DEEPSEEK_API_KEY is not configured")

    transcript = " ".join((transcript_text or "").split())
    if not transcript:
        raise AICopyError("Clip transcript text is empty")

    clip_window = ""
    if clip_start is not None and clip_end is not None:
        clip_window = f"{clip_start:.2f}s-{clip_end:.2f}s"

    system_prompt = (
        "You generate short-form social copy for a video clip. "
        "Return ONLY valid JSON with this exact shape: "
        '{"titles":["...","...","..."],'
        '"hashtag_sets":[["#tag1","#tag2","#tag3"],["#..."],["#..."]]} '
        "Rules: titles should be concise and platform-friendly, not spammy, "
        "and each hashtag set should contain 3 to 5 hashtags."
    )
    user_prompt = (
        f"Video title: {video_title or 'Untitled'}\n"
        f"Clip window: {clip_window or 'unknown'}\n"
        f"Transcript:\n{transcript}"
    )

    payload = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.7,
    }
    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }
    endpoint = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"

    logger.info("[ai_copy] generation start model=%s endpoint=%s", settings.deepseek_model, endpoint)
    try:
        with httpx.Client(timeout=settings.deepseek_timeout_sec) as client:
            response = client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.warning("[ai_copy] generation HTTP failure status=%s error=%s", exc.response.status_code, exc)
        raise AICopyUnavailableError(f"DeepSeek API error: HTTP {exc.response.status_code}") from exc
    except Exception as exc:
        logger.warning("[ai_copy] generation request failure error=%s", exc)
        raise AICopyUnavailableError(f"DeepSeek request failed: {exc}") from exc

    data = response.json()
    content = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    parsed = _extract_content_json(content)

    titles = _ensure_three_titles(parsed.get("titles"))
    hashtag_sets = _ensure_three_hashtag_sets(parsed.get("hashtag_sets"))

    logger.info("[ai_copy] generation end titles=%s hashtag_sets=%s", len(titles), len(hashtag_sets))
    return AICopyResult(title_options=titles, hashtag_options=hashtag_sets)
