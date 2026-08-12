from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / "scripts" / "build_project_facts.py"
SPEC = importlib.util.spec_from_file_location("build_project_facts", MODULE_PATH)
assert SPEC and SPEC.loader
BUILDER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BUILDER
SPEC.loader.exec_module(BUILDER)


class ProjectFactsBaselineTests(unittest.TestCase):
    def test_source_commit_uses_runtime_paths_instead_of_docs_head(self) -> None:
        with patch.object(BUILDER, "git", return_value="abc1234") as mocked_git:
            self.assertEqual(BUILDER.source_commit(), "abc1234")

        mocked_git.assert_called_once_with(
            "log",
            "-1",
            "--format=%H",
            "HEAD",
            "--",
            *BUILDER.FACT_SOURCE_PATHS,
        )
        self.assertTrue(all(not path.startswith("docs/") for path in BUILDER.FACT_SOURCE_PATHS))


if __name__ == "__main__":
    unittest.main()
