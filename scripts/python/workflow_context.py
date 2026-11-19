#!/usr/bin/env python3
"""Component: workflow context; target: developer workstation; task: fork workflow.

Resolve stage inputs without creating artifacts or changing the feature pointer.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True

from common import (  # noqa: E402 - disable cache writes before local imports
    TemplateResolutionError,
    get_repo_root,
    resolve_template_content,
)
from workflow_common import (  # noqa: E402
    architecture,
    canonical_feature_directory,
    environment,
    paths,
    require_files,
    tasks,
)

REQUIRED = {
    "architecture": ["CONSTITUTION", "SPEC"],
    "environment": ["CONSTITUTION", "SPEC", "ARCHITECTURE"],
    "plan": ["CONSTITUTION", "SPEC", "ARCHITECTURE", "ENVIRONMENT"],
    "taskscode": ["CONSTITUTION", "SPEC", "ARCHITECTURE", "ENVIRONMENT", "PLAN"],
    "analyze": [
        "CONSTITUTION",
        "SPEC",
        "ARCHITECTURE",
        "ENVIRONMENT",
        "PLAN",
        "TASKS_CODE",
    ],
    "impcode": [
        "CONSTITUTION",
        "SPEC",
        "ARCHITECTURE",
        "ENVIRONMENT",
        "PLAN",
        "TASKS_CODE",
    ],
    "deployment": [
        "CONSTITUTION",
        "SPEC",
        "ARCHITECTURE",
        "ENVIRONMENT",
        "PLAN",
        "TASKS_CODE",
        "CODE_PROGRESS",
    ],
    "test": [
        "CONSTITUTION",
        "SPEC",
        "ARCHITECTURE",
        "ENVIRONMENT",
        "PLAN",
        "TASKS_CODE",
        "CODE_PROGRESS",
    ],
}


def _require_template(name: str, root: Path) -> str:
    template = resolve_template_content(name + "-template", root)
    if not template or not template.strip():
        raise ValueError(f"Missing {name}-template; reinstall shared infrastructure")
    return template


def specify_context(candidate: Path, *, paths_only: bool) -> dict[str, str]:
    root = get_repo_root(Path(__file__)).resolve()
    feature = canonical_feature_directory(root, candidate)
    relative = feature.relative_to(root).as_posix()
    if ":" in relative or "\\" in relative:
        raise ValueError("The feature directory must have a portable project-relative path")
    if feature.exists() and not feature.is_dir():
        raise ValueError(f"The feature destination is not a directory: {feature}")
    spec = feature / "spec.md"
    if spec.is_symlink() or (spec.exists() and not spec.is_file()):
        raise ValueError(f"The specification destination must be a regular file: {spec}")
    payload = {
        "REPO_ROOT": str(root),
        "FEATURE_DIR": str(feature),
        "FEATURE_DIRECTORY": relative,
        "SPEC": str(spec),
    }
    if not paths_only:
        payload["TEMPLATE_CONTENT"] = _require_template("spec", root)
    return payload


def context(stage: str) -> dict:
    selected = paths()
    require_files(selected, REQUIRED[stage])
    if stage == "environment":
        architecture(selected)
    elif stage in {"plan", "taskscode"}:
        environment(selected)
    elif stage in {"impcode", "deployment", "test"}:
        tasks(selected)
    # Analyze must be able to report malformed inventories, cycles and bad targets.
    payload = {key: str(value) for key, value in selected.items()}
    payload["PYTHON"] = sys.executable
    payload["PROGRESS_HELPER"] = str(
        Path(__file__).with_name("code_progress.py").resolve()
    )
    if stage != "impcode":
        name = {
            "taskscode": "tasks-code",
            "test": "test-report",
            "analyze": "analysis",
        }.get(stage, stage)
        payload["TEMPLATE_CONTENT"] = _require_template(name, selected["REPO_ROOT"])
    payload["AVAILABLE_DOCS"] = sorted(
        p.name for p in selected["FEATURE_DIR"].iterdir()
    )
    return payload


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("specify", *REQUIRED))
    parser.add_argument(
        "--json", action="store_true", help="JSON is the default output"
    )
    parser.add_argument("--feature-directory", type=Path, help="Candidate directory for specify")
    parser.add_argument("--paths-only", action="store_true", help="Resolve specify paths without a template")
    args = parser.parse_args(argv)
    if args.stage == "specify":
        if args.feature_directory is None:
            parser.error("specify requires --feature-directory")
    elif args.feature_directory is not None or args.paths_only:
        parser.error("--feature-directory and --paths-only are specify options")
    try:
        if args.stage == "specify":
            payload = specify_context(args.feature_directory, paths_only=args.paths_only)
        else:
            payload = context(args.stage)
        print(json.dumps(payload, ensure_ascii=True))
        return 0
    except (OSError, ValueError, TemplateResolutionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
