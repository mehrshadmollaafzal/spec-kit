"""Layout-migration guards for ``specify integration upgrade``."""

from __future__ import annotations

import json
from pathlib import Path, PurePath
from typing import TYPE_CHECKING, Any

from packaging.version import InvalidVersion, Version

if TYPE_CHECKING:
    from .base import IntegrationBase
    from .manifest import IntegrationManifest


# Hermes' inherited global layout has no per-file manifest. These are the
# retained command slots it populated before the fork's eleven-stage rollout.
_UPSTREAM_RETAINED_COMMANDS = frozenset({"constitution", "specify", "clarify", "plan", "analyze"})
_UPSTREAM_RETIRED_COMMANDS = ("checklist", "converge", "implement", "tasks")


def _legacy_hermes_manifest(version: object) -> bool:
    if not isinstance(version, str):
        return True
    try:
        return Version(version) < Version("2.0.0.dev0")
    except InvalidVersion:
        return True


def _preflight_core_commands(
    integration: IntegrationBase,
    project_root: Path,
    old_manifest: IntegrationManifest,
    parsed_options: dict[str, Any] | None,
) -> set[str]:
    """Check bundled command destinations before any renderer writes."""
    from . import BUILTIN_INTEGRATION_KEYS
    from .base import _CORE_COMMAND_TEMPLATE_ORDER

    # External adapters have their own declared ownership contract.
    if integration.key not in BUILTIN_INTEGRATION_KEYS or integration.key == "none":
        return set()

    templates = {template.stem for template in integration.list_command_templates()}
    owned = old_manifest.files
    global_layout = integration.key == "hermes"
    legacy_global_layout = global_layout and _legacy_hermes_manifest(old_manifest.version)
    if global_layout:
        # Even a current project manifest cannot establish which projects own
        # or still use these profile-wide legacy command slots.
        occupied_retired_slots = [
            path
            for name in _UPSTREAM_RETIRED_COMMANDS
            for path in integration.core_command_paths(project_root, name, parsed_options)
            if path.parent.is_symlink() or path.is_symlink() or path.exists()
        ]
        if occupied_retired_slots:
            paths = "\n".join(f"  {path}" for path in occupied_retired_slots)
            raise ValueError(
                "Retired Hermes command slots are still present in the shared profile:\n"
                f"{paths}\n"
                "Check whether other projects still use these skills. Move the listed skill "
                "directories outside ~/.hermes/skills to preserve them, then retry the upgrade."
            )
    required = set()
    for name in _CORE_COMMAND_TEMPLATE_ORDER:
        if name not in templates:
            raise ValueError(f"Missing command template for speckit-{name}")
        for path in integration.core_command_paths(project_root, name, parsed_options):
            target = path.parent.resolve() / path.name
            if global_layout:
                relative = target.as_posix()
                unowned = legacy_global_layout and name not in _UPSTREAM_RETAINED_COMMANDS
            else:
                relative = target.relative_to(project_root).as_posix()
                unowned = relative not in owned
                required.add(relative)
            if unowned and (target.exists() or target.is_symlink()):
                raise ValueError(
                    f"Command ownership conflict: {relative} is untracked. "
                    "Move the existing file to a separate location, then retry the upgrade."
                )
    return required


def _verify_core_commands(
    project_root: Path, manifest: IntegrationManifest, required: set[str],
) -> None:
    """Confirm the on-disk command inventory before publishing a workflow."""
    tracked = manifest.files
    missing = [
        path for path in sorted(required)
        if path not in tracked or not (project_root / path).is_file()
    ]
    if missing:
        raise ValueError(f"Missing core command files: {', '.join(missing)}")


def _check_lean_preset(project_root: Path) -> None:
    """Refuse to re-register the upstream Lean workflow's retired contract."""
    from ..presets import PresetManager, PresetManifest

    manager = PresetManager(project_root)
    metadata = manager.registry.get("lean")
    if metadata is None:
        return
    manifest = PresetManifest(manager.presets_dir / "lean" / "preset.yml")
    legacy_commands = ("speckit.plan", "speckit.tasks", "speckit.implement")
    legacy_skills = {
        name for command in legacy_commands for name in manager._skill_names_for_command(command)
    }
    for field, legacy_names in (
        ("registered_commands", legacy_commands), ("registered_skills", legacy_skills),
    ):
        registered = metadata.get(field, {})
        groups = registered.values() if isinstance(registered, dict) else (registered,)
        if any(
            name in legacy_names
            for names in groups if isinstance(names, list)
            for name in names if isinstance(name, str)
        ):
            break
    else:
        if (
            "1.0.0" not in (metadata.get("version"), manifest.version)
            and not any(
                template.get("type") == "command"
                and (
                    template.get("name") in legacy_commands
                    or template.get("replaces") in legacy_commands
                )
                for template in manifest.templates
            )
        ):
            return
    raise ValueError(
        f"Lean preset {manifest.version} conflicts with the eleven-command workflow. "
        "Back up any customized preset sources and commands. "
        "Run 'specify preset update lean' (or 'specify preset remove lean'), then retry the upgrade. "
        "Review any modified generated files reported after updating the preset before using --force."
    )


def _manifest_tracks_skill_layout(manifest) -> bool:
    """Return True when *manifest* tracks any skills-layout artifact.

    A skill scaffold is written as ``.../speckit-<name>/SKILL.md``, so a
    manifest whose tracked files include a ``/SKILL.md`` key is in the skills
    layout; otherwise it is in the command layout. Used by ``upgrade`` to
    detect a dual-mode agent (e.g. Bob) flipping between the legacy commands
    layout and the skills layout so orphaned extension artifacts from the old
    layout can be reconciled.
    """
    return any(str(rel).endswith("/SKILL.md") for rel in manifest.files)


def _manifest_path_under(rel_path: str, root: str) -> bool:
    """Return True when manifest key *rel_path* is inside project-relative *root*."""
    normalized_root = PurePath(root).as_posix().strip("/")
    normalized_rel = PurePath(rel_path).as_posix().strip("/")
    if not normalized_root:
        return False
    return normalized_rel == normalized_root or normalized_rel.startswith(
        f"{normalized_root}/"
    )


def _legacy_command_root_changed(
    integration,
    project_root: Path,
    old_manifest,
    new_manifest,
) -> bool:
    """Return True when command artifacts moved from legacy_dir to canonical dir."""
    config = integration.registrar_config or {}
    canonical = config.get("dir")
    legacy = config.get("legacy_dir")
    if (
        not isinstance(canonical, str)
        or not canonical.strip()
        or not isinstance(legacy, str)
        or not legacy.strip()
        or PurePath(canonical).as_posix() == PurePath(legacy).as_posix()
    ):
        return False

    canonical_dir = project_root / canonical
    legacy_dir = project_root / legacy
    if not canonical_dir.is_dir() or not legacy_dir.is_dir():
        return False

    old_had_legacy = any(
        _manifest_path_under(rel, legacy) for rel in old_manifest.files
    )
    new_has_canonical = any(
        _manifest_path_under(rel, canonical) for rel in new_manifest.files
    )
    return old_had_legacy and new_has_canonical


def _legacy_command_root_upgrade_pending(integration, old_manifest) -> bool:
    """Return True when the old manifest tracks command files under legacy_dir."""
    config = integration.registrar_config or {}
    canonical = config.get("dir")
    legacy = config.get("legacy_dir")
    if (
        not isinstance(canonical, str)
        or not canonical.strip()
        or not isinstance(legacy, str)
        or not legacy.strip()
        or PurePath(canonical).as_posix() == PurePath(legacy).as_posix()
    ):
        return False
    return any(_manifest_path_under(rel, legacy) for rel in old_manifest.files)


class _PresetRegistryUnreadableError(Exception):
    """Raised when an existing preset registry cannot be read or parsed.

    Distinct from a *genuinely absent* registry (no presets installed): an
    unreadable registry means we cannot verify whether preset overrides would
    be orphaned by a layout change, so the migration must be rejected rather
    than proceeding on a false "no presets" assumption.
    """


def _installed_presets_affecting_agent(
    project_root,
    agent_key: str,
    *,
    include_skills: bool = True,
) -> list[str]:
    """Return IDs of installed presets with artifacts registered for *agent_key*.

    Preset registration is active-agent-only (#2948): command overrides are
    written for the active non-skills agent and skills for the active skills
    agent, tracked per preset in ``registered_commands`` /
    ``registered_skills``. Entries for *other* agents may still exist from
    when those agents were active. Callers use this to reject command-root or
    command↔skills layout migrations before mutation: preset rescaffolding is
    best-effort and cannot guarantee every tracked artifact has a replacement.

    Fails **closed**: a genuinely absent registry (no presets ever installed)
    returns an empty list, but if the registry file exists and cannot be read
    or parsed (e.g. a permission error or corruption) this raises
    :class:`_PresetRegistryUnreadableError`.  Reporting "no presets" in that
    case would let a ``--force`` layout-changing upgrade delete
    preset-overridden files while their registry state can't be reconciled —
    the exact inconsistency the guard exists to prevent.
    """
    from ..presets import PresetRegistry

    registry_path = (
        Path(project_root) / ".specify" / "presets" / PresetRegistry.REGISTRY_FILE
    )
    # Genuinely absent registry → no presets installed → safe to proceed.
    if not registry_path.exists():
        return []

    # The registry exists: any failure to read or parse it must surface as an
    # error, not be swallowed into an empty ("no presets") result.
    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise _PresetRegistryUnreadableError(str(exc)) from exc
    if not isinstance(data, dict) or not isinstance(data.get("presets", {}), dict):
        raise _PresetRegistryUnreadableError(
            "preset registry structure is malformed"
        )

    affected: list[str] = []
    for preset_id, meta in data.get("presets", {}).items():
        # A malformed entry means we cannot verify whether this preset owns
        # artifacts for the agent, so fail closed rather than skip it.
        if not isinstance(meta, dict):
            raise _PresetRegistryUnreadableError(
                f"preset '{preset_id}' entry is malformed"
            )
        registered_commands = meta.get("registered_commands", {})
        if not isinstance(registered_commands, dict) or not all(
            isinstance(names, list) for names in registered_commands.values()
        ):
            raise _PresetRegistryUnreadableError(
                f"preset '{preset_id}' registered_commands is malformed"
            )
        registered_skills = meta.get("registered_skills", [])
        if isinstance(registered_skills, dict):
            # Per-agent provenance ({agent: [skill names]}): only entries for
            # *this* agent make the preset affect it. Values must be lists —
            # anything else (e.g. null) leaves ownership undecidable, so fail
            # closed rather than read it as "no artifacts".
            if not all(
                isinstance(names, list) for names in registered_skills.values()
            ):
                raise _PresetRegistryUnreadableError(
                    f"preset '{preset_id}' registered_skills is malformed"
                )
            has_skills = include_skills and bool(
                registered_skills.get(agent_key)
            )
        elif isinstance(registered_skills, (list, tuple)):
            # Legacy flat list: not agent-scoped, so any recorded skill may
            # belong to this agent — fail closed and count it as affecting.
            has_skills = include_skills and bool(registered_skills)
        else:
            raise _PresetRegistryUnreadableError(
                f"preset '{preset_id}' registered_skills is malformed"
            )
        has_commands = bool(registered_commands.get(agent_key))
        if has_commands or has_skills:
            affected.append(preset_id)
    return affected


def _installed_command_presets_affecting_agent(
    project_root,
    agent_key: str,
) -> list[str]:
    """Return installed presets with command artifacts registered for *agent_key*."""
    return _installed_presets_affecting_agent(
        project_root,
        agent_key,
        include_skills=False,
    )
