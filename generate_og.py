#!/usr/bin/env python3
"""
Generate minimal Open Graph images for vRSS blog posts.
Produces a clean canvas with just the title.
"""

import os
import re
import html
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SITE_URL = os.getenv("VRSS_SITE_URL", "https://yocrrz.likes-ur.mom/md").rstrip("/")
BLOG_DIR = Path("blog")
OG_DIR = Path("assets/og")
WIDTH, HEIGHT = 1200, 630

class MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.description = ""
        self.timestamp = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag.lower() == "meta":
            name = attrs.get("name", "").lower()
            content = attrs.get("content", "")
            if name == "blog-title":
                self.title = unescape(content)
            elif name == "description":
                self.description = unescape(content)
            elif name == "blog-timestamp":
                self.timestamp = unescape(content)

def clean_text(value):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(value or ""))).strip()

def get_font(size):
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf"
    ]:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

def wrap_text(draw, text, font, max_width):
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current: lines.append(current)
    return lines

def generate_image(title, output):
    image = Image.new("RGB", (WIDTH, HEIGHT), "#f6f2e8")
    draw = ImageDraw.Draw(image)
    font = get_font(72)
    
    # Wrap and center text
    lines = wrap_text(draw, title, font, WIDTH - 160)
    line_height = 85
    y = (HEIGHT - (len(lines) * line_height)) // 2
    
    for line in lines:
        box = draw.textbbox((0, 0), line, font=font)
        x = (WIDTH - (box[2] - box[0])) // 2
        draw.text((x, y), line, font=font, fill="#25231f")
        y += line_height

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", optimize=True)

def inject_metadata(content, title, description, timestamp, post_url, image_url):
    # Strip old OG/Twitter tags
    content = re.sub(r"\s*<meta\s+(?:property|name)\s*=\s*(['\"])(?:og:|article:|twitter:)[^>]*>\s*", "\n", content)
    
    tags = f"""
    <meta property="og:title" content="{html.escape(title)}">
    <meta property="og:description" content="{html.escape(description)}">
    <meta property="og:type" content="article">
    <meta property="og:url" content="{html.escape(post_url)}">
    <meta property="og:image" content="{html.escape(image_url)}">
    <meta property="article:published_time" content="{html.escape(timestamp)}">
    <meta name="twitter:card" content="summary_large_image">
"""
    # Inject right before </head>
    return re.sub(r"</head>", tags + "</head>", content, flags=re.IGNORECASE)

def process_blog(path):
    original = path.read_text(encoding="utf-8")
    parser = MetadataParser()
    parser.feed(original)

    title = clean_text(parser.title)
    desc = clean_text(parser.description)
    ts = parser.timestamp.strip()

    if not title or not ts:
        print(f"Skipped (missing title or timestamp): {path}")
        return False

    image_path = OG_DIR / f"{path.stem}.png"
    generate_image(title, image_path)

    post_url = f"{SITE_URL}/{path.name}"
    image_url = f"{SITE_URL}/assets/og/{image_path.name}"
    
    updated = inject_metadata(original, title, desc, ts, post_url, image_url)
    if updated != original:
        path.write_text(updated, encoding="utf-8")
        
    print(f"Processed: {path} -> {image_path}")
    return True

def main():
    BLOG_DIR.mkdir(parents=True, exist_ok=True)
    posts = sorted(BLOG_DIR.glob("*.html"))
    if not posts:
        print("No blog posts found.")
        return

    processed = sum(1 for path in posts if process_blog(path))
    print(f"\nProcessed {processed}/{len(posts)} blog posts.")

if __name__ == "__main__":
    main()