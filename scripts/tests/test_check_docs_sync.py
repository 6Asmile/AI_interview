from __future__ import annotations

import argparse
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / "scripts" / "check_docs_sync.py"
SPEC = importlib.util.spec_from_file_location("check_docs_sync", MODULE_PATH)
assert SPEC and SPEC.loader
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


def arguments(files: list[str]) -> argparse.Namespace:
    return argparse.Namespace(
        staged=False, base=None, head=None, files=files, check_vault=False, vault=None
    )


class DocumentationSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = CHECKER.load_config()

    def test_docs_only_change_passes(self) -> None:
        self.assertEqual(
            CHECKER.sync_errors(
                arguments(["docs/ifaceoff-vault/04-卷三-Career与Resume实现.md"]),
                ["docs/ifaceoff-vault/04-卷三-Career与Resume实现.md"],
                self.config,
            ),
            [],
        )

    def test_resume_change_requires_canonical_volume(self) -> None:
        changed = [
            "ai_interview_backend/resumes/models.py",
            self.config["changelog"],
        ]
        errors = CHECKER.sync_errors(arguments(changed), changed, self.config)
        self.assertTrue(any("04-卷三-Career与Resume实现.md" in error for error in errors))

    def test_cross_domain_change_requires_both_volumes(self) -> None:
        changed = [
            "ai_interview_backend/resumes/models.py",
            "ai_interview_backend/interviews/models.py",
            "docs/ifaceoff-vault/04-卷三-Career与Resume实现.md",
            self.config["changelog"],
        ]
        errors = CHECKER.sync_errors(arguments(changed), changed, self.config)
        self.assertTrue(any("05-卷四-Interview与评估实现.md" in error for error in errors))

    def test_wrong_section_is_rejected(self) -> None:
        changed = [
            "ai_interview_backend/resumes/models.py",
            "docs/ifaceoff-vault/04-卷三-Career与Resume实现.md",
            self.config["changelog"],
        ]
        with patch.object(CHECKER, "changed_new_lines", return_value={1}):
            errors = CHECKER.sync_errors(arguments(changed), changed, self.config)
        self.assertTrue(any("no diff falls inside mapped sections" in error for error in errors))

    def test_missing_changelog_is_rejected(self) -> None:
        changed = [
            "ai_interview_backend/knowledge/models.py",
            "docs/ifaceoff-vault/06-卷五-Agent-RAG与Model-Gateway实现.md",
        ]
        errors = CHECKER.sync_errors(arguments(changed), changed, self.config)
        self.assertTrue(any("12-项目变更日志.md" in error for error in errors))

    def test_all_current_sources_have_mapping(self) -> None:
        raw = CHECKER.run_git(
            "ls-files", "--cached", "--others", "--exclude-standard", "-z", binary=True
        )
        paths = [
            item.decode("utf-8", errors="surrogateescape").replace("\\", "/")
            for item in raw.split(b"\0")
            if item
        ]
        unmapped = [
            path
            for path in paths
            if CHECKER.relevant_source(path, self.config)
            and CHECKER.first_rule(path, self.config) is None
        ]
        self.assertEqual(unmapped, [])

    def test_specialized_celery_rule_wins_before_backend_rule(self) -> None:
        rule = CHECKER.first_rule(
            "ai_interview_backend/ai_interview_backend/settings.py",
            self.config,
        )
        self.assertEqual(rule["name"], "celery-topology")

    def test_specialized_platform_events_rule_wins_before_staff_rule(self) -> None:
        rule = CHECKER.first_rule(
            "ai_interview_backend/staff_admin/platform_views.py",
            self.config,
        )
        self.assertEqual(rule["name"], "platform-events-admin")

    def test_verified_commit_accepts_current_head_as_reachable(self) -> None:
        head = CHECKER.run_git("rev-parse", "HEAD").strip()
        self.assertTrue(CHECKER.commit_is_reachable(head, head))
        self.assertFalse(CHECKER.commit_is_reachable("not-a-commit", head))


if __name__ == "__main__":
    unittest.main()
