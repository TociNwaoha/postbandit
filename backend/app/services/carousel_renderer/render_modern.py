#!/usr/bin/env python3
"""Render PostBandit's modern carousel theme collection."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH = 1080
HEIGHT = 1350
PAD = 78
FONT_DIR = Path(__file__).parent / "assets" / "fonts"

THEMES = {
    "editorial-sun": {
        "bg": "#F4EBDD",
        "ink": "#1E1B18",
        "muted": "#6C6258",
        "accent": "#F04E2F",
        "card": "#FFF9F0",
        "line": "#1E1B18",
        "mode": "editorial",
    },
    "paper-notes": {
        "bg": "#D9E8D2",
        "ink": "#20251F",
        "muted": "#596257",
        "accent": "#EE5D3B",
        "card": "#FFFDF4",
        "line": "#20251F",
        "mode": "paper",
    },
    "signal-brutalist": {
        "bg": "#F6F000",
        "ink": "#101010",
        "muted": "#343434",
        "accent": "#FF3B30",
        "card": "#FFFFFF",
        "line": "#101010",
        "mode": "brutalist",
    },
    "data-mint": {
        "bg": "#DDF8E8",
        "ink": "#12372A",
        "muted": "#477060",
        "accent": "#FF6B4A",
        "card": "#F8FFF9",
        "line": "#12372A",
        "mode": "data",
    },
    "aurora-glass": {
        "bg": "#111A3C",
        "ink": "#FFFFFF",
        "muted": "#C9D5F4",
        "accent": "#72F1D0",
        "card": "#26345C",
        "line": "#9FAFE3",
        "mode": "glass",
    },
    "retro-future": {
        "bg": "#FF6A3D",
        "ink": "#20104F",
        "muted": "#512B70",
        "accent": "#F7F05A",
        "card": "#FFD1B8",
        "line": "#20104F",
        "mode": "retro",
    },
    "luxe-mono": {
        "bg": "#F3F0E8",
        "ink": "#111111",
        "muted": "#595650",
        "accent": "#A4772B",
        "card": "#FCFAF5",
        "line": "#111111",
        "mode": "luxe",
    },
    "case-study": {
        "bg": "#E8EEF8",
        "ink": "#17223B",
        "muted": "#5B6880",
        "accent": "#2D63E2",
        "card": "#FFFFFF",
        "line": "#17223B",
        "mode": "case",
    },
}


def rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def font(name, size):
    paths = {
        "black": FONT_DIR / "Inter-Black.ttf",
        "bold": FONT_DIR / "Inter-Bold.ttf",
        "regular": FONT_DIR / "Inter-Regular.ttf",
        "display": FONT_DIR / "BebasNeue-Regular.ttf",
        "hand": FONT_DIR / "Caveat.ttf",
    }
    try:
        return ImageFont.truetype(str(paths[name]), size)
    except OSError:
        return ImageFont.load_default()


FONTS = {
    "display_xl": font("display", 146),
    "display": font("display", 106),
    "headline": font("black", 74),
    "title": font("black", 58),
    "body": font("regular", 39),
    "body_bold": font("bold", 39),
    "small": font("bold", 27),
    "tiny": font("regular", 23),
    "hand": font("hand", 52),
}


def clean(value, fallback=""):
    return " ".join(str(value or fallback).replace("*", "").split())


def slide_heading(slide):
    return clean(slide.get("title") or slide.get("text"), "Make the idea impossible to miss")


def slide_body(slide):
    return clean(slide.get("body") or slide.get("text") or slide.get("subtitle"))


def wrap(draw, text, text_font, max_width):
    words = clean(text).split()
    lines = []
    current = []
    for word in words:
        candidate = " ".join(current + [word])
        if draw.textbbox((0, 0), candidate, font=text_font)[2] <= max_width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


def draw_text_block(draw, text, xy, text_font, fill, max_width, spacing=14, max_lines=None):
    x, y = xy
    lines = wrap(draw, text, text_font, max_width)
    if max_lines:
        lines = lines[:max_lines]
    box = draw.textbbox((0, 0), "Ag", font=text_font)
    line_height = box[3] - box[1] + spacing
    for line in lines:
        draw.text((x, y), line, font=text_font, fill=fill)
        y += line_height
    return y


def draw_footer(draw, config, theme, index, total):
    handle = clean(config.get("profile", {}).get("handle"), "@postbandit")
    footer_background = rgb(theme["ink"]) if theme["mode"] == "retro" else rgb(theme["bg"])
    footer_color = rgb(theme["accent"]) if theme["mode"] == "retro" else rgb(theme["ink"])
    line_color = rgb(theme["accent"]) if theme["mode"] == "retro" else rgb(theme["line"])
    # Keep decorative background geometry from crossing the handle and counter.
    draw.rectangle((0, HEIGHT - 105, WIDTH, HEIGHT), fill=footer_background)
    draw.line((PAD, HEIGHT - 88, WIDTH - PAD, HEIGHT - 88), fill=line_color, width=2)
    draw.text((PAD, HEIGHT - 67), handle, font=FONTS["tiny"], fill=footer_color)
    counter = f"{index:02d} / {total:02d}"
    counter_width = draw.textbbox((0, 0), counter, font=FONTS["small"])[2]
    draw.text((WIDTH - PAD - counter_width, HEIGHT - 70), counter, font=FONTS["small"], fill=footer_color)


def draw_editorial_background(draw, theme, index):
    draw.rectangle((0, 0, 26, HEIGHT), fill=rgb(theme["accent"]))
    draw.ellipse((WIDTH - 330, -160, WIDTH + 120, 290), outline=rgb(theme["accent"]), width=8)
    draw.text((PAD, 65), "POSTBANDIT / FIELD NOTES", font=FONTS["small"], fill=rgb(theme["muted"]))
    draw.text((WIDTH - 205, 52), f"ED.{index:02d}", font=FONTS["display"], fill=rgb(theme["accent"]))


def draw_paper_background(draw, theme, index):
    for y in range(120, HEIGHT - 100, 58):
        draw.line((0, y, WIDTH, y), fill=(191, 211, 185), width=2)
    draw.line((116, 0, 116, HEIGHT), fill=(235, 137, 119), width=3)
    draw.rounded_rectangle((70, 46, 330, 112), radius=8, fill=rgb(theme["accent"]))
    draw.text((92, 61), f"NOTE {index:02d}", font=FONTS["small"], fill=(255, 255, 255))


def draw_brutalist_background(draw, theme, index):
    draw.rectangle((0, 0, WIDTH, 86), fill=rgb(theme["ink"]))
    draw.text((PAD, 24), "POSTBANDIT SIGNAL", font=FONTS["small"], fill=rgb(theme["bg"]))
    draw.rectangle((WIDTH - 210, 0, WIDTH, 86), fill=rgb(theme["accent"]))
    draw.text((WIDTH - 157, 22), f"{index:02d}", font=FONTS["title"], fill=(255, 255, 255))
    for x in range(-150, WIDTH, 210):
        draw.line((x, HEIGHT - 145, x + 145, HEIGHT), fill=rgb(theme["ink"]), width=8)


def draw_data_background(draw, theme, index):
    draw.ellipse((-180, -160, 440, 460), fill=(196, 240, 216))
    draw.ellipse((WIDTH - 250, HEIGHT - 310, WIDTH + 160, HEIGHT + 100), fill=(255, 210, 195))
    draw.rounded_rectangle((PAD, 52, PAD + 220, 110), radius=29, fill=rgb(theme["ink"]))
    draw.text((PAD + 29, 68), f"INSIGHT {index:02d}", font=FONTS["small"], fill=(255, 255, 255))


def draw_glass_background(image, draw, theme, index):
    top = (26, 36, 85)
    bottom = (79, 38, 104)
    for y in range(HEIGHT):
        ratio = y / HEIGHT
        color = tuple(int(top[channel] + (bottom[channel] - top[channel]) * ratio) for channel in range(3))
        draw.line((0, y, WIDTH, y), fill=color)
    draw.ellipse((-220, -120, 530, 630), fill=(49, 195, 210))
    draw.ellipse((650, 680, 1320, 1400), fill=(190, 70, 219))
    veil = Image.new("RGBA", image.size, (9, 16, 48, 105))
    image.paste(Image.alpha_composite(image.convert("RGBA"), veil).convert("RGB"))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((PAD, 52, PAD + 260, 112), radius=30, fill=(255, 255, 255), outline=rgb(theme["accent"]), width=2)
    draw.text((PAD + 31, 69), f"AURORA / {index:02d}", font=FONTS["small"], fill=(24, 32, 70))
    return draw


def draw_retro_background(draw, theme, index):
    draw.ellipse((WIDTH - 330, -120, WIDTH + 130, 340), fill=rgb(theme["accent"]), outline=rgb(theme["ink"]), width=7)
    draw.ellipse((WIDTH - 240, -30, WIDTH + 40, 250), outline=rgb(theme["ink"]), width=5)
    draw.rectangle((0, HEIGHT - 210, WIDTH, HEIGHT), fill=rgb(theme["ink"]))
    for x in range(-200, WIDTH + 200, 110):
        draw.line((WIDTH // 2, HEIGHT - 210, x, HEIGHT), fill=(255, 106, 61), width=3)
    draw.text((PAD, 54), "POSTBANDIT / TOMORROW FILE", font=FONTS["small"], fill=rgb(theme["ink"]))
    draw.text((WIDTH - 190, 63), f"{index:02d}", font=FONTS["display"], fill=rgb(theme["ink"]))


def draw_luxe_background(draw, theme, index):
    draw.rectangle((0, 0, WIDTH, 22), fill=rgb(theme["ink"]))
    draw.line((PAD, 130, WIDTH - PAD, 130), fill=rgb(theme["accent"]), width=3)
    draw.text((PAD, 62), "POSTBANDIT JOURNAL", font=FONTS["small"], fill=rgb(theme["ink"]))
    marker = f"VOL. 01  /  {index:02d}"
    marker_width = draw.textbbox((0, 0), marker, font=FONTS["tiny"])[2]
    draw.text((WIDTH - PAD - marker_width, 67), marker, font=FONTS["tiny"], fill=rgb(theme["muted"]))


def draw_case_background(draw, theme, index):
    draw.rectangle((0, 0, WIDTH, 150), fill=rgb(theme["ink"]))
    draw.text((PAD, 48), "CASE STUDY", font=FONTS["title"], fill=(255, 255, 255))
    draw.rounded_rectangle((WIDTH - 225, 44, WIDTH - PAD, 106), radius=31, fill=rgb(theme["accent"]))
    draw.text((WIDTH - 187, 62), f"STEP {index:02d}", font=FONTS["small"], fill=(255, 255, 255))
    draw.line((PAD, HEIGHT - 155, WIDTH - PAD, HEIGHT - 155), fill=(184, 197, 224), width=3)


def draw_background(draw, theme, index):
    mode = theme["mode"]
    if mode == "editorial":
        draw_editorial_background(draw, theme, index)
    elif mode == "paper":
        draw_paper_background(draw, theme, index)
    elif mode == "brutalist":
        draw_brutalist_background(draw, theme, index)
    elif mode == "data":
        draw_data_background(draw, theme, index)
    elif mode == "retro":
        draw_retro_background(draw, theme, index)
    elif mode == "luxe":
        draw_luxe_background(draw, theme, index)
    elif mode == "case":
        draw_case_background(draw, theme, index)


def draw_hook(draw, slide, theme):
    heading = slide_heading(slide)
    subtitle = clean(slide.get("subtitle"), "A practical breakdown worth saving.")
    mode = theme["mode"]

    if mode == "paper":
        draw.polygon([(65, 235), (980, 190), (1010, 905), (92, 950)], fill=rgb(theme["card"]))
        draw_text_block(draw, heading, (145, 320), FONTS["headline"], rgb(theme["ink"]), 770, 18, 6)
        draw.text((145, 760), subtitle, font=FONTS["hand"], fill=rgb(theme["accent"]))
        draw.arc((690, 720, 930, 930), 205, 350, fill=rgb(theme["accent"]), width=8)
    elif mode == "brutalist":
        draw.rectangle((55, 185, WIDTH - 55, 970), fill=rgb(theme["card"]), outline=rgb(theme["ink"]), width=8)
        draw.rectangle((85, 220, 350, 276), fill=rgb(theme["accent"]))
        draw.text((104, 231), "STOP SCROLLING", font=FONTS["small"], fill=(255, 255, 255))
        draw_text_block(draw, heading.upper(), (100, 335), FONTS["display_xl"], rgb(theme["ink"]), 820, 8, 5)
        draw.rectangle((86, 865, 910, 940), fill=rgb(theme["ink"]))
        draw.text((112, 882), subtitle.upper(), font=FONTS["small"], fill=rgb(theme["bg"]))
    elif mode == "data":
        draw.rounded_rectangle((70, 220, WIDTH - 70, 990), radius=42, fill=rgb(theme["card"]), outline=(171, 221, 194), width=3)
        draw.text((125, 275), "THE QUICK READ", font=FONTS["small"], fill=rgb(theme["accent"]))
        draw_text_block(draw, heading, (125, 360), FONTS["headline"], rgb(theme["ink"]), 775, 18, 6)
        draw.rounded_rectangle((125, 815, 850, 900), radius=18, fill=(224, 247, 233))
        draw.text((158, 838), subtitle, font=FONTS["small"], fill=rgb(theme["muted"]))
    elif mode == "glass":
        draw.rounded_rectangle((65, 210, WIDTH - 65, 1010), radius=52, fill=rgb(theme["card"]), outline=rgb(theme["line"]), width=3)
        draw.text((125, 270), "ONE IDEA / ONE SWIPE", font=FONTS["small"], fill=rgb(theme["accent"]))
        draw_text_block(draw, heading, (125, 370), FONTS["headline"], rgb(theme["ink"]), 790, 18, 6)
        draw.rounded_rectangle((125, 830, 875, 915), radius=42, fill=(255, 255, 255))
        draw_text_block(draw, subtitle, (165, 852), FONTS["small"], (31, 41, 82), 670, 8, 2)
    elif mode == "retro":
        draw.text((PAD, 245), "THE NEXT", font=FONTS["display"], fill=rgb(theme["accent"]))
        draw_text_block(draw, heading.upper(), (PAD, 355), FONTS["display_xl"], rgb(theme["ink"]), 855, 3, 5)
        draw.rectangle((PAD, 880, WIDTH - PAD, 965), fill=rgb(theme["accent"]), outline=rgb(theme["ink"]), width=5)
        draw_text_block(draw, subtitle.upper(), (PAD + 34, 905), FONTS["small"], rgb(theme["ink"]), 790, 7, 2)
    elif mode == "luxe":
        draw.text((PAD, 250), "PERSPECTIVE", font=FONTS["small"], fill=rgb(theme["accent"]))
        draw_text_block(draw, heading, (PAD, 355), FONTS["headline"], rgb(theme["ink"]), 850, 20, 6)
        draw.line((PAD, 850, PAD + 155, 850), fill=rgb(theme["accent"]), width=6)
        draw_text_block(draw, subtitle, (PAD, 905), FONTS["body"], rgb(theme["muted"]), 730, 15, 3)
    elif mode == "case":
        draw.rounded_rectangle((65, 220, WIDTH - 65, 1010), radius=28, fill=rgb(theme["card"]), outline=(184, 197, 224), width=3)
        draw.text((125, 280), "THE OUTCOME", font=FONTS["small"], fill=rgb(theme["accent"]))
        draw_text_block(draw, heading, (125, 375), FONTS["headline"], rgb(theme["ink"]), 790, 18, 6)
        draw.rounded_rectangle((125, 820, 860, 920), radius=18, fill=(232, 238, 252))
        draw_text_block(draw, subtitle, (160, 846), FONTS["small"], rgb(theme["muted"]), 665, 8, 2)
    else:
        draw.text((PAD, 280), "THE", font=FONTS["display"], fill=rgb(theme["accent"]))
        draw_text_block(draw, heading.upper(), (PAD, 380), FONTS["display_xl"], rgb(theme["ink"]), 865, 4, 5)
        draw.line((PAD, 910, 505, 910), fill=rgb(theme["accent"]), width=12)
        draw_text_block(draw, subtitle, (PAD, 955), FONTS["body"], rgb(theme["muted"]), 720, 12, 3)


def draw_body(draw, slide, theme, index):
    heading = slide_heading(slide)
    bullets = [clean(item) for item in (slide.get("bullets") or []) if clean(item)]
    body = slide_body(slide)
    mode = theme["mode"]

    if mode == "brutalist":
        draw.rectangle((55, 160, WIDTH - 55, 1085), fill=rgb(theme["card"]), outline=rgb(theme["ink"]), width=8)
        draw.text((90, 205), f"0{index}", font=FONTS["display_xl"], fill=rgb(theme["accent"]))
        y = draw_text_block(draw, heading.upper(), (300, 245), FONTS["display"], rgb(theme["ink"]), 660, 8, 4) + 35
    elif mode == "paper":
        draw.polygon([(72, 190), (988, 220), (950, 1080), (95, 1050)], fill=rgb(theme["card"]))
        draw.text((125, 235), f"#{index}", font=FONTS["hand"], fill=rgb(theme["accent"]))
        y = draw_text_block(draw, heading, (125, 330), FONTS["title"], rgb(theme["ink"]), 790, 16, 4) + 45
    elif mode == "data":
        draw.rounded_rectangle((70, 180, WIDTH - 70, 1080), radius=38, fill=rgb(theme["card"]), outline=(171, 221, 194), width=3)
        draw.ellipse((115, 230, 235, 350), fill=rgb(theme["accent"]))
        number = str(index)
        number_box = draw.textbbox((0, 0), number, font=FONTS["title"])
        draw.text((175 - (number_box[2] - number_box[0]) / 2, 249), number, font=FONTS["title"], fill=(255, 255, 255))
        y = draw_text_block(draw, heading, (285, 245), FONTS["title"], rgb(theme["ink"]), 650, 15, 4) + 50
    elif mode == "glass":
        draw.rounded_rectangle((65, 190, WIDTH - 65, 1080), radius=48, fill=rgb(theme["card"]), outline=rgb(theme["line"]), width=3)
        draw.text((120, 245), f"0{index}", font=FONTS["display_xl"], fill=rgb(theme["accent"]))
        y = draw_text_block(draw, heading, (320, 285), FONTS["title"], rgb(theme["ink"]), 610, 15, 4) + 55
    elif mode == "retro":
        draw.rectangle((55, 180, WIDTH - 55, 1060), fill=rgb(theme["card"]), outline=rgb(theme["ink"]), width=7)
        draw.ellipse((90, 220, 260, 390), fill=rgb(theme["accent"]), outline=rgb(theme["ink"]), width=5)
        draw.text((135, 250), str(index), font=FONTS["title"], fill=rgb(theme["ink"]))
        y = draw_text_block(draw, heading.upper(), (300, 245), FONTS["display"], rgb(theme["ink"]), 650, 6, 4) + 45
    elif mode == "luxe":
        draw.text((PAD, 205), f"0{index}", font=FONTS["display_xl"], fill=rgb(theme["accent"]))
        y = draw_text_block(draw, heading, (PAD, 390), FONTS["headline"], rgb(theme["ink"]), 840, 18, 4) + 55
    elif mode == "case":
        draw.rounded_rectangle((65, 215, WIDTH - 65, 1050), radius=28, fill=rgb(theme["card"]), outline=(184, 197, 224), width=3)
        labels = ["CONTEXT", "CHALLENGE", "DECISION", "EXECUTION", "RESULT"]
        label = labels[min(max(index - 2, 0), len(labels) - 1)]
        draw.rounded_rectangle((115, 265, 345, 325), radius=30, fill=rgb(theme["accent"]))
        draw.text((145, 282), label, font=FONTS["small"], fill=(255, 255, 255))
        y = draw_text_block(draw, heading, (115, 380), FONTS["title"], rgb(theme["ink"]), 800, 16, 4) + 55
    else:
        draw.text((PAD, 205), f"0{index}", font=FONTS["display_xl"], fill=rgb(theme["accent"]))
        y = draw_text_block(draw, heading.upper(), (PAD, 385), FONTS["display"], rgb(theme["ink"]), 850, 7, 4) + 48

    if bullets:
        for number, bullet in enumerate(bullets[:4], start=1):
            draw.rounded_rectangle((125, y, 187, y + 62), radius=16, fill=rgb(theme["accent"]))
            draw.text((145, y + 12), str(number), font=FONTS["small"], fill=(255, 255, 255))
            y = draw_text_block(draw, bullet, (215, y + 7), FONTS["body"], rgb(theme["ink"]), 690, 10, 2) + 28
    elif body:
        inset_modes = {"paper", "data", "brutalist", "glass", "retro", "case"}
        draw_text_block(draw, body, (125 if mode in inset_modes else PAD, y), FONTS["body"], rgb(theme["muted"]), 790, 16, 7)


def draw_cta(draw, slide, theme):
    heading = slide_heading(slide)
    action = clean(slide.get("cta_action"), 'Comment "GUIDE" and I will DM you the link')
    mode = theme["mode"]

    if mode == "brutalist":
        draw.rectangle((55, 200, WIDTH - 55, 1030), fill=rgb(theme["ink"]))
        draw_text_block(draw, heading.upper(), (100, 285), FONTS["display_xl"], rgb(theme["bg"]), 820, 8, 5)
        draw.rectangle((100, 805, WIDTH - 100, 930), fill=rgb(theme["accent"]))
        draw_text_block(draw, action.upper(), (135, 839), FONTS["small"], (255, 255, 255), 740, 8, 2)
    elif mode == "glass":
        draw.rounded_rectangle((65, 220, WIDTH - 65, 1010), radius=52, fill=rgb(theme["card"]), outline=rgb(theme["line"]), width=3)
        draw.text((125, 280), "SAVE THIS SYSTEM", font=FONTS["small"], fill=rgb(theme["accent"]))
        draw_text_block(draw, heading, (125, 380), FONTS["headline"], rgb(theme["ink"]), 790, 18, 5)
        draw.rounded_rectangle((125, 800, WIDTH - 125, 920), radius=60, fill=(255, 255, 255))
        draw_text_block(draw, action, (165, 833), FONTS["small"], (31, 41, 82), 670, 8, 2)
    elif mode == "retro":
        draw.rectangle((55, 210, WIDTH - 55, 1010), fill=rgb(theme["ink"]), outline=rgb(theme["accent"]), width=8)
        draw_text_block(draw, heading.upper(), (100, 315), FONTS["display_xl"], rgb(theme["accent"]), 820, 5, 5)
        draw.rectangle((100, 790, WIDTH - 100, 920), fill=rgb(theme["accent"]))
        draw_text_block(draw, action.upper(), (140, 827), FONTS["small"], rgb(theme["ink"]), 720, 8, 2)
    elif mode == "luxe":
        draw.rectangle((75, 230, WIDTH - 75, 1000), fill=rgb(theme["ink"]))
        draw.text((125, 295), "A FINAL NOTE", font=FONTS["small"], fill=rgb(theme["accent"]))
        draw_text_block(draw, heading, (125, 390), FONTS["headline"], (255, 255, 255), 780, 18, 5)
        draw.line((125, 785, WIDTH - 125, 785), fill=rgb(theme["accent"]), width=3)
        draw_text_block(draw, action, (125, 835), FONTS["small"], (230, 226, 216), 760, 9, 2)
    else:
        card_box = (75, 230, WIDTH - 75, 1000)
        draw.rounded_rectangle(card_box, radius=40 if mode == "data" else 14, fill=rgb(theme["card"]), outline=rgb(theme["line"]), width=3)
        draw.text((125, 290), "YOUR NEXT MOVE", font=FONTS["small"], fill=rgb(theme["accent"]))
        draw_text_block(draw, heading, (125, 375), FONTS["headline"], rgb(theme["ink"]), 780, 16, 5)
        draw.rounded_rectangle((125, 795, WIDTH - 125, 910), radius=24, fill=rgb(theme["accent"]))
        draw_text_block(draw, action, (165, 825), FONTS["small"], (255, 255, 255), 690, 8, 2)


def render(config, slide, index, total):
    theme = THEMES.get(config.get("template_id"), THEMES["editorial-sun"])
    image = Image.new("RGB", (WIDTH, HEIGHT), rgb(theme["bg"]))
    draw = ImageDraw.Draw(image)
    if theme["mode"] == "glass":
        draw = draw_glass_background(image, draw, theme, index)
    else:
        draw_background(draw, theme, index)
    slide_type = slide.get("type", "body")
    if slide_type == "hook":
        draw_hook(draw, slide, theme)
    elif slide_type == "cta":
        draw_cta(draw, slide, theme)
    else:
        draw_body(draw, slide, theme, index)
    draw_footer(draw, config, theme, index, total)
    return image


def render_carousel(directory):
    directory = Path(directory)
    with (directory / "config.json").open(encoding="utf-8") as file:
        config = json.load(file)
    slides = config.get("slides", [])
    for index, slide in enumerate(slides, start=1):
        image = render(config, slide, index, len(slides))
        image.save(directory / f"slide_{index}.png", "PNG")
    print(f"Rendered {len(slides)} {config.get('template_id', 'modern')} slides")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 render_modern.py <carousel-directory>")
    render_carousel(sys.argv[1])
