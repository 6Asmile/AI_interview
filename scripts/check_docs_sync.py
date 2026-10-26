#!/usr/bin/env python3
"""Validate the one-book/six-volume Vault and enforce section-aware doc sync."""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import hashlib
import json
import re
import struct
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import unquote


REPO = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO / "scripts" / "doc_sync_map.json"
EXPECTED_MARKDOWN = {
    f"{number:02d}-{name}.md"
    for number, name in [
        (0, "开始这里"),
        (1, "iFaceoff项目全解"),
        (2, "卷一-产品定位与求职闭环"),
        (3, "卷二-全栈架构与一次请求"),
        (4, "卷三-Career与Resume实现"),
        (5, "卷四-Interview与评估实现"),
        (6, "卷五-Agent-RAG与Model-Gateway实现"),
        (7, "卷六-平台工程可靠性安全与运维"),
        (8, "项目面试题与连续追问"),
        (9, "代码-API-数据事实索引"),
        (10, "运行与故障手册"),
        (11, "ADR与项目演进时间线"),
        (12, "项目变更日志"),
        (13, "截图证据清单"),
        (14, "词汇表与实现状态口径"),
    ]
}
REQUIRED_PROPERTIES = {
    "title",
    "type",
    "order",
    "status",
    "implementation_status",
    "updated",
    "last_verified",
    "verified_commit",
    "audience",
    "related_code",
    "tags",
}
DATE_PROPERTIES = {"updated", "last_verified"}
ALLOWED_IMPLEMENTATION = {
    "implemented",
    "mixed",
    "partial",
    "legacy-compatible",
    "target-design",
    "pending-verification",
}
WIKI_LINK_RE = re.compile(r"!?\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
SECRET_PATTERNS = {
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "credential URL": re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^@\s/]{8,}@"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


def run_git(*args: str, binary: bool = False):
    return subprocess.run(
        ["git", *args],
        cwd=REPO,
        check=True,
        stdout=subprocess.PIPE,
        text=not binary,
        encoding=None if binary else "utf-8",
    ).stdout


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def changed_files(args: argparse.Namespace) -> list[str]:
    if args.files:
        return sorted({item.replace("\\", "/") for item in args.files})
    if args.staged:
        cmd = ("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    elif args.base and args.head:
        cmd = ("diff", "--name-only", "--diff-filter=ACMR", "-z", f"{args.base}...{args.head}")
    elif args.base:
        cmd = ("diff", "--name-only", "--diff-filter=ACMR", "-z", args.base)
    else:
        cmd = ("diff", "--name-only", "--diff-filter=ACMR", "-z", "HEAD")
    raw = run_git(*cmd, binary=True)
    result = {
        item.decode("utf-8", errors="surrogateescape").replace("\\", "/")
        for item in raw.split(b"\0")
        if item
    }
    if not args.staged and not args.base:
        untracked = run_git("ls-files", "--others", "--exclude-standard", "-z", binary=True)
        result.update(
            item.decode("utf-8", errors="surrogateescape").replace("\\", "/")
            for item in untracked.split(b"\0")
            if item
        )
    return sorted(result)


def matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def first_rule(path: str, config: dict) -> dict | None:
    for rule in config["rules"]:
        if matches(path, rule["patterns"]):
            return rule
    return None


def rule_targets(rule: dict) -> list[dict[str, object]]:
    """Return every authoritative document target for a first-match rule."""

    if rule.get("targets"):
        return list(rule["targets"])
    return [{"document": rule["document"], "sections": rule["sections"]}]


def relevant_source(path: str, config: dict) -> bool:
    if matches(path, config["ignored"]):
        return False
    if path in config["tracked_root_files"]:
        return True
    return first_rule(path, config) is not None


def diff_args(args: argparse.Namespace, path: str) -> list[str]:
    if args.staged:
        return ["diff", "--cached", "-U0", "--", path]
    if args.base and args.head:
        return ["diff", "-U0", f"{args.base}...{args.head}", "--", path]
    if args.base:
        return ["diff", "-U0", args.base, "--", path]
    return ["diff", "-U0", "HEAD", "--", path]


def changed_new_lines(args: argparse.Namespace, path: str) -> set[int]:
    if args.files:
        return set(range(1, 10_000_000))
    if not (REPO / path).exists():
        return set()
    untracked = set(
        item.decode("utf-8", errors="replace").replace("\\", "/")
        for item in run_git("ls-files", "--others", "--exclude-standard", "-z", binary=True).split(b"\0")
        if item
    )
    if path in untracked:
        return set(range(1, len((REPO / path).read_text(encoding="utf-8").splitlines()) + 1))
    patch = run_git(*diff_args(args, path))
    result: set[int] = set()
    for match in re.finditer(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", patch, re.MULTILINE):
        start = int(match.group(1))
        length = int(match.group(2) or "1")
        result.update(range(start, start + length))
    return result


def section_ranges(path: Path) -> dict[str, range]:
    lines = path.read_text(encoding="utf-8").splitlines()
    headings = [(index + 1, line.strip()) for index, line in enumerate(lines) if line.startswith("## ")]
    ranges: dict[str, range] = {}
    for offset, (start, title) in enumerate(headings):
        end = headings[offset + 1][0] if offset + 1 < len(headings) else len(lines) + 1
        ranges[title] = range(start, end)
    return ranges


def sync_errors(args: argparse.Namespace, changed: list[str], config: dict) -> list[str]:
    sources = [item for item in changed if relevant_source(item, config)]
    if not sources:
        return []
    errors: list[str] = []
    changed_set = set(changed)
    if config["changelog"] not in changed_set:
        errors.append(f"source changes require {config['changelog']}")
    grouped: dict[str, list[str]] = defaultdict(list)
    rules: dict[str, dict] = {}
    for source in sources:
        rule = first_rule(source, config)
        if not rule:
            errors.append(f"unmapped source: {source}")
            continue
        grouped[rule["name"]].append(source)
        rules[rule["name"]] = rule
    for name, source_paths in grouped.items():
        rule = rules[name]
        for target in rule_targets(rule):
            document = str(target["document"])
            sections = list(target["sections"])
            if document not in changed_set:
                errors.append(
                    f"{name}: {', '.join(source_paths[:3])} requires canonical document {document}"
                )
                continue
            doc_path = REPO / document
            if not doc_path.exists():
                errors.append(f"{name}: missing mapped document {document}")
                continue
            changed_lines = changed_new_lines(args, document)
            ranges = section_ranges(doc_path)
            matched_section = False
            for section in sections:
                if section not in ranges:
                    errors.append(f"{name}: mapped section missing in {document}: {section}")
                    continue
                if changed_lines.intersection(ranges[section]):
                    matched_section = True
            if not matched_section:
                errors.append(
                    f"{name}: {document} changed, but no diff falls inside mapped sections: "
                    + ", ".join(sections)
                )
            lines = doc_path.read_text(encoding="utf-8").splitlines()
            verified_lines = {
                index + 1 for index, line in enumerate(lines)
                if line.startswith("verified_commit:")
            }
            if not changed_lines.intersection(verified_lines):
                errors.append(f"{name}: {document} must refresh verified_commit in the same diff")
    return errors


def parse_frontmatter(path: Path) -> tuple[dict[str, object], list[str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        return {}, ["missing opening frontmatter"]
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}, ["missing closing frontmatter"]
    data: dict[str, object] = {}
    current_list: str | None = None
    for raw in lines[1:end]:
        if raw.startswith("  - ") and current_list:
            assert isinstance(data[current_list], list)
            data[current_list].append(raw[4:].strip())
            continue
        if ":" not in raw or raw.startswith((" ", "\t")):
            continue
        key, value = raw.split(":", 1)
        key, value = key.strip(), value.strip().strip('"')
        if value:
            data[key] = value
            current_list = None
        else:
            data[key] = []
            current_list = key
    errors = []
    missing = REQUIRED_PROPERTIES - data.keys()
    if missing:
        errors.append("missing properties: " + ", ".join(sorted(missing)))
    for key in DATE_PROPERTIES:
        try:
            dt.date.fromisoformat(str(data.get(key, "")))
        except ValueError:
            errors.append(f"invalid date {key}: {data.get(key)!r}")
    if data.get("implementation_status") not in ALLOWED_IMPLEMENTATION:
        errors.append(f"invalid implementation_status: {data.get('implementation_status')!r}")
    for key in ("audience", "related_code", "tags"):
        if not isinstance(data.get(key), list) or not data.get(key):
            errors.append(f"{key} must be a non-empty YAML list")
    return data, errors


def commit_is_reachable(commit: object, head: str) -> bool:
    """A document may cite an already verified ancestor, avoiding self-reference."""

    value = str(commit or "").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{7,40}", value):
        return False
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", value, head],
        cwd=REPO,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def outside_fences(text: str) -> str:
    output: list[str] = []
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if not fenced:
            output.append(line)
    return "\n".join(output)


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        signature = handle.read(24)
    if len(signature) < 24 or signature[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    return struct.unpack(">II", signature[16:24])


def vault_errors(vault: Path) -> list[str]:
    errors: list[str] = []
    markdown = sorted(vault.glob("*.md"))
    names = {path.name for path in markdown}
    if names != EXPECTED_MARKDOWN:
        errors.append(
            "Vault must contain exactly the 15 canonical Markdown files; "
            f"missing={sorted(EXPECTED_MARKDOWN - names)}, extra={sorted(names - EXPECTED_MARKDOWN)}"
        )
    nested_markdown = [path for path in vault.rglob("*.md") if path.parent != vault]
    if nested_markdown:
        errors.append("nested Markdown is not allowed: " + ", ".join(str(item) for item in nested_markdown))
    head = run_git("rev-parse", "HEAD").strip()
    titles: dict[str, Path] = {}
    combined = ""
    for path in markdown:
        properties, property_errors = parse_frontmatter(path)
        errors.extend(f"{path.name}: {item}" for item in property_errors)
        if not commit_is_reachable(properties.get("verified_commit"), head):
            errors.append(
                f"{path.name}: verified_commit must be a commit reachable from current HEAD {head}"
            )
        title = str(properties.get("title", ""))
        if title in titles:
            errors.append(f"duplicate title {title!r}: {titles[title].name}, {path.name}")
        titles[title] = path
        text = path.read_text(encoding="utf-8")
        combined += "\n" + text
        safe = outside_fences(text)
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(safe):
                errors.append(f"{path.name}: possible secret ({label})")
        for target in WIKI_LINK_RE.findall(safe):
            target = target.strip()
            if not target:
                continue
            candidate = vault / (target if target.endswith(".md") else f"{target}.md")
            if not candidate.exists() and not (vault / target).exists():
                errors.append(f"{path.name}: broken Wiki link {target}")
        for raw in MARKDOWN_LINK_RE.findall(safe):
            target = unquote(raw.split("#", 1)[0].strip().strip("<>"))
            if not target or re.match(r"^[a-z][a-z0-9+.-]*://", target) or target.startswith("#"):
                continue
            if not (path.parent / target).resolve().exists():
                errors.append(f"{path.name}: broken Markdown link {raw}")

    total_chars = sum(len(path.read_text(encoding="utf-8")) for path in markdown)
    if total_chars < 240_000:
        errors.append(f"Vault has {total_chars} characters; minimum is 240000")
    mermaid_count = combined.count("```mermaid")
    if mermaid_count < 35:
        errors.append(f"Vault has {mermaid_count} Mermaid diagrams; minimum is 35")

    screenshots = sorted((vault / "assets" / "screenshots").glob("*.png"))
    if len(screenshots) < 27:
        errors.append(f"Vault has {len(screenshots)} PNG screenshots; minimum is 27")
    hashes: Counter[str] = Counter()
    for screenshot in screenshots:
        try:
            width, height = png_size(screenshot)
        except ValueError as exc:
            errors.append(f"{screenshot.name}: {exc}")
            continue
        if (width, height) != (1440, 900):
            errors.append(f"{screenshot.name}: expected 1440x900, got {width}x{height}")
        digest = hashlib.sha256(screenshot.read_bytes()).hexdigest()
        hashes[digest] += 1
        if screenshot.name not in combined:
            errors.append(f"{screenshot.name}: missing from screenshot manifest/book")
    if any(count > 1 for count in hashes.values()):
        errors.append("duplicate screenshot content detected")

    paragraphs: dict[str, set[str]] = defaultdict(set)
    for path in markdown:
        text = outside_fences(path.read_text(encoding="utf-8"))
        for paragraph in re.split(r"\n\s*\n", text):
            normalized = re.sub(r"\s+", " ", paragraph).strip()
            if len(normalized) >= 120 and not normalized.startswith(("---", "|", "![", ">")):
                paragraphs[normalized].add(path.name)
    repeated = [(text, files) for text, files in paragraphs.items() if len(files) >= 3]
    if repeated:
        errors.append(
            "paragraphs of 120+ characters repeated across three documents: "
            + "; ".join(f"{sorted(files)}: {text[:80]}..." for text, files in repeated[:5])
        )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--base")
    parser.add_argument("--head")
    parser.add_argument("--files", nargs="*")
    parser.add_argument("--check-vault", action="store_true")
    parser.add_argument("--vault", type=Path)
    args = parser.parse_args()
    config = load_config()
    changed = changed_files(args)
    explicit_diff = args.staged or args.base or args.head or args.files is not None
    errors = sync_errors(args, changed, config) if explicit_diff or not args.check_vault else []
    if args.check_vault:
        vault = args.vault.resolve() if args.vault else REPO / config["vault"]
        errors.extend(vault_errors(vault))
    if errors:
        print("documentation checks failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(
        f"documentation checks passed ({len(changed)} changed paths"
        + (", vault validated" if args.check_vault else "")
        + ")"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
