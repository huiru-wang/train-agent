#!/usr/bin/env python3
"""Atomically bundle and save PPT HTML output.

This script is called by the Agent via terminal tool. It:
1. Bundles HTML by inlining ./assets/ references
2. Saves to the files directory
3. Outputs JSON result for the Agent

Usage:
    python3 save_and_output.py '<JSON_ARGS>'
    python3 save_and_output.py --stdin < <json_file>

JSON_ARGS format:
    {
        "workspace_id": "uuid",
        "content": "<HTML string>",
        "filename": "output.html"
    }
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = SKILL_DIR / "assets"

LINK_RE = __import__("re").compile(
    r'<link\s[^>]*href="(\./assets/[^"]+)"[^>]*/?>',
    __import__("re").IGNORECASE,
)
SCRIPT_RE = __import__("re").compile(
    r'<script\s[^>]*src="(\./assets/[^"]+)"[^>]*>\s*</script>',
    __import__("re").IGNORECASE,
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

    def replace_link(match):
        content = resolve_asset(match.group(1))
        if content is None:
            return match.group(0)
        return f"<style>\n{content}\n</style>"

    def replace_script(match):
        content = resolve_asset(match.group(1))
        if content is None:
            return match.group(0)
        return f"<script>\n{content}\n</script>"

    result = LINK_RE.sub(replace_link, html)
    result = SCRIPT_RE.sub(replace_script, result)
    return result


def main():
    # Parse arguments
    if len(sys.argv) >= 2 and sys.argv[1] == "--stdin":
        # Read JSON from stdin
        json_str = sys.stdin.read()
    elif len(sys.argv) >= 2:
        json_str = sys.argv[1]
    else:
        print("ERROR: No input provided", file=sys.stderr)
        print("Usage: save_and_output.py '<JSON_ARGS>'", file=sys.stderr)
        sys.exit(1)

    try:
        args = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    workspace_id = args.get("workspace_id", "default")
    html_content = args.get("content", "")
    filename = args.get("filename", "output.html")

    if not html_content:
        print("ERROR: No content provided", file=sys.stderr)
        sys.exit(1)

    # Bundle the HTML
    bundled = inline_assets(html_content)

    # Determine save path
    # Files are saved under base_dir/workspace_id/outputs/
    base_dir = os.environ.get("FILES_BASE_DIR", "/tmp/train-agent-files")
    file_path = Path(base_dir) / workspace_id / "outputs" / filename

    # Save
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(bundled, encoding="utf-8")

    original_size = len(html_content.encode("utf-8"))
    bundled_size = len(bundled.encode("utf-8"))

    # Output result as JSON
    result = {
        "success": True,
        "file_path": str(file_path),
        "filename": filename,
        "size": bundled_size,
        "original_size": original_size,
        "message": f"产出已保存: {filename} ({original_size // 1024}KB -> {bundled_size // 1024}KB)。用户可在右侧产出面板查看和下载。"
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
