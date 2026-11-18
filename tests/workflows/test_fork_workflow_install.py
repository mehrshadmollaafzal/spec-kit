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
