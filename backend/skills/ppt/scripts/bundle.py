#!/usr/bin/env python3
"""Bundle PPT HTML into a standalone file by inlining all ./assets/ references.

Usage:
    python3 bundle.py <html_file>

Resolves ./assets/ paths relative to the skill directory (this script's parent.parent),
reads CSS/JS content, inlines them, and overwrites the original file.
No external dependencies — uses only Python stdlib.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = SKILL_DIR / "assets"

LINK_RE = re.compile(
    r'<link\s[^>]*href="(\./assets/[^"]+)"[^>]*/?>',
    re.IGNORECASE,
)
SCRIPT_RE = re.compile(
    r'<script\s[^>]*src="(\./assets/[^"]+)"[^>]*>\s*</script>',
    re.IGNORECASE,
)


def resolve_asset(relative_path: str) -> str | None:
    """Resolve ./assets/xxx to file content."""
    clean = relative_path.removeprefix("./assets/")
    file_path = ASSETS_DIR / clean
    if file_path.exists():
        return file_path.read_text(encoding="utf-8", errors="ignore")
    print(f"WARNING: asset not found: {file_path}", file=sys.stderr)
    return None


def inline_assets(html: str) -> str:
    """Replace external ./assets/ link/script tags with inline content."""

    def replace_link(match: re.Match) -> str:
        content = resolve_asset(match.group(1))
        if content is None:
            return match.group(0)
        return f"<style>\n{content}\n</style>"

    def replace_script(match: re.Match) -> str:
        content = resolve_asset(match.group(1))
        if content is None:
            return match.group(0)
        return f"<script>\n{content}\n</script>"

    result = LINK_RE.sub(replace_link, html)
    result = SCRIPT_RE.sub(replace_script, result)
    return result


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <html_file>", file=sys.stderr)
        sys.exit(1)

    html_path = Path(sys.argv[1])
    if not html_path.exists():
        print(f"ERROR: file not found: {html_path}", file=sys.stderr)
        sys.exit(1)

    html = html_path.read_text(encoding="utf-8")
    bundled = inline_assets(html)
    html_path.write_text(bundled, encoding="utf-8")

    original_size = len(html.encode("utf-8"))
    bundled_size = len(bundled.encode("utf-8"))
    print(f"OK: {html_path.name} bundled ({original_size // 1024}KB -> {bundled_size // 1024}KB)")


if __name__ == "__main__":
    main()
