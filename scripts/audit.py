#!/usr/bin/env python3
"""Repo audit (spec 00.1), run before every push to the public GitHub repo.

Checks that the roadmap, spec files, issues log, settings and CLAUDE.md agree with
each other, and that nothing secret or machine-local is committed. It reads one git
revision (default HEAD), not the working tree, so it checks exactly what gets pushed:

    python3 scripts/audit.py --rev main

Prints each finding with its file and exits with 1 if there are any (2 if the audit
itself can't run). Standard library only. If the format of the roadmap, issues log
or spec files changes, update this script in the same change.
"""

from __future__ import annotations

import argparse
import ast
import posixpath
import re
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass

ROADMAP = "specs/README.md"
ISSUES = "specs/ISSUES.md"
CLAUDE_MD = "CLAUDE.md"
CONFIG = "backend/storymaker/config.py"
ENV_EXAMPLE = "backend/.env.example"

# A spec ID such as 02.1 or 11.10 inside text, but not part of a longer number like 3.12.1.
SPEC_ID_IN_TEXT = re.compile(r"(?<![\d.])\d{2}\.\d+(?!\d|\.\d)")
ROADMAP_ROW = re.compile(r"^\| (\d{2}\.\d+) \| (.*) \| (\w+) \|\s*$")
SPEC_LINK = re.compile(r"\(\[spec\]\(([^)\s]+)\)\)")
SPEC_FILE = re.compile(r"^specs/[^/]+/[^/]+\.md$")
SPEC_FILE_NAME = re.compile(r"^(\d{2}\.\d+)-.+\.md$")
NEEDS_FILE = {"written", "approved", "done", "changing"}
# Section starts in specs/_template.md.
SECTION = re.compile(r"^(Goal|Behavior|Acceptance|Out of scope|Later|Consistency check|Changes)\b")
UNTICKED = re.compile(r"^\s*- \[ \]")
STALE_MARKER = re.compile(r"pending your answer|proposed:", re.IGNORECASE)
QUOTED = re.compile(r'"[^"\n]*"|“[^”\n]*”|`[^`\n]*`')
ISSUE_ROW = re.compile(r"^\|\s*(ISSUE-(\d+))\s*\|")
ENV_LINE = re.compile(r"^\s*(?:#\s*)?(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")
SECRET_NAME = re.compile(r"_(KEY|SECRET|TOKEN)$")
FILLED_SECRET_LINE = re.compile(r"^\s*(?:#\s*)?(?:export\s+)?([A-Z][A-Z0-9_]*_(?:KEY|SECRET|TOKEN))\s*=(.*)$")
GOOGLE_KEY_PATTERN = re.compile(rb"AIza[0-9A-Za-z_\-]{35}")
BACKEND_PATH = re.compile(r"backend/[\w.\-/]*")
DATABASE_FILE = re.compile(r"\.(db|sqlite3?)(-wal|-shm|-journal)?$")


@dataclass
class Finding:
    path: str
    line: int | None
    message: str

    def __str__(self) -> str:
        where = f"{self.path}:{self.line}" if self.line else self.path
        return f"{where}: {self.message}"


@dataclass
class RoadmapRow:
    id: str
    status: str
    link: str | None  # repo path of the linked spec file
    line: int


@dataclass
class IssueRow:
    number: int
    label: str
    section: str
    cells: list[str]
    line: int


def git(cwd: str | None, *args: str, input: bytes | None = None) -> bytes:
    return subprocess.run(["git", *args], cwd=cwd, input=input, capture_output=True, check=True).stdout


class Snapshot:
    """Every tracked file at one git revision."""

    def __init__(self, rev: str):
        self.root = git(None, "rev-parse", "--show-toplevel").decode().strip()
        self.commit = git(self.root, "rev-parse", "--verify", f"{rev}^{{commit}}").decode().strip()
        blobs = []
        for entry in git(self.root, "ls-tree", "-r", "-z", "--full-tree", self.commit).split(b"\0"):
            if entry:
                meta, path = entry.split(b"\t", 1)
                _mode, kind, sha = meta.split()
                if kind == b"blob":
                    blobs.append((path.decode("utf-8", "surrogateescape"), sha))
        out = git(self.root, "cat-file", "--batch", input=b"".join(sha + b"\n" for _, sha in blobs))
        self.files: dict[str, bytes] = {}
        pos = 0
        for path, _sha in blobs:
            header_end = out.index(b"\n", pos)
            size = int(out[pos:header_end].split()[2])
            self.files[path] = out[header_end + 1 : header_end + 1 + size]
            pos = header_end + 1 + size + 1

    def lines(self, path: str) -> list[str] | None:
        data = self.files.get(path)
        return None if data is None else data.decode("utf-8", "replace").splitlines()

    def exists(self, path: str) -> bool:
        folder = path.rstrip("/") + "/"
        return path in self.files or any(name.startswith(folder) for name in self.files)


def has_value(raw: str) -> bool:
    """True if the right-hand side of NAME=... holds something other than a comment or quotes."""
    value = raw.strip()
    if value.startswith("#"):
        return False
    value = re.split(r"\s#", value, maxsplit=1)[0].strip()
    return value.strip("'\"") != ""


def roadmap_rows(snap: Snapshot) -> list[RoadmapRow]:
    rows = []
    for number, line in enumerate(snap.lines(ROADMAP) or [], 1):
        match = ROADMAP_ROW.match(line)
        if match:
            link = SPEC_LINK.search(match[2])
            path = posixpath.normpath(f"specs/{link[1]}") if link else None
            rows.append(RoadmapRow(match[1], match[3], path, number))
    return rows


def check_roadmap_and_specs(snap: Snapshot, rows: list[RoadmapRow]) -> Iterator[Finding]:
    if snap.lines(ROADMAP) is None:
        yield Finding(ROADMAP, None, "not found")
        return
    ids = {row.id for row in rows}
    linked = {}
    for row in rows:
        if row.link is None:
            if row.status in NEEDS_FILE:
                yield Finding(ROADMAP, row.line, f"{row.id} is '{row.status}' but links no spec file")
            continue
        linked[row.link] = row
        if row.link not in snap.files:
            yield Finding(ROADMAP, row.line, f"{row.id} links to {row.link}, which doesn't exist")

    for path in sorted(name for name in snap.files if SPEC_FILE.match(name)):
        row = linked.get(path)
        if row is None:
            yield Finding(path, None, "spec file isn't linked from the roadmap")
        name_id = SPEC_FILE_NAME.match(posixpath.basename(path))
        spec_id = row.id if row else name_id[1] if name_id else None
        lines = snap.lines(path) or [""]
        if spec_id and not re.match(rf"# {re.escape(spec_id)}(\s|$)", lines[0]):
            yield Finding(path, 1, f"title should start with '# {spec_id}'")
        for number, line in enumerate(lines, 1):
            if line.startswith("Depends on:"):
                for dep in SPEC_ID_IN_TEXT.findall(line):
                    if dep not in ids:
                        yield Finding(path, number, f"depends on {dep}, which isn't in the roadmap")
        if row and row.status == "done":
            yield from check_done_spec(path, lines)


def check_done_spec(path: str, lines: list[str]) -> Iterator[Finding]:
    section = None
    for number, line in enumerate(lines, 1):
        start = SECTION.match(line)
        if start:
            section = start[1]
        if section == "Changes":
            break  # it may describe what was fixed, markers included
        if section == "Acceptance" and UNTICKED.match(line):
            yield Finding(path, number, "spec is done, but this acceptance box isn't ticked")
        marker = STALE_MARKER.search(QUOTED.sub("", line))
        if marker:
            yield Finding(path, number, f"spec is done, but still says '{marker[0]}'")


def issue_rows(snap: Snapshot) -> list[IssueRow]:
    rows, section = [], ""
    for number, line in enumerate(snap.lines(ISSUES) or [], 1):
        if line.startswith("## "):
            section = line[3:].strip().lower()
        match = ISSUE_ROW.match(line)
        if match:
            cells = [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip())[1:-1]]
            rows.append(IssueRow(int(match[2]), match[1], section, cells, number))
    return rows


def check_issues(snap: Snapshot, issues: list[IssueRow], roadmap_ids: set[str]) -> Iterator[Finding]:
    if snap.lines(ISSUES) is None:
        yield Finding(ISSUES, None, "not found")
        return
    seen = set()
    for issue in issues:
        if issue.number in seen:
            yield Finding(ISSUES, issue.line, f"{issue.label} is used more than once")
        seen.add(issue.number)
    missing = sorted(set(range(1, max(seen, default=0) + 1)) - seen)
    if missing:
        yield Finding(ISSUES, None, "IDs skipped: " + ", ".join(f"ISSUE-{n:03d}" for n in missing))

    highest = 0
    for issue in (row for row in issues if row.section == "resolved"):
        if issue.number < highest:
            yield Finding(ISSUES, issue.line, f"{issue.label} comes after ISSUE-{highest:03d}; resolved issues go in ID order")
        highest = max(highest, issue.number)
        for spec_id in SPEC_ID_IN_TEXT.findall(issue.cells[-1]):
            if spec_id not in roadmap_ids:
                yield Finding(ISSUES, issue.line, f"{issue.label}'s resolution names {spec_id}, which isn't in the roadmap")


def settings_env_names(source: str) -> list[str] | None:
    """Environment variable names read by the Settings class, without importing it."""
    settings = next(
        (node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.ClassDef) and node.name == "Settings"),
        None,
    )
    if settings is None:
        return None
    prefix, fields = "", []
    for statement in settings.body:
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            name, value = statement.target.id, statement.value
        elif isinstance(statement, ast.Assign) and len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name):
            name, value = statement.targets[0].id, statement.value
        else:
            continue
        if name == "model_config":
            prefix = keyword_text(value, "env_prefix") or ""
        elif isinstance(statement, ast.AnnAssign):
            fields.append((name, keyword_text(value, "validation_alias") or keyword_text(value, "alias")))
    return [(alias or f"{prefix}{name}").upper() for name, alias in fields]


def keyword_text(call: ast.expr | None, keyword: str) -> str | None:
    if isinstance(call, ast.Call):
        for item in call.keywords:
            if item.arg == keyword and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
                return item.value.value
    return None


def check_settings(snap: Snapshot) -> Iterator[Finding]:
    config, example = snap.lines(CONFIG), snap.lines(ENV_EXAMPLE)
    if config is None or example is None:
        yield Finding(CONFIG if config is None else ENV_EXAMPLE, None, "not found")
        return
    env_names = settings_env_names("\n".join(config))
    if env_names is None:
        yield Finding(CONFIG, None, "no Settings class found")
        return

    listed = set()
    for number, line in enumerate(example, 1):
        match = ENV_LINE.match(line)
        if match:
            listed.add(match[1].upper())
            if SECRET_NAME.search(match[1].upper()) and has_value(match[2]):
                yield Finding(ENV_EXAMPLE, number, f"{match[1]} has a value; this file is committed, so it holds names only")
    for name in env_names:
        if name not in listed:
            yield Finding(ENV_EXAMPLE, None, f"{name} is in Settings ({CONFIG}) but missing here")


def check_claude_md(snap: Snapshot) -> Iterator[Finding]:
    for number, line in enumerate(snap.lines(CLAUDE_MD) or [], 1):
        for mention in BACKEND_PATH.findall(line):
            path = mention.rstrip(".,;:")
            if not snap.exists(path):
                yield Finding(CLAUDE_MD, number, f"mentions {path}, which doesn't exist")


def check_hygiene_and_secrets(snap: Snapshot) -> Iterator[Finding]:
    for path, data in sorted(snap.files.items()):
        name = posixpath.basename(path)
        if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
            yield Finding(path, None, "a .env file is committed; it may hold real secrets")
        elif DATABASE_FILE.search(name):
            yield Finding(path, None, "a database file is committed")
        elif "__pycache__" in path.split("/") or name.endswith(".pyc"):
            yield Finding(path, None, "Python cache is committed")
        elif name == ".DS_Store":
            yield Finding(path, None, "a macOS .DS_Store file is committed")

        for match in GOOGLE_KEY_PATTERN.finditer(data):
            yield Finding(path, data.count(b"\n", 0, match.start()) + 1, "looks like a Google API key")
        if path == ENV_EXAMPLE or b"\0" in data:
            continue  # .env.example is covered by check_settings; binary files have no lines
        for number, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
            match = FILLED_SECRET_LINE.match(line)
            if match and has_value(match[2]):
                yield Finding(path, number, f"{match[1]} is filled in")


def run_audit(snap: Snapshot) -> tuple[list[Finding], list[IssueRow]]:
    rows = roadmap_rows(snap)
    issues = issue_rows(snap)
    findings = [
        *check_roadmap_and_specs(snap, rows),
        *check_issues(snap, issues, {row.id for row in rows}),
        *check_settings(snap),
        *check_claude_md(snap),
        *check_hygiene_and_secrets(snap),
    ]
    return findings, [issue for issue in issues if issue.section == "open"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the repo at one git revision before pushing (spec 00.1).")
    parser.add_argument("--rev", default="HEAD", help="git revision to check (default: HEAD)")
    args = parser.parse_args(argv)
    try:
        snap = Snapshot(args.rev)
    except subprocess.CalledProcessError as error:
        print(f"audit: can't read revision {args.rev!r}: {error.stderr.decode().strip()}", file=sys.stderr)
        return 2

    findings, open_issues = run_audit(snap)
    label = f"{args.rev} ({snap.commit[:7]})"
    if open_issues:
        print("Open issues (listed, not failures):")
        for issue in open_issues:
            summary = " | ".join(issue.cells[1:3])
            print(f"  {issue.label}: {summary[:120]}")
    if findings:
        print(f"Audit of {label}: {len(findings)} finding(s)")
        for finding in findings:
            print(f"  {finding}")
        return 1
    print(f"Audit of {label}: no findings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
