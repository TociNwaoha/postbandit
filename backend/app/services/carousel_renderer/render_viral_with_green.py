#!/usr/bin/env python3
"""
Viral Instagram Carousel Renderer
Black background with teal glow blobs, Inter Black headlines, teal accent bullets.
Matches the high-engagement viral format used by top AI/tech accounts.

Usage:
    python3 render_viral.py <carousel-dir>
    python3 render_viral.py workspace/my-carousel
"""

import json
import math
import sys
import os
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

SLIDE_WIDTH = 1080
SLIDE_HEIGHT = 1350

ASSETS_DIR = Path(__file__).parent / "assets"
FONT_DIR = ASSETS_DIR / "fonts"
LOGO_PATH = ASSETS_DIR / "postbandit-logo.png"
HEADSHOT_PATH = ASSETS_DIR / "headshot.jpg"

COLORS = {
    "bg":           "#000000",
    "teal":         "#00E5BF",
    "teal_dark":    "#00B897",
    "white":        "#FFFFFF",
    "off_white":    "#E8E8E8",
    "gray":         "#888888",
    "card_bg":      "#111111",
    "card_border":  "#222222",
    "badge_bg":     "#1A1A1A",
    "black":        "#000000",
}

PADDING = 72
CONTENT_WIDTH = SLIDE_WIDTH - (PADDING * 2)


def load_fonts():
    black_path  = str(FONT_DIR / "Inter-Black.ttf")
    extrabold_path = str(FONT_DIR / "Inter-ExtraBold.ttf")
    bold_path   = str(FONT_DIR / "Inter-Bold.ttf")
    regular_path = str(FONT_DIR / "Inter-Regular.ttf")
    caveat_path = str(FONT_DIR / "Caveat.ttf")

    def inter_black(size):
        return ImageFont.truetype(black_path, size)

    def inter_extrabold(size):
        return ImageFont.truetype(extrabold_path, size)

    def inter_bold(size):
        return ImageFont.truetype(bold_path, size)

    def inter_regular(size):
        return ImageFont.truetype(regular_path, size)

    def caveat(size):
        return ImageFont.truetype(caveat_path, size)

    fonts = {}
    try:
        fonts["headline_xl"] = inter_black(88)
        fonts["headline_lg"] = inter_black(72)
        fonts["headline_md"] = inter_extrabold(58)
        fonts["headline_sm"] = inter_extrabold(46)
        fonts["headline_xs"] = inter_bold(38)
        fonts["body_lg"]     = inter_bold(44)
        fonts["body"]        = inter_bold(38)
        fonts["body_sm"]     = inter_bold(32)
        fonts["label"]       = inter_bold(26)
        fonts["caption"]     = inter_regular(26)
        fonts["handle"]      = inter_regular(28)
        fonts["display_name"] = inter_bold(32)
        fonts["badge"]       = inter_bold(24)
        fonts["arrow_xl"]    = inter_black(60)
        fonts["hand"]        = caveat(48)
    except Exception as e:
        print(f"Font error: {e}")
        default = ImageFont.load_default()
        for key in ["headline_xl","headline_lg","headline_md","headline_sm","headline_xs",
                    "body_lg","body","body_sm","label","caption","handle","display_name",
                    "badge","arrow_xl","hand"]:
            fonts[key] = default
    return fonts


def hex_to_rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def draw_teal_glow(img, positions="corners", intensity=60):
    """Paint teal radial glow blobs. positions: 'corners', 'left', 'right', 'bottom', 'full'"""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    teal_r, teal_g, teal_b = hex_to_rgb(COLORS["teal"])

    blobs = []
    if positions == "corners":
        blobs = [
            (0, SLIDE_HEIGHT, 560, intensity),
            (SLIDE_WIDTH, SLIDE_HEIGHT, 440, intensity // 2),
        ]
    elif positions == "left":
        blobs = [
            (0, SLIDE_HEIGHT // 2, 480, intensity),
            (SLIDE_WIDTH, SLIDE_HEIGHT, 360, intensity // 3),
        ]
    elif positions == "right":
        blobs = [
            (SLIDE_WIDTH, SLIDE_HEIGHT // 2, 480, intensity),
            (0, SLIDE_HEIGHT, 340, intensity // 3),
        ]
    elif positions == "bottom":
        blobs = [(SLIDE_WIDTH // 2, SLIDE_HEIGHT, 640, intensity)]
    elif positions == "full":
        blobs = [
            (0, SLIDE_HEIGHT, 580, intensity),
            (SLIDE_WIDTH, SLIDE_HEIGHT // 2, 440, intensity // 2),
            (SLIDE_WIDTH // 2, SLIDE_HEIGHT, 400, intensity // 3),
        ]
    elif positions == "top-right":
        blobs = [
            (SLIDE_WIDTH, 0, 460, intensity),
            (0, SLIDE_HEIGHT, 380, intensity // 3),
        ]
    elif positions == "spread":
        blobs = [
            (0, SLIDE_HEIGHT, 540, intensity),
            (SLIDE_WIDTH, 220, 400, intensity // 2),
            (SLIDE_WIDTH // 2, SLIDE_HEIGHT, 360, intensity // 3),
        ]

    for cx, cy, radius, alpha_max in blobs:
        glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        steps = 18
        for i in range(steps, 0, -1):
            r = int(radius * i / steps)
            a = int(alpha_max * (1 - i / steps) ** 1.5)
            gd.ellipse([cx - r, cy - r, cx + r, cy + r],
                       fill=(teal_r, teal_g, teal_b, a))
        glow = glow.filter(ImageFilter.GaussianBlur(60))
        overlay = Image.alpha_composite(overlay, glow)

    combined = Image.alpha_composite(img.convert("RGBA"), overlay)
    img.paste(combined.convert("RGB"), (0, 0))


def create_base_slide(glow_pos="corners", intensity=90):
    img = Image.new("RGB", (SLIDE_WIDTH, SLIDE_HEIGHT), hex_to_rgb(COLORS["bg"]))
    draw_teal_glow(img, positions=glow_pos, intensity=intensity)
    return img


def load_cta_avatar(size):
    """Prefer PostBandit logo; fall back to legacy headshot."""
    for candidate in (LOGO_PATH, HEADSHOT_PATH):
        if not candidate.exists():
            continue
        avatar = Image.open(candidate).convert("RGB")
        square = min(avatar.size)
        avatar = avatar.crop(
            (
                (avatar.width - square) // 2,
                (avatar.height - square) // 2,
                (avatar.width + square) // 2,
                (avatar.height + square) // 2,
            )
        )
        avatar = avatar.resize((size, size), Image.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        md = ImageDraw.Draw(mask)
        md.ellipse([0, 0, size, size], fill=255)
        avatar.putalpha(mask)
        return avatar
    return None


def draw_text_line(draw, text, x, y, font, fill, max_width=None):
    """Draw a single line, return height used."""
    if max_width:
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        if w > max_width:
            # shrink doesn't apply here — caller wraps instead
            pass
    draw.text((x, y), text, font=font, fill=fill)
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[3] - bbox[1]


def wrap_text(draw, text, font, max_width):
    """Wrap text into lines that fit max_width."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def text_height(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[3] - bbox[1]


def text_width(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def draw_mixed_text(draw, text, x, y, font, default_fill, accent_fill, max_width, line_gap=14):
    """Render text with *accent* segments. Returns total height used."""
    import re

    # Split on *accent* markers, preserving them as separate parts
    parts = re.split(r'(\*[^*]+\*)', text)

    # Build tokens: (word, color, is_punctuation)
    # is_punctuation=True means no leading space when placed after another token
    PUNCT_START = set('.,!?:;)')
    tokens = []
    for part in parts:
        if part.startswith('*') and part.endswith('*'):
            inner = part[1:-1]
            # Check if the accent word itself ends with trailing punctuation
            # e.g. *free.* → keep punctuation attached
            tokens.append((inner, accent_fill, inner[0] in PUNCT_START))
        else:
            # Split on spaces, but preserve leading punctuation attached to previous token
            for w in part.split(' '):
                if w:
                    tokens.append((w, default_fill, w[0] in PUNCT_START))

    # Word-wrap respecting accent and punctuation spacing
    lines = []
    current_line = []
    current_width = 0

    for word, color, is_punct in tokens:
        word_w = text_width(draw, word, font)
        space_w = text_width(draw, ' ', font)
        # No leading space for punctuation tokens or first token on line
        needs_space = current_line and not is_punct
        needed = word_w + (space_w if needs_space else 0)
        if current_line and current_width + needed > max_width:
            lines.append(current_line)
            current_line = [(word, color, is_punct)]
            current_width = word_w
        else:
            current_line.append((word, color, is_punct))
            current_width += needed

    if current_line:
        lines.append(current_line)

    total_h = 0
    line_h = text_height(draw, "Ag", font) + line_gap

    for line_tokens in lines:
        cx = x
        for i, (word, color, is_punct) in enumerate(line_tokens):
            # Add space before this word unless it's punctuation or first on line
            if i > 0 and not is_punct:
                cx += text_width(draw, ' ', font)
            draw.text((cx, y + total_h), word, font=font, fill=color)
            cx += text_width(draw, word, font)
        total_h += line_h

    return total_h


def draw_viral_badge(draw, fonts, cx, y):
    """Draw the 'VIRAL' pill badge centered at cx."""
    label = "VIRAL"
    lw = text_width(draw, label, fonts["badge"])
    pad_x, pad_y = 24, 10
    pill_w = lw + pad_x * 2
    pill_h = text_height(draw, label, fonts["badge"]) + pad_y * 2
    x0 = cx - pill_w // 2
    r = pill_h // 2
    # background pill
    draw.rounded_rectangle([x0, y, x0 + pill_w, y + pill_h], radius=r,
                            fill=hex_to_rgb(COLORS["badge_bg"]))
    # teal text
    draw.text((x0 + pad_x, y + pad_y), label, font=fonts["badge"],
              fill=hex_to_rgb(COLORS["teal"]))
    return pill_h + 18


def draw_rounded_card(img, draw, x, y, w, h, bg_color="#111111", border_color="#2A2A2A", radius=28):
    draw.rounded_rectangle([x, y, x + w, y + h], radius=radius,
                            fill=hex_to_rgb(bg_color),
                            outline=hex_to_rgb(border_color), width=2)


def load_reference_image(carousel_dir, filename, target_w, target_h, fit="fill"):
    path = carousel_dir / "reference" / filename
    if not path.exists():
        return None
    img = Image.open(path).convert("RGB")
    if fit == "fill":
        # center-crop to exact size
        src_ratio = img.width / img.height
        tgt_ratio = target_w / target_h
        if src_ratio > tgt_ratio:
            new_w = int(img.height * tgt_ratio)
            offset = (img.width - new_w) // 2
            img = img.crop((offset, 0, offset + new_w, img.height))
        else:
            new_h = int(img.width / tgt_ratio)
            offset = (img.height - new_h) // 2
            img = img.crop((0, offset, img.width, offset + new_h))
        img = img.resize((target_w, target_h), Image.LANCZOS)
    elif fit == "fit":
        img.thumbnail((target_w, target_h), Image.LANCZOS)
    return img


def draw_footer(img, draw, fonts, handle="@scaledbytoci.ai"):
    """Draw subtle bottom footer with handle."""
    y = SLIDE_HEIGHT - 52
    draw.text((PADDING, y), handle, font=fonts["handle"],
              fill=hex_to_rgb(COLORS["gray"]))


def draw_image_in_card(img, carousel_dir, filename, x, y, w, h, radius=24):
    """Paste a reference image inside a rounded-corner card."""
    ref = load_reference_image(carousel_dir, filename, w, h, fit="fill")
    if ref is None:
        return

    # Create a rounded mask
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, w, h], radius=radius, fill=255)

    ref_rgba = ref.convert("RGBA")
    ref_rgba.putalpha(mask)
    img.paste(ref_rgba, (x, y), ref_rgba)


# -- Slide Renderers ----------------------------------------------------------

def render_hook_slide(config, slide, fonts, carousel_dir):
    """
    Large image fills top 55% of slide.
    Black gradient fade at bottom.
    VIRAL badge + big headline + subtitle below image.
    """
    img = create_base_slide(glow_pos="corners")
    draw = ImageDraw.Draw(img)

    image_h = int(SLIDE_HEIGHT * 0.56)

    # Hero image
    if slide.get("image"):
        ref = load_reference_image(carousel_dir, slide["image"], SLIDE_WIDTH, image_h, fit="fill")
        if ref:
            img.paste(ref, (0, 0))
            # Gradient fade from transparent to black at bottom of image
            fade = Image.new("RGBA", (SLIDE_WIDTH, image_h), (0, 0, 0, 0))
            fd = ImageDraw.Draw(fade)
            fade_start = int(image_h * 0.45)
            for i in range(fade_start, image_h):
                alpha = int(255 * ((i - fade_start) / (image_h - fade_start)) ** 1.2)
                fd.line([(0, i), (SLIDE_WIDTH, i)], fill=(0, 0, 0, alpha))
            img.paste(fade, (0, 0), fade)

    y = image_h - 20

    # VIRAL badge
    draw = ImageDraw.Draw(img)
    badge_h = draw_viral_badge(draw, fonts, SLIDE_WIDTH // 2, y)
    y += badge_h + 8

    # Headline
    headline = slide.get("text", "")
    hcolor = hex_to_rgb(COLORS["white"])
    accent  = hex_to_rgb(COLORS["teal"])
    h_used = draw_mixed_text(draw, headline, PADDING, y, fonts["headline_lg"],
                             hcolor, accent, CONTENT_WIDTH, line_gap=8)
    y += h_used + 16

    # Subtitle
    if slide.get("subtitle"):
        sub = slide["subtitle"]
        s_used = draw_mixed_text(draw, sub, PADDING, y, fonts["body"],
                                 hex_to_rgb(COLORS["off_white"]), accent, CONTENT_WIDTH, line_gap=6)
        y += s_used

    draw_footer(img, draw, fonts, config.get("profile", {}).get("handle", "@scaledbytoci.ai"))
    return img


def _estimate_body_height(draw, slide, fonts):
    """Pre-calculate total content height for a body slide (for vertical centering)."""
    h = 0
    if slide.get("label"):
        h += text_height(draw, slide["label"], fonts["label"]) + 16
    if slide.get("title"):
        # rough estimate: 2 lines max for headline
        title_h = text_height(draw, "Ag", fonts["headline_lg"]) + 6
        h += title_h * 2 + 28
    if slide.get("text"):
        body_h = text_height(draw, "Ag", fonts["body_lg"]) + 10
        h += body_h * 3 + 24
    if slide.get("subheading"):
        h += text_height(draw, "Ag", fonts["headline_sm"]) + 6 + 24
    if slide.get("bullets"):
        bullet_h = text_height(draw, "Ag", fonts["body"]) + 8
        h += len(slide["bullets"]) * (bullet_h + 22)
    return h


def render_body_slide(config, slide, fonts, carousel_dir):
    has_image = bool(slide.get("image"))
    img = create_base_slide(glow_pos=slide.get("glow", "corners"), intensity=115)
    draw = ImageDraw.Draw(img)

    white  = hex_to_rgb(COLORS["white"])
    teal   = hex_to_rgb(COLORS["teal"])

    # Vertically center content on text-only slides
    if has_image:
        y = PADDING + 20
    else:
        estimated_h = _estimate_body_height(draw, slide, fonts)
        footer_clearance = 100
        centered_y = (SLIDE_HEIGHT - footer_clearance - estimated_h) // 2
        y = max(PADDING + 20, centered_y)

    # Optional top label
    if slide.get("label"):
        draw.text((PADDING, y), slide["label"].upper(), font=fonts["label"], fill=teal)
        y += text_height(draw, slide["label"], fonts["label"]) + 16

    # Headline (big)
    if slide.get("title"):
        h_used = draw_mixed_text(draw, slide["title"], PADDING, y, fonts["headline_lg"],
                                 white, teal, CONTENT_WIDTH, line_gap=6)
        y += h_used + 28

    # Body text
    if slide.get("text"):
        t_used = draw_mixed_text(draw, slide["text"], PADDING, y, fonts["body_lg"],
                                 white, teal, CONTENT_WIDTH, line_gap=10)
        y += t_used + 24

    # Teal-accent subheading
    if slide.get("subheading"):
        sh_used = draw_mixed_text(draw, slide["subheading"], PADDING, y, fonts["headline_sm"],
                                  teal, white, CONTENT_WIDTH, line_gap=6)
        y += sh_used + 24

    # Bullets with teal arrow prefix
    if slide.get("bullets"):
        for bullet in slide["bullets"]:
            arrow = "→  "
            draw.text((PADDING, y), arrow, font=fonts["body"], fill=teal)
            arrow_w = text_width(draw, arrow, fonts["body"])
            b_used = draw_mixed_text(draw, bullet, PADDING + arrow_w, y, fonts["body"],
                                     white, teal, CONTENT_WIDTH - arrow_w, line_gap=8)
            line_h = text_height(draw, "Ag", fonts["body"])
            y += max(b_used, line_h) + 22

    # Image card (screenshot / diagram)
    if has_image:
        remaining = SLIDE_HEIGHT - 80 - y
        if remaining > 160:
            card_h = min(remaining, 480)
            card_x = PADDING
            card_w = CONTENT_WIDTH
            draw_image_in_card(img, carousel_dir, slide["image"],
                               card_x, y, card_w, card_h, radius=24)
            y += card_h

    draw_footer(img, draw, fonts, config.get("profile", {}).get("handle", "@scaledbytoci.ai"))
    return img


def render_cta_slide(config, slide, fonts, carousel_dir):
    """
    CTA with teal glow, up-arrow cluster, DM notification pill, bold CTA text.
    """
    img = create_base_slide(glow_pos="full")
    draw = ImageDraw.Draw(img)

    white = hex_to_rgb(COLORS["white"])
    teal  = hex_to_rgb(COLORS["teal"])
    black = hex_to_rgb(COLORS["black"])

    y = PADDING + 10

    # Main CTA text (top)
    if slide.get("text"):
        t_used = draw_mixed_text(draw, slide["text"], PADDING, y, fonts["headline_md"],
                                 white, teal, CONTENT_WIDTH, line_gap=8)
        y += t_used + 40

    # Arrow cluster (↑ pointing up) in teal
    arrow_count = 7
    arrow_font = fonts["arrow_xl"]
    arrow_sym = "↑"
    sym_w = text_width(draw, arrow_sym, arrow_font)
    sym_h = text_height(draw, arrow_sym, arrow_font)
    total_arrow_w = arrow_count * (sym_w + 12) - 12
    ax_start = (SLIDE_WIDTH - total_arrow_w) // 2
    arrow_y = y

    teal_r, teal_g, teal_b = hex_to_rgb(COLORS["teal"])
    dark_r, dark_g, dark_b = 30, 30, 30

    for i in range(arrow_count):
        color = (teal_r, teal_g, teal_b) if i % 2 == 1 else (dark_r, dark_g, dark_b)
        ax = ax_start + i * (sym_w + 12)
        draw.text((ax, arrow_y), arrow_sym, font=arrow_font, fill=color)

    y += sym_h + 36

    # DM notification pill
    pill_w = 520
    pill_h = 88
    pill_x = (SLIDE_WIDTH - pill_w) // 2
    pill_y = y

    draw.rounded_rectangle([pill_x, pill_y, pill_x + pill_w, pill_y + pill_h],
                            radius=pill_h // 2,
                            fill=hex_to_rgb(COLORS["card_bg"]),
                            outline=hex_to_rgb(COLORS["card_border"]), width=2)

    # Avatar circle (PostBandit logo by default)
    avatar_size = 60
    avatar_x = pill_x + 14
    avatar_y = pill_y + (pill_h - avatar_size) // 2

    avatar = load_cta_avatar(avatar_size)
    if avatar is not None:
        img.paste(avatar, (avatar_x, avatar_y), avatar)

        # Accent ring
        ring_draw = ImageDraw.Draw(img)
        ring_draw.ellipse([avatar_x - 3, avatar_y - 3,
                           avatar_x + avatar_size + 3, avatar_y + avatar_size + 3],
                          outline=(0, 229, 191, 255), width=3)
    else:
        draw.ellipse([avatar_x, avatar_y, avatar_x + avatar_size, avatar_y + avatar_size],
                     fill=teal)

    handle = config.get("profile", {}).get("handle", "@scaledbytoci.ai")
    display = config.get("profile", {}).get("display_name", "Scaled by Toci")

    text_x = avatar_x + avatar_size + 16
    name_y = pill_y + 16
    draw.text((text_x, name_y), display, font=fonts["display_name"], fill=white)
    draw.text((text_x, name_y + 36), "Sent a message · 1m", font=fonts["caption"],
              fill=hex_to_rgb(COLORS["gray"]))

    # Camera icon placeholder
    cam_x = pill_x + pill_w - 52
    cam_y = pill_y + (pill_h - 30) // 2
    draw.text((cam_x, cam_y), "⊙", font=fonts["label"], fill=hex_to_rgb(COLORS["gray"]))

    y = pill_y + pill_h + 40

    # Bottom CTA action text
    if slide.get("cta_action"):
        ca_used = draw_mixed_text(draw, slide["cta_action"], PADDING, y, fonts["headline_sm"],
                                  white, teal, CONTENT_WIDTH, line_gap=6)
        y += ca_used

    elif slide.get("button_text"):
        # Standard button fallback
        btn_text = slide["button_text"]
        btn_w = text_width(draw, btn_text, fonts["body_lg"]) + 80
        btn_h = 70
        btn_x = (SLIDE_WIDTH - btn_w) // 2
        draw.rounded_rectangle([btn_x, y, btn_x + btn_w, y + btn_h],
                                radius=btn_h // 2, fill=teal)
        draw.text((btn_x + 40, y + (btn_h - text_height(draw, btn_text, fonts["body_lg"])) // 2),
                  btn_text, font=fonts["body_lg"], fill=black)

    draw_footer(img, draw, fonts, handle)
    return img


# -- Main Renderer ------------------------------------------------------------

def render_carousel(carousel_dir):
    carousel_dir = Path(carousel_dir)
    config_path = carousel_dir / "config.json"

    if not config_path.exists():
        print(f"Error: config.json not found in {carousel_dir}")
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    fonts = load_fonts()
    slides = config.get("slides", [])
    title = config.get("title", "Carousel")

    print(f"Rendering {len(slides)} slides for '{title}'...")

    for i, slide in enumerate(slides):
        slide_type = slide.get("type", "body")

        if slide_type == "hook":
            img = render_hook_slide(config, slide, fonts, carousel_dir)
        elif slide_type == "cta":
            img = render_cta_slide(config, slide, fonts, carousel_dir)
        else:
            img = render_body_slide(config, slide, fonts, carousel_dir)

        out_path = carousel_dir / f"slide_{i + 1}.png"
        img.save(out_path, "PNG")
        print(f"  Saved slide_{i + 1}.png ({slide_type})")

    print(f"\nDone! {len(slides)} slides saved to {carousel_dir}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 render_viral.py <carousel-dir>")
        sys.exit(1)
    render_carousel(sys.argv[1])
