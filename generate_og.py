#!/usr/bin/env python3
"""
Generate clean, editorial Open Graph images for vRSS blog posts.

Input:  blog/*.html
Output: assets/og/<post>.png
Also injects Open Graph + Twitter metadata into each post.

Requires: Pillow
    pip install pillow
"""

from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from datetime import datetime, timezone
import html
import os
import re

from PIL import Image, ImageDraw, ImageFont


SITE_URL = os.getenv(
    "VRSS_SITE_URL",
    "https://blog.vorcinex.yocrrz.is-a.dev",
).rstrip("/")

BLOG_DIR = Path("blog")
OG_DIR = Path("assets/og")

WIDTH, HEIGHT = 1200, 630

# Quiet editorial palette
PAPER = "#f6f2e8"
PAPER_SHADE = "#ebe4d5"
CARD = "#fbf9f3"
INK = "#25231f"
SOFT_INK = "#514c43"
MUTED = "#81796d"
FAINT = "#b1a897"
BORDER = "#d9d0bf"
ACCENT = "#bd583d"
ACCENT_PALE = "#ead3c8"


class MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.description = ""
        self.timestamp = ""
        self.author = ""
        self._in_author = False
        self._author_text = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs = dict(attrs)

        if tag == "meta":
            name = attrs.get("name", "").lower()
            content = attrs.get("content", "")
            if name == "blog-title":
                self.title = unescape(content)
            elif name == "description":
                self.description = unescape(content)
            elif name == "blog-timestamp":
                self.timestamp = unescape(content)

        elif tag == "div" and "author" in attrs.get("class", "").split():
            self._in_author = True

    def handle_endtag(self, tag):
        if tag.lower() == "div" and self._in_author:
            self._in_author = False
            text = re.sub(r"\s+", " ", " ".join(self._author_text)).strip()
            match = re.search(r"Published\s+by\s+(.+)$", text, re.I)
            if match:
                self.author = match.group(1).strip()
            self._author_text = []

    def handle_data(self, data):
        if self._in_author:
            self._author_text.append(data)


class BodyTextParser(HTMLParser):
    """Extract readable body text without scripts, styles, or page chrome."""

    SKIP_TAGS = {"script", "style", "svg", "noscript", "iframe", "head"}

    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.SKIP_TAGS:
            self.skip_depth += 1
        elif not self.skip_depth and tag.lower() in {"p", "br", "h1", "h2", "h3", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in self.SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
        elif not self.skip_depth and tag.lower() in {"p", "h1", "h2", "h3", "li"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip_depth:
            text = re.sub(r"\s+", " ", data).strip()
            if text:
                self.parts.append(text + " ")


def clean_text(value):
    value = unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def make_excerpt(description, body_text, limit=112):
    """
    Produce a short teaser, not a full poem or long description.
    Prefer the meta description; fall back to readable body text.
    Stop at a sensible sentence boundary when possible.
    """
    text = clean_text(description) or clean_text(body_text)
    text = re.sub(r"\s+", " ", text).strip(" \t\n\r—–-")

    if not text:
        return ""

    # Prefer a concise first sentence if it isn't excessively short.
    sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0].strip()
    if 36 <= len(sentence) <= limit:
        text = sentence
    elif len(text) > limit:
        cut = text[:limit + 1]
        # Prefer ending on a word rather than slicing through one.
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        text = cut.rstrip(" ,;:-—")

    if len(text) > limit:
        text = text[:limit].rstrip()
    if len(clean_text(description) or clean_text(body_text)) > len(text):
        text = text.rstrip(" .") + "…"
    return text


def parse_timestamp(timestamp):
    if not timestamp:
        return None
    try:
        dt = datetime.fromisoformat(timestamp)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_date(timestamp):
    dt = parse_timestamp(timestamp)
    return dt.strftime("%d %b %Y").upper() if dt else ""


def format_url(path):
    return f"{SITE_URL}/{path.as_posix().lstrip('/')}"


def get_font(paths, size):
    for path in paths:
        path = Path(path)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                pass
    return ImageFont.load_default()


def get_fonts():
    serif_regular = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf",
    ]
    serif_bold = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf",
    ]
    sans = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    mono = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf",
    ]
    return {
        "title": get_font(serif_bold, 66),
        "excerpt": get_font(serif_regular, 25),
        "brand": get_font(mono, 19),
        "label": get_font(mono, 15),
        "meta": get_font(sans, 17),
    }


def text_width(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def wrap_text(draw, text, font, max_width, max_lines=3):
    words = text.split()
    lines = []
    current = ""

    for word in words:
        candidate = word if not current else f"{current} {word}"
        if text_width(draw, candidate, font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
            if len(lines) >= max_lines:
                break

    if current and len(lines) < max_lines:
        lines.append(current)

    # If text overflowed, mark the last visible line with an ellipsis.
    consumed = " ".join(lines).split()
    if len(consumed) < len(words) and lines:
        last = lines[-1].rstrip(" .…")
        while last and text_width(draw, last + "…", font) > max_width:
            last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
        lines[-1] = last.rstrip() + "…"

    return lines


def draw_title(draw, title, font, x, y, max_width, max_lines=3):
    lines = wrap_text(draw, title, font, max_width, max_lines=max_lines)
    line_height = 79
    for line in lines:
        draw.text((x, y), line, font=font, fill=INK)
        y += line_height
    return y


def generate_image(title, description, timestamp, author, output):
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    fonts = get_fonts()

    # Double-frame editorial page.
    draw.rounded_rectangle(
        (22, 22, WIDTH - 23, HEIGHT - 23),
        radius=8,
        outline=BORDER,
        width=2,
    )
    draw.rectangle((42, 42, WIDTH - 43, HEIGHT - 43), outline="#e8e0d1", width=1)

    # Quiet abstract motif on the right: a restrained circular stamp.
    draw.ellipse((890, 135, 1115, 360), fill=PAPER_SHADE)
    draw.ellipse((925, 170, 1080, 325), outline=ACCENT, width=2)
    draw.ellipse((955, 200, 1050, 295), outline="#c9bba5", width=1)
    draw.arc((940, 185, 1065, 310), start=205, end=335, fill=ACCENT, width=5)
    draw.line((1002, 215, 1002, 280), fill=ACCENT, width=2)
    draw.line((970, 248, 1035, 248), fill=ACCENT, width=2)
    draw.ellipse((994, 240, 1010, 256), fill=ACCENT)

    # Brand row.
    draw.ellipse((76, 76, 90, 90), fill=ACCENT)
    draw.text((108, 69), "VORCINEX_STUDIO", font=fonts["brand"], fill=INK)
    label = "vRSS  /  FIELD NOTES"
    draw.text((WIDTH - 78 - text_width(draw, label, fonts["label"]), 76),
              label, font=fonts["label"], fill=MUTED)

    # Fine separator.
    draw.line((76, 117, WIDTH - 76, 117), fill=BORDER, width=2)

    # Category label and title.
    draw.text((78, 151), "A NOTE FROM THE BLOG", font=fonts["label"], fill=ACCENT)

    title_end = draw_title(
        draw,
        clean_text(title) or "Untitled",
        fonts["title"],
        x=76,
        y=190,
        max_width=780,
        max_lines=3,
    )

    # A short teaser, never a full article or poem.
    excerpt = make_excerpt(description, "")
    if excerpt:
        excerpt_lines = wrap_text(draw, excerpt, fonts["excerpt"], 740, max_lines=2)
        excerpt_y = min(max(title_end + 3, 405), 438)
        for line in excerpt_lines[:2]:
            draw.text((80, excerpt_y), line, font=fonts["excerpt"], fill=SOFT_INK)
            excerpt_y += 34

    # Footer with concise metadata only.
    draw.line((76, 518, WIDTH - 76, 518), fill=BORDER, width=2)

    date = format_date(timestamp)
    metadata = "  /  ".join(part for part in [author.strip(), date] if part)
    if metadata:
        draw.text((78, 542), metadata[:90], font=fonts["meta"], fill=MUTED)

    domain = SITE_URL.replace("https://", "").replace("http://", "").rstrip("/")
    draw.text((78, 579), domain, font=fonts["label"], fill=FAINT)

    # Small signature bar.
    draw.rounded_rectangle((WIDTH - 210, 579, WIDTH - 78, 584), radius=2, fill=ACCENT)

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", optimize=True)


GENERATED_META_NAMES = {
    "og:title", "og:description", "og:type", "og:url", "og:image",
    "og:image:width", "og:image:height", "og:site_name",
    "article:published_time", "twitter:card", "twitter:title",
    "twitter:description", "twitter:image",
}


def remove_generated_tags(content):
    names = "|".join(re.escape(name) for name in sorted(GENERATED_META_NAMES))
    pattern = re.compile(
        r"\s*<meta\s+(?:property|name)\s*=\s*(['\"])(?:" + names +
        r")\1[^>]*>\s*",
        re.IGNORECASE,
    )
    return pattern.sub("\n", content)


def inject_metadata(content, title, description, timestamp, post_url, image_url):
    content = remove_generated_tags(content)

    def esc(value):
        return html.escape(value or "", quote=True)

    tags = f"""
    <meta property="og:title" content="{esc(title)}">
    <meta property="og:description" content="{esc(description)}">
    <meta property="og:type" content="article">
    <meta property="og:url" content="{esc(post_url)}">
    <meta property="og:image" content="{esc(image_url)}">
    <meta property="og:image:width" content="1200">
    <meta property="og:image:height" content="630">
    <meta property="og:site_name" content="VORCINEX_STUDIO vRSS">
    <meta property="article:published_time" content="{esc(timestamp)}">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{esc(title)}">
    <meta name="twitter:description" content="{esc(description)}">
    <meta name="twitter:image" content="{esc(image_url)}">
"""
    match = re.search(r"</head>", content, re.IGNORECASE)
    if not match:
        raise RuntimeError("Could not find </head> in blog HTML.")
    return content[:match.start()] + tags + "\n" + content[match.start():]


def process_blog(path):
    original = path.read_text(encoding="utf-8")
    parser = MetadataParser()
    parser.feed(original)

    title = clean_text(parser.title)
    description = clean_text(parser.description)
    timestamp = parser.timestamp.strip()
    author = clean_text(parser.author)

    body_parser = BodyTextParser()
    body_parser.feed(original)
    body_text = clean_text(" ".join(body_parser.parts))

    # Keep social previews compact even if the source description is very long.
    excerpt = make_excerpt(description, body_text, limit=112)
    if not title:
        print(f"Skipping {path}: missing blog-title.")
        return False
    if not timestamp:
        print(f"Skipping {path}: missing blog-timestamp.")
        return False

    post_url = format_url(path)
    image_name = f"{path.stem}.png"
    image_path = OG_DIR / image_name
    image_url = f"{SITE_URL}/assets/og/{image_name}"

    generate_image(
        title=title,
        description=excerpt,
        timestamp=timestamp,
        author=author,
        output=image_path,
    )

    updated = inject_metadata(
        original, title, excerpt, timestamp, post_url, image_url
    )
    if updated != original:
        path.write_text(updated, encoding="utf-8")
        status = "updated"
    else:
        status = "unchanged"

    print(f"{status}: {path} -> {image_path}")
    return True


def main():
    BLOG_DIR.mkdir(parents=True, exist_ok=True)
    OG_DIR.mkdir(parents=True, exist_ok=True)
    posts = sorted(BLOG_DIR.glob("*.html"))

    if not posts:
        print("No blog posts found.")
        return

    processed = sum(1 for path in posts if process_blog(path))
    print(f"\nProcessed {processed}/{len(posts)} blog posts.")


if __name__ == "__main__":
    main()
