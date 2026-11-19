"""Install and reconcile the fork's single core workflow under the workflow lock."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Literal

from .._assets import _locate_bundled_workflow
from ..integrations._file_changes import changing_file
from . import _commands as cli
from .catalog import WorkflowCatalogError, WorkflowRegistry
from .catalog._domain import packaged_speckit
from .catalog._versions import select_release
from .engine import WorkflowDefinition, validate_workflow
from .overlay import WorkflowResolver
from .overlay.composer import StepListComposer

# Git blob contents (LF) at the pre-fork revision 2ee2b1e8005905db05f5717300a469b3068b908f.
_UPSTREAM_102 = "dc0409237d62f267b2d496022cbafadb1fcebe2c1335127fead51dbcd5acbd84"
# Stock 2.0.0 before the bundled stage completion contract was declared.
_FORK_200 = "a61ed36e7e2a163321dbce93be244194690d0fae5d2de664432e323963607802"


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _check_upgrade_definition(
    project: Path, candidate: Path, version: str | None, origin: str
) -> None:
    """Validate the workflow that a new run would resolve, including active overlays."""
    from ..extensions import CORE_COMMAND_NAMES
    from .composition import resolve_target

    def validate_commands(definition, ancestry):
        def check(step):
            kind = step.get("type", "command")
            if kind == "workflow":
                child = resolve_target(project, step.get("workflow"), ancestry)
                return validate_commands(child, (*ancestry, child.id))
            if kind != "command":
                return []
            command = step.get("command")
            if (
                not isinstance(command, str)
                or command.removeprefix("speckit.") not in CORE_COMMAND_NAMES
            ):
                return [f"step {step['id']!r}: cannot verify core command {command!r}"]
            if step.get("verify_completion") is not True:
                return [
                    f"step {step['id']!r}: {command} requires verify_completion: true and capture: true"
                ]
            return []

        return validate_workflow(definition, validate_step=check)

    try:
        layers = WorkflowResolver(project).collect_all_layers("speckit")
        definition = WorkflowDefinition.from_yaml(candidate)
        if any(layer.tier != "base" for layer in layers):
            # The composer needs well-formed step mappings to address its edits.
            errors = validate_workflow(definition)
            if errors:
                raise ValueError("; ".join(errors))
            layers = [
                replace(layer, path=candidate) if layer.tier == "base" else layer
                for layer in layers
            ]
            definition, _ = StepListComposer().compose(layers)
            if definition is None:
                raise ValueError("installed workflow.yml is missing")
        if definition.id != "speckit" or definition.version != version:
            raise ValueError("workflow ID or version differs from its registry entry")
        errors = validate_commands(definition, ("speckit",))
        if errors:
            raise ValueError("; ".join(errors))
    except (OSError, ValueError, RecursionError) as exc:
        raise ValueError(
            f"Speckit workflow compatibility conflict ({origin}): {exc}. "
            "Update the workflow or its overlays and retry. To replace the base, back up "
            ".specify/workflows/speckit and its registry entry, then run:\n"
            "  specify workflow add speckit --bundled\n"
            "Then rerun integration upgrade."
        ) from exc


def install_speckit(
    project: Path,
    mode: Literal["init", "preflight", "upgrade", "replace"],
    *,
    version: str | None = None,
) -> str:
    workflows = project / ".specify/workflows"
    cli._reject_unsafe_dir(project / ".specify", ".specify")
    cli._reject_unsafe_dir(workflows, ".specify/workflows")
    upgrading = mode in {"preflight", "upgrade"}
    if upgrading and not workflows.exists():
        # A project without workflow storage has nothing to reconcile.
        return "not installed"
    with cli._workflow_install_transaction(project):
        directory = cli._safe_workflow_id_dir(workflows, "speckit")
        target = directory / "workflow.yml"
        registry = WorkflowRegistry(project)
        existing = registry.get("speckit")
        if mode == "init" and existing is not None:
            return "already installed"
        if upgrading and not registry.is_installed("speckit") and not target.exists():
            return "not installed"

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
            or info.get("bundled_sha256", info.get("sha256")) != canonical
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
        if mode != "replace" and (target.exists() or registry.is_installed("speckit")):
            installed = target.read_bytes() if target.is_file() else b""
            installed_digest = _digest(installed.replace(b"\r\n", b"\n"))
            recorded = existing if isinstance(existing, dict) else {}
            current = (
                recorded.get("version") == definition.version
                and installed_digest == canonical
            )
            legacy = (
                (recorded.get("version"), installed_digest)
                in {("1.0.2", _UPSTREAM_102), ("2.0.0", _FORK_200)}
            )
            if (
                recorded.get("source") != "bundled"
                or not (current or legacy)
                or ("sha256" in recorded and recorded["sha256"] != _digest(installed))
            ):
                if (
                    upgrading
                    and isinstance(recorded.get("source"), str)
                    and recorded["source"]
                ):
                    origin = {
                        "bundled": "customized bundle",
                        "catalog": "catalog installation",
                    }.get(recorded["source"], "explicit workflow source")
                    _check_upgrade_definition(
                        project, target, recorded.get("version"), origin
                    )
                    return f"preserved compatible {origin}"
                raise ValueError(
                    "Speckit workflow compatibility conflict: unrecognized ownership. Back up "
                    "your workflow, run 'specify workflow add speckit --bundled' to replace it, "
                    "then rerun integration upgrade."
                )
            if upgrading:
                _check_upgrade_definition(
                    project,
                    asset / "workflow.yml",
                    definition.version,
                    "bundled upgrade",
                )
            if (
                current
                and installed == content
                and all(recorded.get(k) == v for k, v in entry.items())
            ):
                return "already current"

        if mode == "preflight":
            return "ready to upgrade"
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
