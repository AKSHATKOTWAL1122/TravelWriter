"""Tests for scripts/audit.py (spec 00.1). Run from the repo root:

    python3 -m unittest discover scripts

Each test builds a small throwaway git repo that passes the audit, adds exactly one
problem, and checks that it's reported with a non-zero exit code. Fake secrets are
assembled at runtime so this file never trips the real audit.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

AUDIT = Path(__file__).resolve().parent / "audit.py"

# Git without the developer's own config (signing, hooks, default branch).
GIT_ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}

README = """\
# Specs roadmap

### 01 Foundation
| Spec | What | Status |
|---|---|---|
| 01.1 | Setup ([spec](01-foundation/01.1-setup.md)) | done |
| 01.2 | Settings ([spec](01-foundation/01.2-settings.md)) | approved |
| 01.3 | Database | proposed |
"""

SETUP_SPEC = """\
# 01.1 Setup

Feature: 01 Foundation
Depends on: none

Goal: a project that starts.

Behavior
- The app starts.

Acceptance
- [x] The app starts.

Out of scope: everything else.
Later: none

Consistency check (vs. all specs + CLAUDE.md)
- Checked against: 01.2
- Findings: none

Changes (after build, see CLAUDE.md rule 5)
- none
"""

SETTINGS_SPEC = """\
# 01.2 Settings

Feature: 01 Foundation
Depends on: 01.1

Goal: settings from the environment.

Acceptance
- [ ] Settings load.

Changes (after build, see CLAUDE.md rule 5)
- none
"""

ISSUES = """\
# Consistency issues

## Open

| ID | Type | Clash | Proposed fix |
|---|---|---|---|

## Resolved

| ID | Clash | Resolution |
|---|---|---|
| ISSUE-001 | Setup before settings? | Yes (01.1, then 01.2). |
| ISSUE-002 | Where do settings live? | One class (01.2). |
"""

CLAUDE_MD = """\
# Demo

Settings live in `backend/storymaker/config.py`; names go in `backend/.env.example`.
"""

CONFIG = """\
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STORYMAKER_")

    gemini_api_key: str = Field(default="", validation_alias="GEMINI_API_KEY")
    model: str = "demo-model"
"""

ENV_EXAMPLE = """\
# Committed: names only.
GEMINI_API_KEY=
# STORYMAKER_MODEL=demo-model
"""

FILES = {
    "specs/README.md": README,
    "specs/01-foundation/01.1-setup.md": SETUP_SPEC,
    "specs/01-foundation/01.2-settings.md": SETTINGS_SPEC,
    "specs/ISSUES.md": ISSUES,
    "specs/_template.md": "# FF.N Title\n",
    "CLAUDE.md": CLAUDE_MD,
    "backend/storymaker/config.py": CONFIG,
    "backend/.env.example": ENV_EXAMPLE,
}


class AuditTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)
        self.git("init", "-q", "-b", "main")
        for path, text in FILES.items():
            self.write(path, text)
        self.commit()

    def git(self, *args):
        subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", *args],
            cwd=self.repo, env=GIT_ENV, check=True, capture_output=True,
        )

    def write(self, path, text):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def edit(self, path, old, new):
        text = (self.repo / path).read_text()
        self.assertIn(old, text)
        self.write(path, text.replace(old, new, 1))

    def commit(self):
        self.git("add", "--all", "--force")  # --force: a global gitignore mustn't hide test files
        self.git("commit", "-q", "--allow-empty", "-m", "change")

    def audit(self, *args):
        return subprocess.run(
            [sys.executable, str(AUDIT), *args], cwd=self.repo, env=GIT_ENV, capture_output=True, text=True
        )

    def assertPasses(self):
        self.commit()
        result = self.audit()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def assertReported(self, *fragments):
        self.commit()
        result = self.audit()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        for fragment in fragments:
            self.assertIn(fragment, result.stdout)
        return result.stdout


class CleanRepo(AuditTest):
    def test_clean_repo_passes(self):
        self.assertIn("no findings", self.assertPasses())

    def test_checks_the_given_revision_not_the_working_tree(self):
        self.git("rm", "-q", "specs/01-foundation/01.2-settings.md")
        self.commit()

        self.assertEqual(self.audit().returncode, 1)
        self.assertEqual(self.audit("--rev", "HEAD~1").returncode, 0)

    def test_unknown_revision_fails_to_run(self):
        self.assertEqual(self.audit("--rev", "no-such-branch").returncode, 2)


class RoadmapAndSpecFiles(AuditTest):
    def test_linked_spec_file_must_exist(self):
        self.git("rm", "-q", "specs/01-foundation/01.2-settings.md")
        self.assertReported("01.2 links to specs/01-foundation/01.2-settings.md, which doesn't exist")

    def test_every_spec_file_is_linked(self):
        self.write("specs/01-foundation/01.3-database.md", "# 01.3 Database\n")
        self.assertReported("specs/01-foundation/01.3-database.md: spec file isn't linked")

    def test_written_or_later_status_needs_a_file(self):
        for status in ("written", "approved", "done", "changing"):
            with self.subTest(status=status):
                self.edit("specs/README.md", "| Database | proposed |", f"| Database | {status} |")
                self.assertReported(f"01.3 is '{status}' but links no spec file")
                self.edit("specs/README.md", f"| Database | {status} |", "| Database | proposed |")

    def test_done_spec_has_every_box_ticked(self):
        self.edit("specs/01-foundation/01.1-setup.md", "- [x] The app starts.", "- [ ] The app starts.")
        self.assertReported("01.1-setup.md:12: spec is done, but this acceptance box isn't ticked")

    def test_unticked_box_is_fine_before_done(self):
        self.assertPasses()  # 01.2 is approved and has an unticked box

    def test_title_starts_with_the_spec_id(self):
        self.edit("specs/01-foundation/01.1-setup.md", "# 01.1 Setup", "# Setup")
        self.assertReported("01.1-setup.md:1: title should start with '# 01.1'")

    def test_depends_on_ids_are_in_the_roadmap(self):
        self.edit("specs/01-foundation/01.2-settings.md", "Depends on: 01.1", "Depends on: 01.1, 07.4")
        self.assertReported("depends on 07.4, which isn't in the roadmap")


class StaleText(AuditTest):
    def test_done_spec_has_no_stale_markers(self):
        for marker in ("Proposed: one folder.", "Which folder? (pending your answer)"):
            with self.subTest(marker=marker):
                self.edit("specs/01-foundation/01.1-setup.md", "- The app starts.", f"- The app starts. {marker}")
                self.assertReported("01.1-setup.md:9: spec is done, but still says")
                self.edit("specs/01-foundation/01.1-setup.md", f"- The app starts. {marker}", "- The app starts.")

    def test_markers_in_the_changes_section_are_not_reported(self):
        self.edit(
            "specs/01-foundation/01.1-setup.md",
            "Changes (after build, see CLAUDE.md rule 5)\n- none",
            "Changes (after build, see CLAUDE.md rule 5)\n- 2026-03-02: the note still said Proposed: one folder; fixed.",
        )
        self.assertPasses()

    def test_quoted_markers_are_not_reported(self):
        self.edit(
            "specs/01-foundation/01.1-setup.md",
            "- The app starts.",
            '- The app starts. The audit looks for "Proposed:" and `pending your answer`.',
        )
        self.assertPasses()

    def test_markers_are_fine_before_done(self):
        self.edit("specs/01-foundation/01.2-settings.md", "Goal: settings", "Goal: Proposed: settings")
        self.assertPasses()


class IssuesLog(AuditTest):
    def test_ids_are_unique(self):
        self.edit("specs/ISSUES.md", "| ISSUE-002 |", "| ISSUE-001 |")
        self.assertReported("ISSUE-001 is used more than once")

    def test_ids_have_no_gaps(self):
        self.edit("specs/ISSUES.md", "| ISSUE-002 |", "| ISSUE-003 |")
        self.assertReported("IDs skipped: ISSUE-002")

    def test_resolved_issues_are_in_id_order(self):
        self.edit("specs/ISSUES.md", "| ISSUE-001 |", "| ISSUE-00X |")
        self.edit("specs/ISSUES.md", "| ISSUE-002 |", "| ISSUE-001 |")
        self.edit("specs/ISSUES.md", "| ISSUE-00X |", "| ISSUE-002 |")
        self.assertReported("ISSUE-001 comes after ISSUE-002")

    def test_resolution_spec_numbers_are_in_the_roadmap(self):
        self.edit("specs/ISSUES.md", "One class (01.2).", "One class (01.2, 09.9).")
        self.assertReported("ISSUE-002's resolution names 09.9")

    def test_open_issues_are_listed_but_do_not_fail(self):
        self.edit(
            "specs/ISSUES.md",
            "|---|---|---|---|\n",
            "|---|---|---|---|\n| ISSUE-003 | decision | How long can a trip name be? | Ask the user. |\n",
        )
        output = self.assertPasses()
        self.assertIn("ISSUE-003: decision | How long can a trip name be?", output)


class Settings(AuditTest):
    def test_every_setting_is_in_env_example(self):
        self.edit("backend/storymaker/config.py", '    model: str = "demo-model"\n', '    model: str = "demo-model"\n    data_dir: str = "data"\n')
        self.assertReported("STORYMAKER_DATA_DIR is in Settings")

    def test_secret_settings_in_env_example_are_empty(self):
        for line in ("GEMINI_API_KEY" + "=not-empty", "# GEMINI_API_KEY" + '="not-empty"'):
            with self.subTest(line=line):
                self.edit("backend/.env.example", "GEMINI_API_KEY=\n", line + "\n")
                self.assertReported(".env.example:2: GEMINI_API_KEY has a value")
                self.edit("backend/.env.example", line + "\n", "GEMINI_API_KEY=\n")


class ClaudeMd(AuditTest):
    def test_backend_paths_exist(self):
        self.edit("CLAUDE.md", "`backend/.env.example`.", "`backend/.env.example` and `backend/storymaker/gone.py`.")
        self.assertReported("CLAUDE.md:3: mentions backend/storymaker/gone.py, which doesn't exist")


class HygieneAndSecrets(AuditTest):
    def test_local_files_are_not_committed(self):
        cases = {
            "backend/.env": "a .env file is committed",
            "backend/data/storymaker.db": "a database file is committed",
            "backend/storymaker/__pycache__/config.cpython-312.pyc": "Python cache is committed",
            ".DS_Store": "a macOS .DS_Store file is committed",
        }
        for path, message in cases.items():
            with self.subTest(path=path):
                self.write(path, "local\n")
                self.assertReported(f"{path}: {message}")
                self.git("rm", "-q", path)

    def test_google_api_keys_are_reported(self):
        fake_key = "AIza" + "Q" * 35
        self.write("backend/storymaker/llm.py", f'client = connect(api_key="{fake_key}")\n')
        output = self.assertReported("llm.py:1: looks like a Google API key")
        self.assertNotIn(fake_key, output)

    def test_filled_in_secret_lines_are_reported(self):
        for name in ("GEMINI_API_KEY", "STORYMAKER_SIGNING_SECRET", "MAPS_TOKEN"):
            with self.subTest(name=name):
                self.write("notes/setup.txt", f"Run this first:\nexport {name}" + "=abc123\n")
                self.assertReported(f"notes/setup.txt:2: {name} is filled in")
                self.git("rm", "-q", "notes/setup.txt")

    def test_empty_secret_lines_are_fine(self):
        self.write("notes/setup.txt", "MAPS_TOKEN" + "=\nSIGNING_SECRET" + '=""\n')
        self.assertPasses()


if __name__ == "__main__":
    unittest.main()
