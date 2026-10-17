#!/usr/bin/env python3
"""Generate index.json from the published vRSS blog HTML files."""

from html.parser import HTMLParser
from pathlib import Path
from datetime import datetime, timezone
import json
import os


SITE_URL = os.getenv(
    "VRSS_SITE_URL",
    "https://blog.vorcinex.yocrrz.is-a.dev/",
).rstrip("/") + "/"

BLOG_DIR = Path("blog")
OUTPUT = Path("index.json")


class MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = None
        self.timestamp = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "meta":
            return

        attrs = dict(attrs)

        if attrs.get("name") == "blog-title":
            self.title = attrs.get("content", "")

        elif attrs.get("name") == "blog-timestamp":
            self.timestamp = attrs.get("content", "")


def parse_blog(path):
    parser = MetadataParser()
    parser.feed(path.read_text(encoding="utf-8"))

    if not parser.title or not parser.timestamp:
        return None

    try:
        dt = datetime.fromisoformat(parser.timestamp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        timestamp = dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        return None

    relative_url = path.as_posix()
    url = SITE_URL + relative_url

    return {
        "title": parser.title,
        "timestamp": timestamp,
        "url": url,
    }


def main():
    entries = []

    for path in sorted(BLOG_DIR.glob("*.html")):
        entry = parse_blog(path)

        if entry:
            entries.append(entry)

    entries.sort(key=lambda item: item["timestamp"], reverse=True)

    OUTPUT.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Generated {OUTPUT} with {len(entries)} blog entries.")


if __name__ == "__main__":
    main()
