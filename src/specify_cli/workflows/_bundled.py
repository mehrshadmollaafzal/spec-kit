"""Install and reconcile the fork's single core workflow under the workflow lock."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from .._assets import _locate_bundled_workflow
from ..integrations._file_changes import changing_file
from . import _commands as cli
from .catalog import WorkflowCatalogError, WorkflowRegistry
from .catalog._domain import packaged_speckit
from .catalog._versions import select_release
from .engine import WorkflowDefinition, validate_workflow

# Git blob contents (LF) at the pre-fork revision 2ee2b1e8005905db05f5717300a469b3068b908f.
_UPSTREAM_102 = "dc0409237d62f267b2d496022cbafadb1fcebe2c1335127fead51dbcd5acbd84"


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def install_speckit(
    project: Path,
    mode: Literal["init", "upgrade", "replace"],
    *,
    version: str | None = None,
) -> str:
    workflows = project / ".specify/workflows"
    cli._reject_unsafe_dir(project / ".specify", ".specify")
    cli._reject_unsafe_dir(workflows, ".specify/workflows")
    with cli._workflow_install_transaction(project):
        directory = cli._safe_workflow_id_dir(workflows, "speckit")
        target = directory / "workflow.yml"
        registry = WorkflowRegistry(project)
        existing = registry.get("speckit")
        if mode == "init" and existing is not None:
            return "already installed"
        if mode == "upgrade" and existing is None and not target.exists():
            return "not installed"
        if (
            mode == "upgrade"
            and isinstance(existing, dict)
            and existing.get("source") != "bundled"
        ):
            return (
                "preserved workflow from a custom source. Review its command references. "
                "To replace it after backup, run specify workflow add speckit --bundled."
            )

        asset = _locate_bundled_workflow("speckit")
        if asset is None:
            raise ValueError("Packaged speckit workflow is missing")
        content = (asset / "workflow.yml").read_bytes()
        # Compare the catalog digest of the Git blob even in a CRLF checkout.
        canonical = _digest(content.replace(b"\r\n", b"\n"))
        info = packaged_speckit()
        definition = WorkflowDefinition.from_string(content.decode("utf-8"))
        if (
            definition.id != "speckit"
            or info.get("id") != definition.id
            or info.get("version") != definition.version
            or info.get("sha256") != canonical
        ):
            raise ValueError(
                "Packaged speckit workflow ID, version or SHA-256 differs from its catalog"
            )
        if select_release(info, version) != info:
            raise ValueError(
                f"Packaged speckit workflow version {version} is unavailable"
            )
        errors = validate_workflow(definition)
        if errors:
            raise ValueError("Invalid packaged workflow: " + ", ".join(errors))
        entry = {
            "name": definition.name,
            "description": definition.description,
            "version": definition.version,
            "source": "bundled",
            "sha256": _digest(content),
        }
        if isinstance(existing, dict) and not existing.get("enabled", True):
            entry["enabled"] = False
        installed = None
        if mode != "replace" and (target.exists() or existing is not None):
            installed = target.read_bytes() if target.is_file() else b""
            installed_digest = _digest(installed.replace(b"\r\n", b"\n"))
            recorded = existing if isinstance(existing, dict) else {}
            current = (
                recorded.get("version") == definition.version
                and installed_digest == canonical
            )
            legacy = (
                recorded.get("version") == "1.0.2" and installed_digest == _UPSTREAM_102
            )
            if (
                recorded.get("source") != "bundled"
                or not (current or legacy)
                or ("sha256" in recorded and recorded["sha256"] != _digest(installed))
            ):
                raise ValueError(
                    "Installed speckit workflow differs from the recognized bundle. Back up "
                    "your workflow, run 'specify workflow add speckit --bundled' to replace it, "
                    "then rerun integration upgrade."
                )
            if (
                current
                and installed == content
                and all(recorded.get(k) == v for k, v in entry.items())
            ):
                return "already current"

        existed = directory.exists()
        staged = cli._stage_workflow_file(
            directory, use_project_file_mode=not target.exists()
        )
        try:
            staged.write_bytes(content)
            with changing_file(target):
                backup = cli._commit_workflow_file(
                    staged, target, existed or target.exists()
                )
                try:
                    if mode != "replace":
                        # Check the actual inode moved aside. An editor can save
                        # new bytes without taking the CLI's workflow lock.
                        if backup is not None and (
                            backup.is_symlink() or not backup.is_file()
                        ):
                            raise ValueError(
                                "Workflow changed during migration; review it and retry"
                            )
                        previous = backup.read_bytes() if backup is not None else None
                        if previous != installed:
                            raise ValueError(
                                "Workflow changed during migration; review it and retry"
                            )
                    registry.add("speckit", entry)
                except BaseException:
                    cli._rollback_committed_workflow_file(
                        target, directory, existed, backup
                    )
                    raise
            cli._discard_committed_backup_file(backup)
        except BaseException:
            cli._safe_discard_staged_workflow_file(staged, directory, existed)
            raise
    return f"installed v{definition.version}"


def install_speckit_or_exit(
    project: Path, mode: Literal["upgrade", "replace"], *, version: str | None = None
) -> None:
    try:
        result = install_speckit(project, mode, version=version)
    except (OSError, ValueError, WorkflowCatalogError) as exc:
        cli.console.print(f"[red]Error:[/red] {cli._escape_markup(str(exc))}")
        raise cli.typer.Exit(1) from exc
    cli.console.print(f"speckit workflow: {result}")
