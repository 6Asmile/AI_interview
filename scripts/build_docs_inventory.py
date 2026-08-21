#!/usr/bin/env python3
"""Check the deliberately small, flat iFaceoff interview-book inventory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from check_docs_sync import EXPECTED_MARKDOWN, vault_errors


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VAULT = ROOT / "docs" / "ifaceoff-vault"


def inventory(vault: Path) -> dict[str, object]:
    markdown = sorted(vault.glob("*.md"))
    screenshots = sorted((vault / "assets" / "screenshots").glob("*.png"))
    texts = [path.read_text(encoding="utf-8") for path in markdown]
    return {
        "markdown_files": [path.name for path in markdown],
        "markdown_count": len(markdown),
        "characters": sum(map(len, texts)),
        "mermaid_diagrams": sum(text.count("```mermaid") for text in texts),
        "screenshot_references": sum(text.count("assets/screenshots/") for text in texts),
        "screenshots": [path.name for path in screenshots],
        "screenshot_count": len(screenshots),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    vault = args.vault.resolve()
    result = inventory(vault)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"Vault inventory: {result['markdown_count']} Markdown, "
            f"{result['characters']} characters, {result['mermaid_diagrams']} Mermaid, "
            f"{result['screenshot_count']} screenshots"
        )
    if not args.check:
        return 0
    errors = []
    if set(result["markdown_files"]) != EXPECTED_MARKDOWN:
        errors.append("Markdown inventory is not the canonical 15-file book")
    errors.extend(vault_errors(vault))
    if errors:
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
