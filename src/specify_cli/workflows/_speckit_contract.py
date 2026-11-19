"""Completion requirements for the eleven-stage bundled workflow."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from .._assets import _locate_core_pack, _repo_root
from ..shared_infra import shared_scripts_source

if TYPE_CHECKING:
    from .base import StepContext
    from .engine import WorkflowDefinition


# Canonical JSON digest of the unmarked 2.0.0 definition at 64dbcdd1.
# Persisted snapshots preserve the YAML data, but can change its formatting.
_STOCK_200 = "17f5eb8e1a6d557fd3d49e49562921abae431271edca3638b3d25162ff08e01a"


SHARED_OUTPUTS = {
    "constitution": ".specify/memory/constitution.md",
    "architecture": ".specify/memory/architecture.md",
    "environment": ".specify/memory/environment.md",
}
FEATURE_OUTPUTS = {
    "clarify": "spec.md",
    "plan": "plan.md",
    "taskscode": "tasks-code.md",
    "analyze": "analysis.md",
    "impcode": "code-progress.json",
    "deployment": "deployment.md",
    "test": "test-report.md",
}


def uses_speckit_contract(definition: WorkflowDefinition) -> bool:
    if definition.data.get("completion_contract") == "speckit":
        return True
    if definition.id != "speckit" or definition.version != "2.0.0":
        return False
    # Pending stock 2.0.0 runs keep their original definition snapshot. Apply
    # the contract there too, without interpreting a customized YAML as stock.
    try:
        canonical = json.dumps(definition.data, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError, RecursionError):
        return False
    return hashlib.sha256(canonical.encode("ascii")).hexdigest() == _STOCK_200


def _canonical_feature(root: Path, name: str) -> str:
    try:
        relative = PurePosixPath(name)
        if (
            relative.as_posix() in {".", ""}
            or relative.is_absolute()
            or relative.as_posix() != name
            or ".." in relative.parts
            or ":" in name
            or "\\" in name
        ):
            raise ValueError
        directory = root.joinpath(*relative.parts)
        spec = directory / "spec.md"
        if (
            directory.resolve(strict=True).relative_to(root).as_posix() != name
            or spec.resolve(strict=True) != spec
            or not spec.is_file()
        ):
            raise ValueError
        current = directory
        while current != root:
            if current.is_symlink():
                raise ValueError
            current = current.parent
        return name
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(f"Invalid or unavailable bound feature directory: {name!r}") from exc


def feature_from_specify(root: Path, artifacts: dict[str, str]) -> str:
    """Bind core and Lean runs to their required spec; checklist evidence is optional."""
    specs = [
        PurePosixPath(path).parent.as_posix()
        for path in artifacts
        if (
            isinstance(path, str)
            and PurePosixPath(path).name == "spec.md"
            and PurePosixPath(path).as_posix() == path
        )
    ]
    if len(specs) != 1:
        raise ValueError("Specify completion must report one feature spec.md")
    return _canonical_feature(root, specs[0])


def _completed_commands(context: StepContext, stage: str) -> list[dict]:
    candidates = []
    for result in context.steps.values():
        output = result.get("output")
        if (
            result.get("status") == "completed"
            and isinstance(output, dict)
            and output.get("command") in (f"speckit.{stage}", stage)
        ):
            candidates.append(output)
    return candidates


def bound_feature(root: Path, context: StepContext) -> tuple[str, bool]:
    candidates = _completed_commands(context, "specify")
    if len(candidates) != 1:
        raise ValueError("Run has no unique verified specify result. Start a new speckit run.")
    output = candidates[0]
    feature = output.get("feature_directory")
    if isinstance(feature, str):
        return _canonical_feature(root, feature), False
    # Older checkpoints have the verified receipt but no explicit binding.
    # Recover from that receipt, never from the mutable project selector.
    receipt = output.get("completion")
    if (
        not isinstance(receipt, dict)
        or receipt.get("status") != "completed"
        or not isinstance(receipt.get("artifacts"), dict)
    ):
        raise ValueError("Run has no verified feature spec.md. Start a new speckit run.")
    try:
        return feature_from_specify(root, receipt["artifacts"]), True
    except ValueError as exc:
        raise ValueError(
            f"Cannot recover the run's feature from its specify receipt. {exc}. Start a new speckit run."
        ) from exc


def verify_legacy_prerequisites(root: Path, feature: str, context: StepContext, stage: str) -> None:
    """Check completed steps that a pre-contract resume will replay without executing."""
    earlier = {
        "impcode": ("analyze",),
        "deployment": ("analyze", "impcode"),
        "test": ("analyze", "impcode"),
    }
    for previous in earlier.get(stage, ()):
        outputs = _completed_commands(context, previous)
        required = f"{feature}/{FEATURE_OUTPUTS[previous]}"
        for output in outputs:
            receipt = output.get("completion")
            artifacts = receipt.get("artifacts") if isinstance(receipt, dict) else None
            if (
                not isinstance(artifacts, dict)
                or required not in artifacts
                or not (root / required).is_file()
            ):
                raise ValueError(
                    f"Earlier {previous} checkpoint lacks {required}. Start a new speckit run."
                )
        if previous == "impcode" and outputs:
            verify_coding_status(root, feature)


def feature_environment(root: Path, feature: str) -> dict[str, str]:
    return {
        **os.environ,
        "SPECIFY_INIT_DIR": root.as_posix(),
        "SPECIFY_FEATURE_DIRECTORY": feature,
        "SPECIFY_FEATURE_NO_PERSIST": "1",
    }


def principal_output(stage: str, feature: str | None) -> str | None:
    if feature is not None and stage in FEATURE_OUTPUTS:
        return f"{feature}/{FEATURE_OUTPUTS[stage]}"
    return SHARED_OUTPUTS.get(stage)


def verify_coding_status(root: Path, feature: str) -> None:
    scripts = shared_scripts_source(core_pack=_locate_core_pack(), repo_root=_repo_root())
    helper = scripts / "python/code_progress.py"
    try:
        result = subprocess.run(
            [sys.executable, "-E", "-B", str(helper), "status"],
            cwd=root,
            env=feature_environment(root, feature),
            capture_output=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )
        if result.returncode:
            raise ValueError(result.stderr.strip() or f"status exited {result.returncode}")
        status = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"Cannot verify CODE_COMPLETE for {feature}: {exc}") from exc
    if not isinstance(status, dict) or status.get("code_complete") is not True:
        raise ValueError(f"Coding progress for {feature} has unfinished tasks (CODE_COMPLETE is false)")
