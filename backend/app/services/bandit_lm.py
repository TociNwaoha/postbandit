from __future__ import annotations

import json
import re

import httpx

from app.config import settings
from app.models.brand_profile import BrandProfile

BANDIT_LM_BASE_URL = "https://api.deepseek.com"
BANDIT_LM_MODEL = "deepseek-v4-flash"
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\\s*(.*?)\\s*```", re.IGNORECASE | re.DOTALL)


def _strip_markdown_json(raw: str) -> str:
    content = (raw or "").strip()
    if not content:
        raise ValueError("Bandit LM returned an empty response")

    if content.startswith("```"):
        match = _JSON_BLOCK_RE.search(content)
        if match:
            return match.group(1).strip()

    return content


def _join_items(items: list[str]) -> str:
    cleaned = [item.strip() for item in items if item and item.strip()]
    return ", ".join(cleaned) if cleaned else "none specified"


async def generate_carousel_config(
    topic: str,
    brand: BrandProfile,
    template_id: str = "viral-dark",
) -> dict:
    system_prompt = f"""You are a viral social media carousel copywriter for {brand.display_name}.

Brand profile:
- Niche: {brand.niche}
- Target audience: {brand.target_audience}
- Tone: {brand.tone}
- Always use these phrases/styles: {_join_items(brand.use_phrases or [])}
- Never use: {_join_items(brand.avoid_phrases or [])}
- Handle: {brand.handle}

Write a 6-slide Instagram carousel about the given topic.
Return ONLY valid JSON matching this exact schema — no explanation, no markdown:

{{
  "title": "short internal title",
  "profile": {{ "display_name": "{brand.display_name}", "handle": "{brand.handle}" }},
  "renderer": "{template_id}",
  "slides": [
    {{
      "type": "hook",
      "text": "Bold hook statement. Use *asterisks* around 1-3 key words.",
      "subtitle": "Optional supporting context under 100 chars."
    }},
    {{
      "type": "body",
      "title": "SECTION TITLE",
      "bullets": ["Point one with *accent*", "Point two", "Point three", "Point four"],
      "glow": "spread"
    }},
    {{
      "type": "body",
      "title": "SECTION TITLE",
      "text": "Body paragraph. *Accent key words.*",
      "glow": "left"
    }},
    {{
      "type": "body",
      "title": "SECTION TITLE",
      "bullets": ["Point one", "Point two", "Point three"],
      "glow": "right"
    }},
    {{
      "type": "body",
      "title": "SECTION TITLE",
      "text": "Body paragraph with *accented words*.",
      "subheading": "Supporting one-liner.",
      "glow": "top-right"
    }},
    {{
      "type": "cta",
      "text": "Your *call to action* here.",
      "cta_action": "Comment *\\"KEYWORD\\"* and I'll send you the link."
    }}
  ]
}}

Rules:
- Max 120 characters per text field
- Max 4 bullets per slide
- Use *asterisks* on 1-3 words per slide only
- Hook must be attention-grabbing and slightly provocative
- CTA keyword should be a single word related to the topic
- Match the brand tone: {brand.tone}
"""

    if not settings.bandit_lm_api_key or settings.bandit_lm_api_key.strip().lower() == "placeholder":
        raise RuntimeError("Bandit LM is not configured")

    try:
        async with httpx.AsyncClient(base_url=BANDIT_LM_BASE_URL, timeout=30) as client:
            response = await client.post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {settings.bandit_lm_api_key}"},
                json={
                    "model": BANDIT_LM_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Topic: {topic}"},
                    ],
                    "temperature": 0.8,
                    "max_tokens": 2000,
                },
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError("Bandit LM is currently unavailable. Please try again.") from exc

    if not settings.bandit_lm_api_key or settings.bandit_lm_api_key.strip().lower() == "placeholder":
        raise RuntimeError("Bandit LM is not configured")

    try:
        raw = response.json()["choices"][0]["message"]["content"].strip()
        raw_json = _strip_markdown_json(raw)
        parsed = json.loads(raw_json)
    except Exception as exc:
        raise ValueError("Bandit LM returned invalid JSON content") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Bandit LM returned an invalid response payload")

    return parsed
