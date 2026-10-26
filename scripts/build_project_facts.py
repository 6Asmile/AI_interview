#!/usr/bin/env python3
"""Generate the factual code/API/data index for the iFaceoff interview book.

This generator intentionally does not write explanatory chapters.  It only
extracts current repository facts that can be checked mechanically.
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VAULT = ROOT / "docs" / "ifaceoff-vault"
OUTPUT_NAME = "09-代码-API-数据事实索引.md"
FACT_SOURCE_PATHS = (
    "ai_interview_backend",
    "ai-interview-frontend/src",
    "ai-interview-admin/src",
    "docker-compose.yml",
    "docker-compose.infra.yml",
    "docker-compose.production-resilience.yml",
    "docker-compose.observability.yml",
    "docker",
)


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True, encoding="utf-8"
    ).strip()


def source_commit() -> str:
    """Return the latest application/infrastructure commit, not a docs-only HEAD.

    Embedding HEAD in a generated file creates an impossible self-reference: the
    commit that adds the refreshed file immediately changes HEAD again.  A facts
    index instead cites the newest commit that can alter the extracted runtime
    facts.  Documentation-only descendants therefore remain reproducible.
    """

    return git("log", "-1", "--format=%H", "HEAD", "--", *FACT_SOURCE_PATHS)


def markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def code(value: str) -> str:
    return f"`{value.replace('`', '')}`"


def is_model_base(node: ast.expr) -> bool:
    if isinstance(node, ast.Attribute):
        return node.attr == "Model"
    return isinstance(node, ast.Name) and node.id == "Model"


def top_level_symbols(path: Path) -> tuple[list[str], list[str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return [], []
    classes = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]
    functions = [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    return classes, functions


def model_classes(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    return [
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef) and any(is_model_base(base) for base in node.bases)
    ]


def named_constraints(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return sorted(set(re.findall(r"name=['\"]([^'\"]+)['\"]", text)))


@dataclass(frozen=True)
class RouteFact:
    file: str
    line: int
    expression: str


def route_facts() -> list[RouteFact]:
    facts: list[RouteFact] = []
    for path in sorted((ROOT / "ai_interview_backend").rglob("urls.py")):
        rel = path.relative_to(ROOT).as_posix()
        for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = raw.strip()
            if "path(" in line or "router.register" in line:
                facts.append(RouteFact(rel, number, line.rstrip(",")))
    return facts


def frontend_routes() -> list[tuple[str, str]]:
    facts: list[tuple[str, str]] = []
    for relative in (
        Path("ai-interview-frontend/src/router/index.ts"),
        Path("ai-interview-admin/src/router.ts"),
    ):
        path = ROOT / relative
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"path\s*:\s*['\"]([^'\"]+)['\"]", text):
            facts.append((relative.as_posix(), match.group(1)))
    return facts


def celery_tasks() -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    backend = ROOT / "ai_interview_backend"
    for path in sorted(backend.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            decorators = ast.get_source_segment(path.read_text(encoding="utf-8"), node) or ""
            if any(
                (
                    isinstance(dec, ast.Name) and dec.id == "shared_task"
                )
                or (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Name)
                    and dec.func.id == "shared_task"
                )
                for dec in node.decorator_list
            ):
                result.append((path.relative_to(ROOT).as_posix(), node.name))
    return result


def compose_services() -> list[str]:
    services: list[str] = []
    text = (ROOT / "docker-compose.infra.yml").read_text(encoding="utf-8")
    in_services = False
    for raw in text.splitlines():
        if raw == "services:":
            in_services = True
            continue
        if in_services and raw and not raw.startswith(" "):
            break
        match = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", raw)
        if in_services and match:
            services.append(match.group(1))
    return services


def test_entries() -> list[str]:
    entries: list[str] = []
    for base in (
        ROOT / "ai_interview_backend",
        ROOT / "scripts" / "tests",
        ROOT / "ai-interview-frontend" / "tests",
    ):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            if (
                (path.suffix == ".py" and path.name.startswith("test"))
                or path.name == "tests.py"
                or path.name.endswith(".spec.ts")
            ):
                entries.append(path.relative_to(ROOT).as_posix())
    return entries


def render() -> str:
    commit = source_commit()
    commit_summary = git("show", "-s", "--format=%cI %s", commit)
    backend = ROOT / "ai_interview_backend"
    apps: list[tuple[str, list[str], list[str]]] = []
    for models_path in sorted(backend.glob("*/models.py")):
        app = models_path.parent.name
        models = model_classes(models_path)
        if models:
            apps.append((app, models, named_constraints(models_path)))

    routes = route_facts()
    ui_routes = frontend_routes()
    tasks = celery_tasks()
    tests = test_entries()
    services = compose_services()

    service_symbols: list[tuple[str, list[str], list[str]]] = []
    candidate_files = list(backend.glob("*/services.py")) + [
        backend / "interviews" / "agent_runtime.py",
        backend / "interviews" / "agent_v4" / "engine.py",
        backend / "interviews" / "configuration.py",
    ]
    for path in sorted({item for item in candidate_files if item.exists()}):
        classes, functions = top_level_symbols(path)
        if classes or functions:
            service_symbols.append(
                (path.relative_to(ROOT).as_posix(), classes, functions)
            )

    lines = [
        "---",
        "title: 代码 API 数据事实索引",
        "type: generated-facts",
        "order: 9",
        "status: generated",
        "implementation_status: implemented",
        "updated: 2026-08-12",
        "last_verified: 2026-08-12",
        f"verified_commit: {commit}",
        "audience:",
        "  - engineer",
        "  - interviewer",
        "related_code:",
        "  - ai_interview_backend",
        "  - ai-interview-frontend",
        "  - ai-interview-admin",
        "  - docker-compose.infra.yml",
        "tags:",
        "  - generated",
        "  - code-facts",
        "  - api-index",
        "---",
        "",
        "# 代码、API、数据事实索引",
        "",
        "> 本文由 `scripts/build_project_facts.py` 从当前仓库生成，只列可机械提取的事实；它不能替代六卷中的设计解释。",
        "",
        "## 基线",
        "",
        f"- Commit：{code(commit)}",
        f"- 最近提交：{markdown_cell(commit_summary)}",
        f"- Django 数据模型应用：{len(apps)}",
        f"- Django model classes：{sum(len(item[1]) for item in apps)}",
        f"- HTTP router/path declarations：{len(routes)}",
        f"- Candidate/Staff route paths：{len(ui_routes)}",
        f"- Celery shared tasks：{len(tasks)}",
        f"- 测试入口文件：{len(tests)}",
        "",
        "## Django 应用与模型",
        "",
        "| 应用 | 模型 | 命名约束/索引名称 |",
        "|---|---|---|",
    ]
    for app, models, constraints in apps:
        lines.append(
            f"| {code(app)} | {', '.join(code(item) for item in models)} | "
            f"{', '.join(code(item) for item in constraints) or '—'} |"
        )

    lines += [
        "",
        "## 后端 HTTP 路由声明",
        "",
        "| 文件:行 | 声明 |",
        "|---|---|",
    ]
    for fact in routes:
        lines.append(
            f"| {code(f'{fact.file}:{fact.line}')} | {code(fact.expression)} |"
        )

    lines += [
        "",
        "## 前端路由",
        "",
        "| 应用路由文件 | path |",
        "|---|---|",
    ]
    for path, route in ui_routes:
        lines.append(f"| {code(path)} | {code(route)} |")

    lines += [
        "",
        "## Celery 任务",
        "",
        "| 文件 | 任务函数 |",
        "|---|---|",
    ]
    for path, task in tasks:
        lines.append(f"| {code(path)} | {code(task)} |")

    lines += [
        "",
        "## Service、Agent 与配置入口",
        "",
        "| 文件 | Classes | Functions |",
        "|---|---|---|",
    ]
    for path, classes, functions in service_symbols:
        lines.append(
            f"| {code(path)} | {', '.join(code(item) for item in classes) or '—'} | "
            f"{', '.join(code(item) for item in functions) or '—'} |"
        )

    lines += [
        "",
        "## Compose 基础设施服务",
        "",
        "| Compose 文件 | Services |",
        "|---|---|",
        f"| {code('docker-compose.infra.yml')} | {', '.join(code(item) for item in services)} |",
        "",
        "关系运行库为 PostgreSQL；Redis/RabbitMQ/Qdrant/Meilisearch 等职责与当前配置见卷二、卷五和卷六。Compose service 名存在不等于应用 readiness 已通过。",
        "",
        "## 测试入口",
        "",
    ]
    lines.extend(f"- {code(path)}" for path in tests)
    lines += [
        "",
        "## 使用规则",
        "",
        "1. 任何正文引用类、函数、路由、模型或测试前先在本索引或当前代码中核对。",
        "2. 本索引自动生成，不能代替对应卷的正文更新。",
        "3. `--check` 比较当前仓库事实和已提交索引；基线引用最近的应用/基础设施 Commit，避免文档提交自引用。",
        "4. 历史 migration 中出现而当前代码已删除的符号不列为当前实现。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = args.vault.resolve() / OUTPUT_NAME
    expected = render()
    if args.write:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(expected, encoding="utf-8", newline="\n")
        print(f"wrote {target}")
        return 0
    if not target.exists():
        print(f"missing generated facts index: {target}", file=sys.stderr)
        return 1
    actual = target.read_text(encoding="utf-8")
    if actual != expected:
        print(
            "generated facts index is stale; run "
            f"python scripts/build_project_facts.py --vault {args.vault} --write",
            file=sys.stderr,
        )
        return 1
    print(f"facts index current: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
