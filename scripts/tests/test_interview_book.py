from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / "scripts" / "check_docs_sync.py"
SPEC = importlib.util.spec_from_file_location("book_checker", MODULE_PATH)
assert SPEC and SPEC.loader
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class InterviewBookTests(unittest.TestCase):
    def test_canonical_vault_passes(self) -> None:
        errors = CHECKER.vault_errors(REPO / "docs" / "ifaceoff-vault")
        self.assertEqual(errors, [])

    def test_frontmatter_requires_book_properties(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.md"
            path.write_text("---\ntitle: bad\n---\n# bad\n", encoding="utf-8")
            _, errors = CHECKER.parse_frontmatter(path)
        self.assertTrue(any("missing properties" in error for error in errors))

    def test_png_dimensions_are_read_from_header(self) -> None:
        screenshot = next(
            (REPO / "docs" / "ifaceoff-vault" / "assets" / "screenshots").glob("*.png")
        )
        self.assertEqual(CHECKER.png_size(screenshot), (1440, 900))

    def test_exactly_fifteen_flat_markdown_files(self) -> None:
        vault = REPO / "docs" / "ifaceoff-vault"
        self.assertEqual({path.name for path in vault.glob("*.md")}, CHECKER.EXPECTED_MARKDOWN)
        self.assertEqual([path for path in vault.rglob("*.md") if path.parent != vault], [])


if __name__ == "__main__":
    unittest.main()
