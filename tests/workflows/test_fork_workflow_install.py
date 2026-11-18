"""Installed workflow regressions using a genuine parent-wheel Codex project."""

import hashlib
import io
import json
import time
from pathlib import Path
from zipfile import ZipFile

import pytest
from typer.testing import CliRunner

from specify_cli import app
from specify_cli.workflows.base import RunStatus, StepResult, StepStatus
from specify_cli.workflows.catalog import WorkflowCatalog, WorkflowRegistry
from specify_cli.workflows.engine import WorkflowEngine
from specify_cli.workflows.step.command import CommandStep

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/fork-workflow/upstream-codex-init.zip"
WORKFLOW = ".specify/workflows/speckit/workflow.yml"
UPSTREAM = "https://raw.githubusercontent.com/github/spec-kit/main/workflows/"
COMMANDS = "constitution specify clarify architecture environment plan taskscode analyze impcode deployment test".split()


@pytest.fixture
def legacy(tmp_path, monkeypatch):
    root = tmp_path / "project"
    # Output of init --integration codex --script py --ignore-agent-tools using
    # the wheel built from 2ee2b1e8005905db05f5717300a469b3068b908f.
    with ZipFile(FIXTURE) as archive:
        archive.extractall(root)
    monkeypatch.chdir(root)
    monkeypatch.setenv("SPECIFY_INIT_DIR", str(root))
    return root


def cli(*args):
    return CliRunner().invoke(app, list(args))


def commands(steps):
    for step in steps:
        if "command" in step:
            yield step["command"].removeprefix("speckit.")
        for branch in ("then", "else"):
            yield from commands(step.get(branch, []))


def assert_installed(root):
    definition = WorkflowEngine(root).load_workflow("speckit")
    assert list(commands(definition.steps)) == COMMANDS
    record = WorkflowRegistry(root).get("speckit")
    assert record["version"] == definition.version == "2.0.0"
    assert record["source"] == "bundled"
    assert (
        record["sha256"] == hashlib.sha256((root / WORKFLOW).read_bytes()).hexdigest()
    )


def test_parent_upgrade_uses_fork_for_new_runs(legacy, monkeypatch):
    from specify_cli.integrations.manifest import IntegrationManifest

    engine = WorkflowEngine(legacy)
    invoked = []

    def dispatch(self, config, context):
        invoked.append(config["command"])
        return StepResult(status=StepStatus.COMPLETED)

    monkeypatch.setattr(CommandStep, "execute", dispatch)

    def new_run():
        return engine.execute(
            engine.load_workflow("speckit"),
            inputs={"integration": "codex", "spec": "feature"},
        )

    old = new_run()
    assert old.status is RunStatus.PAUSED
    assert invoked == ["speckit.specify"]
    history = {
        p: p.read_bytes()
        for p in (legacy / ".specify/workflows/runs" / old.run_id).rglob("*")
        if p.is_file()
    }
    assert history
    preserved = {}
    for name, content in {
        "src/app.py": "name = 'existing app'",
        "specs/001-app/tasks.md": "- [x] T001 Original task",
        "specs/001-app/code-progress.json": '{"schema_version":1,"inputs":{},"tasks":{},"history":[]}',
        ".specify/feature.json": '{"feature_directory":"specs/001-app"}',
    }.items():
        path = legacy / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        preserved[path] = path.read_bytes()
    registry = WorkflowRegistry(legacy).registry_path
    migrated_registry = None
    for _ in range(2):
        result = cli("integration", "upgrade", "codex")
        assert result.exit_code == 0, result.output
        assert_installed(legacy)
        if migrated_registry is not None:
            assert registry.read_bytes() == migrated_registry
        migrated_registry = registry.read_bytes()
        assert {
            p.name.removeprefix("speckit-")
            for p in (legacy / ".agents/skills").iterdir()
            if (p / "SKILL.md").exists()
        } == set(COMMANDS)
        for key in ("codex", "speckit"):
            assert not IntegrationManifest.load(key, legacy).check_modified()
        assert {p: p.read_bytes() for p in history} == history
        assert {p: p.read_bytes() for p in preserved} == preserved
    invoked.clear()
    assert new_run().status is RunStatus.PAUSED
    assert invoked == ["speckit.constitution", "speckit.specify"]


def test_parent_upgrade_preserves_customized_workflow(legacy):
    path = legacy / WORKFLOW
    modified = path.read_bytes() + b"\n# team customization\n"
    path.write_bytes(modified)
    registry = WorkflowRegistry(legacy).registry_path
    before = registry.read_bytes()
    result = cli("integration", "upgrade", "codex")
    assert result.exit_code != 0
    assert "workflow add speckit" in result.output
    assert path.read_bytes() == modified
    assert registry.read_bytes() == before
    assert cli("workflow", "add", "speckit", "--bundled").exit_code == 0
    assert cli("integration", "upgrade", "codex").exit_code == 0
    assert_installed(legacy)


def test_parent_upgrade_registry_failure_restores_workflow(legacy, monkeypatch):
    path = legacy / WORKFLOW
    registry = WorkflowRegistry(legacy).registry_path
    before = (path.read_bytes(), registry.read_bytes())

    def fail(self):
        raise OSError("injected registry failure")

    monkeypatch.setattr(WorkflowRegistry, "save", fail)
    result = cli("integration", "upgrade", "codex")
    assert result.exit_code != 0
    assert "injected registry failure" in result.output
    assert (path.read_bytes(), registry.read_bytes()) == before


def test_default_readd_with_cached_upstream_catalog(legacy, monkeypatch):
    from specify_cli.authentication import http

    catalog = WorkflowCatalog(legacy)
    catalog.cache_dir.mkdir(exist_ok=True)
    url = UPSTREAM + "speckit/workflow.yml"
    with ZipFile(FIXTURE) as archive:
        content = archive.read(WORKFLOW)

    class Response(io.BytesIO):
        def geturl(self):
            return url

    def open_url(target, **kwargs):
        assert target == url
        return Response(content)

    monkeypatch.setattr(http, "open_url", open_url)
    for remote, entries in [
        (
            UPSTREAM + "catalog.json",
            {"speckit": {"id": "speckit", "version": "1.0.2", "url": url}},
        ),
        (UPSTREAM + "catalog.community.json", {}),
    ]:
        cache, meta = catalog._get_cache_paths(remote)
        cache.write_text(json.dumps({"workflows": entries}))
        meta.write_text(json.dumps({"fetched_at": time.time()}))
    for _ in range(2):
        result = cli("workflow", "add", "speckit")
        assert result.exit_code == 0, result.output
        assert_installed(legacy)
    assert (
        hashlib.sha256(content).digest()
        != hashlib.sha256((legacy / WORKFLOW).read_bytes()).digest()
    )


def test_fresh_init_offline_add_and_bundled_update(tmp_path, monkeypatch):
    from specify_cli.authentication import http

    monkeypatch.setattr(
        http, "open_url", lambda *a, **kw: pytest.fail("unexpected download")
    )
    project = tmp_path / "fresh"
    result = cli(
        "init",
        str(project),
        "--integration",
        "codex",
        "--script",
        "py",
        "--ignore-agent-tools",
    )
    assert result.exit_code == 0, result.output
    monkeypatch.chdir(project)
    assert_installed(project)
    for args in [
        ("add", "speckit"),
        ("update", "speckit"),
        ("add", "speckit", "--bundled"),
    ]:
        result = cli("workflow", *args)
        assert result.exit_code == 0, result.output
        assert_installed(project)
    assert cli("workflow", "remove", "speckit").exit_code == 0
    assert not (project / WORKFLOW).exists()
    assert cli("workflow", "add", "speckit").exit_code == 0
    assert_installed(project)


@pytest.mark.parametrize("field", ["version", "sha256", "id"])
def test_invalid_packaged_catalog_preserves_install(legacy, monkeypatch, field):
    from specify_cli.workflows import _bundled

    before = (
        (legacy / WORKFLOW).read_bytes(),
        WorkflowRegistry(legacy).registry_path.read_bytes(),
    )
    info = _bundled.packaged_speckit()
    info[field] = "mismatched"
    monkeypatch.setattr(_bundled, "packaged_speckit", lambda: info)
    result = cli("workflow", "add", "speckit")
    assert result.exit_code != 0 and "catalog" in result.output
    assert (
        (legacy / WORKFLOW).read_bytes(),
        WorkflowRegistry(legacy).registry_path.read_bytes(),
    ) == before


def test_explicit_catalog_wins_and_checks_download_version(legacy, monkeypatch):
    from specify_cli.authentication import http

    result = cli("workflow", "update", "speckit")
    assert result.exit_code == 0, result.output
    assert_installed(legacy)
    content = (
        (legacy / WORKFLOW)
        .read_bytes()
        .replace(b"version: 2.0.0", b"version: 3.0.0", 1)
    )
    advertised = "4.0.0"
    catalog_url = "https://example.com/team/catalog.json"
    asset_url = "https://example.com/team/workflow.yml"
    monkeypatch.setenv("SPECKIT_WORKFLOW_CATALOG_URL", catalog_url)

    def response(url, **kwargs):
        class Response(io.BytesIO):
            def geturl(self):
                return url

        if url == asset_url:
            return Response(content)
        assert url == catalog_url
        return Response(
            json.dumps(
                {
                    "workflows": {
                        "speckit": {
                            "id": "speckit",
                            "version": advertised,
                            "url": asset_url,
                            "sha256": hashlib.sha256(content).hexdigest(),
                        }
                    }
                }
            ).encode()
        )

    monkeypatch.setattr(http, "open_url", response)
    registry = WorkflowRegistry(legacy).registry_path
    before = (registry.read_bytes(), (legacy / WORKFLOW).read_bytes())
    result = cli("workflow", "add", "speckit")
    assert result.exit_code != 0 and "does not match" in result.output
    assert before == (registry.read_bytes(), (legacy / WORKFLOW).read_bytes())
    cache, _ = WorkflowCatalog(legacy)._get_cache_paths(catalog_url)
    cache.unlink()
    advertised = "3.0.0"
    result = cli("workflow", "add", "speckit")
    assert result.exit_code == 0, result.output
    assert (legacy / WORKFLOW).read_bytes() == content
    assert WorkflowRegistry(legacy).get("speckit")["source"] == "catalog"
    before = registry.read_bytes()
    assert_codex_upgrade(legacy)
    assert registry.read_bytes() == before
    assert (legacy / WORKFLOW).read_bytes() == content
    assert WorkflowEngine(legacy).load_workflow("speckit").version == "3.0.0"
    assert cli("workflow", "add", "speckit", "--bundled").exit_code == 0
    assert_installed(legacy)


def test_upgrade_keeps_edit_made_while_replacement_is_staged(legacy, monkeypatch):
    from specify_cli.workflows import _commands

    target = legacy / WORKFLOW
    edited = target.read_bytes() + b"\n# team edit during upgrade\n"
    registry = WorkflowRegistry(legacy).registry_path
    before = registry.read_bytes()
    commit = _commands._commit_workflow_file

    def edit_before_swap(staged, destination, existed):
        destination.write_bytes(edited)
        return commit(staged, destination, existed)

    monkeypatch.setattr(_commands, "_commit_workflow_file", edit_before_swap)
    result = cli("integration", "upgrade", "codex")
    assert result.exit_code != 0
    assert target.read_bytes() == edited
    assert registry.read_bytes() == before


def test_bare_speckit_id_and_explicit_local_source(legacy):
    local = legacy / "speckit"
    local.mkdir()
    definition = (legacy / WORKFLOW).read_bytes()
    (local / "workflow.yml").write_bytes(definition)
    result = cli("workflow", "add", "speckit", "--version", "2.0.0")
    assert result.exit_code == 0, result.output
    assert_installed(legacy)
    result = cli("workflow", "add", "--dev", "speckit")
    assert result.exit_code == 0, result.output
    assert (legacy / WORKFLOW).read_bytes() == definition
    assert WorkflowRegistry(legacy).get("speckit")["source"] == "speckit"
    before = project_files(legacy)
    result = cli("integration", "upgrade", "codex")
    assert result.exit_code == 1 and "speckit.tasks" in result.output
    assert project_files(legacy) == before


def project_files(project):
    # Advisory locks persist across operations and contain no installation data.
    return {
        p.relative_to(project): p.read_bytes()
        for p in project.rglob("*")
        if p.is_file() and p != project / ".specify/.workflow-install.lock"
    }


def assert_codex_upgrade(project):
    from specify_cli.integrations.manifest import IntegrationManifest

    result = cli("integration", "upgrade", "codex")
    assert result.exit_code == 0, result.output
    files = (project / ".agents/skills").glob("speckit-*/SKILL.md")
    assert {p.parent.name for p in files} == {"speckit-" + cmd for cmd in COMMANDS}
    for key in ("codex", "speckit"):
        assert not IntegrationManifest.load(key, project).check_modified()


@pytest.mark.parametrize(
    "phase", ["infra", "skill", "manifest", "stale", "resync", "workflow", "registry"]
)
def test_failed_core_upgrade_restores_files_and_can_retry(legacy, monkeypatch, phase):
    from specify_cli import shared_infra
    from specify_cli.integrations import get_integration
    from specify_cli.integrations.manifest import IntegrationManifest
    from specify_cli.workflows import _commands

    preserved = (
        ".agents/skills/team/SKILL.md",
        ".specify/workflows/runs/historical/state.json",
    )
    for name in preserved:
        path = legacy / name
        path.parent.mkdir(parents=True)
        path.write_bytes(b"team owned")
    before = project_files(legacy)
    calls = 0
    owner, method = {
        "infra": (shared_infra, "_write_shared_bytes"),
        "skill": (get_integration("codex"), "write_file_and_record"),
        "manifest": (IntegrationManifest, "save"),
        "resync": (IntegrationManifest, "save"),
        "stale": (Path, "unlink"),
        "workflow": (_commands, "_commit_workflow_file"),
        "registry": (WorkflowRegistry, "save"),
    }[phase]
    original = getattr(owner, method)

    def fail(*args, **kwargs):
        nonlocal calls
        if phase == "stale":
            if args[0] == legacy / ".agents/skills/speckit-tasks/SKILL.md":
                raise OSError("injected stale failure")
            return original(*args, **kwargs)
        if phase == "resync" and args[0].key == "codex" and calls == 1:
            # The first manifest save completed. A second save can fail after
            # opening its journal entry but before replacing the destination.
            from specify_cli.integrations._file_changes import before_file_change

            before_file_change(args[0].manifest_path)
            raise OSError("injected resync failure")
        # Fail before the workflow swap or after a real, journalable write.
        if phase != "workflow":
            value = original(*args, **kwargs)
            if phase in ("manifest", "resync") and args[0].key != "codex":
                return value
            calls += 1
            if phase == "resync" and calls < 2:
                return value
        raise OSError(f"injected {phase} failure")

    with monkeypatch.context() as faults:
        faults.setattr(owner, method, fail)
        result = cli("integration", "upgrade", "codex")
    assert result.exit_code == 1, result.output
    assert f"injected {phase} failure" in result.output
    assert "upgraded successfully" not in result.output
    assert project_files(legacy) == before
    assert WorkflowEngine(legacy).load_workflow("speckit").version == "1.0.2"
    successful = None
    for _ in range(2):
        assert_codex_upgrade(legacy)
        assert_installed(legacy)
        for name in preserved:
            assert (legacy / name).read_bytes() == b"team owned"
        files = project_files(legacy)
        if successful is not None:
            assert files == successful
        successful = files


@pytest.mark.parametrize(
    ("source", "variant", "reason"),
    [
        ("catalog", "upstream", "speckit.tasks"),
        ("../team", "upstream", "speckit.tasks"),
        ("catalog", "nested", "speckit.implement"),
        ("catalog", "unverified", "verify_completion"),
        ("catalog", "malformed", "workflow"),
        ("bundled", "customized", "speckit.tasks"),
    ],
)
def test_custom_workflow_conflict_precedes_setup_and_is_recoverable(
    legacy, monkeypatch, source, variant, reason
):
    import specify_cli

    path = legacy / WORKFLOW
    content = path.read_bytes()
    version = "1.0.2"
    if variant in {"nested", "unverified"}:
        content = (ROOT / "workflows/speckit/workflow.yml").read_bytes()
        version = "2.0.0"
        if variant == "nested":
            content = content.replace(
                b"command: speckit.deployment", b"command: speckit.implement"
            )
        else:
            content = content.replace(
                b"verify_completion: true", b"verify_completion: false", 1
            )
    if variant == "customized":
        content += b"\n# team edit\n"
    if variant == "malformed":
        content = b"invalid: ["
    path.write_bytes(content)
    registry = WorkflowRegistry(legacy)
    registry.add(
        "speckit", {**registry.get("speckit"), "source": source, "version": version}
    )
    before = project_files(legacy)
    with monkeypatch.context() as guard:
        guard.setattr(
            specify_cli,
            "_install_shared_infra_or_exit",
            lambda *a, **kw: pytest.fail("preflight missed"),
        )
        result = cli("integration", "upgrade", "codex", "--force")
    assert result.exit_code == 1, result.output
    assert "conflict" in result.output.lower() and reason in result.output
    assert "workflow add speckit" in result.output
    assert project_files(legacy) == before
    result = cli("workflow", "add", "speckit", "--bundled")
    assert result.exit_code == 0, result.output
    for _ in range(2):
        assert_codex_upgrade(legacy)
        assert_installed(legacy)


@pytest.mark.parametrize("source", ["catalog", "../team", "bundled"])
def test_compatible_custom_workflow_preserves_provenance(legacy, source):
    path = legacy / WORKFLOW
    content = (
        (ROOT / "workflows/speckit/workflow.yml")
        .read_bytes()
        .replace(b"name: Full SDD Cycle", b"name: Team SDD Cycle")
    )
    path.write_bytes(content)
    registry = WorkflowRegistry(legacy)
    registry.add(
        "speckit", {**registry.get("speckit"), "source": source, "version": "2.0.0"}
    )
    before = registry.registry_path.read_bytes()
    for _ in range(2):
        assert_codex_upgrade(legacy)
        definition = WorkflowEngine(legacy).load_workflow("speckit")
        assert definition.name == "Team SDD Cycle"
        assert list(commands(definition.steps)) == COMMANDS
        assert path.read_bytes() == content
        assert registry.registry_path.read_bytes() == before


def test_new_core_skill_cannot_overwrite_an_unowned_team_skill(legacy):
    skill = legacy / ".agents/skills/speckit-architecture/SKILL.md"
    skill.parent.mkdir()
    skill.write_bytes(b"our existing architecture skill")
    before = project_files(legacy)
    result = cli("integration", "upgrade", "codex", "--force")
    assert result.exit_code == 1 and "speckit-architecture" in result.output
    assert project_files(legacy) == before
    skill.parent.rename(skill.parent.with_name("team-architecture"))
    assert_codex_upgrade(legacy)
    assert_installed(legacy)
    assert (
        skill.parent.parent / "team-architecture/SKILL.md"
    ).read_bytes() == b"our existing architecture skill"


def test_missing_manifest_cannot_report_a_pending_migration_as_complete(legacy):
    manifest = legacy / ".specify/integrations/codex.manifest.json"
    saved = manifest.read_bytes()
    manifest.unlink()
    before = project_files(legacy)
    result = cli("integration", "upgrade", "codex")
    assert result.exit_code == 1 and "restore" in result.output.lower()
    assert project_files(legacy) == before
    manifest.write_bytes(saved)
    assert_codex_upgrade(legacy)


@pytest.mark.parametrize("phase", ["templates", "manifest"])
def test_partial_skill_inventory_cannot_publish_workflow(legacy, monkeypatch, phase):
    from specify_cli.integrations import get_integration

    codex = get_integration("codex")
    templates = codex.list_command_templates()
    before = project_files(legacy)
    with monkeypatch.context() as faults:
        if phase == "templates":
            faults.setattr(
                codex,
                "list_command_templates",
                lambda: [p for p in templates if p.stem != "test"],
            )
        else:
            setup = codex.setup

            def omit_test(root, manifest, **options):
                setup(root, manifest, **options)
                manifest.remove(".agents/skills/speckit-test/SKILL.md")

            faults.setattr(codex, "setup", omit_test)
        result = cli("integration", "upgrade", "codex")
    assert result.exit_code == 1 and "speckit-test" in result.output
    assert project_files(legacy) == before
    assert_codex_upgrade(legacy)


def test_overlay_checked_against_prospective_bundle_before_writes(legacy):
    overlay = legacy / ".specify/workflows/overlays/speckit/team.yml"
    overlay.parent.mkdir(parents=True)
    overlay.write_text(
        "id: team\nextends: speckit\nedits:\n- replace: deployment\n"
        "  step:\n    id: team-deploy\n    command: speckit.converge\n"
    )
    before = project_files(legacy)
    result = cli("integration", "upgrade", "codex")
    assert result.exit_code == 1 and "speckit.converge" in result.output
    assert project_files(legacy) == before


def test_custom_workflow_edited_after_preflight_rolls_back_skills(legacy, monkeypatch):
    from specify_cli.integrations import command_upgrade

    target = legacy / WORKFLOW
    content = (ROOT / "workflows/speckit/workflow.yml").read_bytes()
    target.write_bytes(content)
    registry = WorkflowRegistry(legacy)
    registry.add(
        "speckit", {**registry.get("speckit"), "source": "catalog", "version": "2.0.0"}
    )
    before = project_files(legacy)
    edited = content.replace(b"command: speckit.test", b"command: speckit.checklist")
    resync = command_upgrade._resync_manifest_after_registration

    def edit_after_setup(*args, **kwargs):
        resync(*args, **kwargs)
        target.write_bytes(edited)

    monkeypatch.setattr(
        command_upgrade, "_resync_manifest_after_registration", edit_after_setup
    )
    result = cli("integration", "upgrade", "codex")
    assert result.exit_code == 1 and "speckit.checklist" in result.output
    assert project_files(legacy) == {**before, Path(WORKFLOW): edited}


def test_incomplete_skill_write_reports_original_for_manual_recovery(
    legacy, monkeypatch
):
    import tempfile

    skill = legacy / ".agents/skills/speckit-specify/SKILL.md"
    original = project_files(legacy)
    backup_parent = legacy.parent / "backups"
    backup_parent.mkdir()
    write = Path.write_bytes

    def partial_write(path, data):
        if path == skill:
            write(path, b"incomplete write")
            raise OSError("interrupted skill write")
        return write(path, data)

    with monkeypatch.context() as faults:
        faults.setattr(tempfile, "tempdir", str(backup_parent))
        faults.setattr(Path, "write_bytes", partial_write)
        result = cli("integration", "upgrade", "codex")
    assert result.exit_code == 1 and "Recovery snapshots retained" in result.output
    assert project_files(legacy) == {
        **original,
        skill.relative_to(legacy): b"incomplete write",
    }
    # Unobserved bytes could also belong to a concurrent editor. Recover the
    # prior version from the reported journal instead of overwriting that edit.
    snapshots = list(backup_parent.glob("speckit-integration-rollback-*/writes/*"))
    (saved,) = [
        p for p in snapshots if p.read_bytes() == original[skill.relative_to(legacy)]
    ]
    assert str(saved) in "".join(result.output.splitlines())
    skill.write_bytes(saved.read_bytes())
    assert_codex_upgrade(legacy)
    assert_installed(legacy)
