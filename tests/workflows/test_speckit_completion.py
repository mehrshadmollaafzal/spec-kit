"""Run the bundled stage contracts with deterministic agent responses."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from specify_cli import app
from specify_cli.integrations.codex import CodexIntegration
from specify_cli.workflows import engine as engine_module
from specify_cli.workflows._bundled import install_speckit
from specify_cli.workflows.base import RunStatus
from specify_cli.workflows.catalog import WorkflowRegistry
from specify_cli.workflows.engine import RunState, WorkflowDefinition, WorkflowEngine
from specify_cli.workflows.step import gate
from specify_cli.workflows.step.command import CommandStep

ROOT = Path(__file__).resolve().parents[2]
BUNDLED = ROOT / "workflows/speckit/workflow.yml"


def receipt(nonce, root, paths):
    return {
        "nonce": nonce,
        "status": "completed",
        "artifacts": {
            path: hashlib.sha256((root / path).read_bytes()).hexdigest()
            for path in paths
        },
    }


def write(root, path, content):
    destination = root / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")


def inventory(root, path, **records):
    write(root, path, "# Inventory\n\n```json\n" + json.dumps(
        {"schema_version": 1, **records}
    ) + "\n```\n")


@pytest.fixture
def engine(monkeypatch, project_dir):
    monkeypatch.delenv("SPECIFY_FEATURE_DIRECTORY", raising=False)
    monkeypatch.delenv("SPECIFY_FEATURE", raising=False)
    monkeypatch.delenv("SPECIFY_FEATURE_NO_PERSIST", raising=False)
    monkeypatch.setenv("SPECIFY_INIT_DIR", project_dir.as_posix())
    monkeypatch.setattr(gate, "sys", SimpleNamespace(stdin=SimpleNamespace(isatty=lambda: False)))
    return WorkflowEngine(project_dir)


def test_upgrade_replaces_previous_stock_bundle(project_dir):
    target = project_dir / ".specify/workflows/speckit/workflow.yml"
    assert install_speckit(project_dir, "init") == "installed v2.0.0"
    previous = BUNDLED.read_text(encoding="utf-8").replace("completion_contract: speckit\n", "", 1)
    advertised = json.loads((ROOT / "workflows/catalog.json").read_text(encoding="utf-8"))["workflows"]["speckit"]
    assert advertised["sha256"] == hashlib.sha256(previous.encode("utf-8")).hexdigest()
    target.write_bytes(previous.encode("utf-8"))
    registry = WorkflowRegistry(project_dir)
    registry.add("speckit", {
        **registry.get("speckit"),
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    })

    assert install_speckit(project_dir, "upgrade") == "installed v2.0.0"
    assert target.read_bytes() == BUNDLED.read_bytes()


def test_installed_lean_spec_without_checklist_passes_review_handoff(tmp_path, monkeypatch):
    root = tmp_path / "lean-project"
    result = CliRunner().invoke(app, [
        "init", str(root), "--integration", "codex", "--preset", "lean",
        "--script", "py", "--ignore-agent-tools", "--non-interactive",
    ])
    assert result.exit_code == 0, result.output
    skills = root / ".agents/skills"
    specify = (skills / "speckit-specify/SKILL.md").read_text(encoding="utf-8")
    clarify = (skills / "speckit-clarify/SKILL.md").read_text(encoding="utf-8")
    assert "Report `spec.md` as the principal artifact" in specify
    assert "Skip checklist re-validation when the file is absent" in clarify
    feature = "specs/lean-feature"
    spec = f"{feature}/spec.md"
    checklist = root / feature / "checklists/requirements.md"

    def dispatch(command, integration, model, args, context, *rest, **kwargs):
        stage = command.removeprefix("speckit.")
        if stage == "constitution":
            path = ".specify/memory/constitution.md"
        elif stage == "specify":
            path = spec
            write(root, ".specify/feature.json", json.dumps({"feature_directory": feature}))
        elif stage == "clarify":
            assert kwargs["env"]["SPECIFY_FEATURE_DIRECTORY"] == feature
            assert not checklist.exists()
            path = spec
        else:
            return {"exit_code": 1, "stderr": "Smoke ends after clarify", "stdout": ""}
        write(root, path, f"# Lean {stage}")
        nonce = re.search(r"completion_nonce=([a-f0-9]+)", args)[1]
        return {
            "exit_code": 0, "stderr": "",
            "stdout": "SPECKIT_RESULT " + json.dumps(receipt(nonce, root, [path])),
        }

    monkeypatch.setattr(CommandStep, "_try_dispatch", staticmethod(dispatch))
    monkeypatch.setattr(gate, "sys", SimpleNamespace(stdin=SimpleNamespace(isatty=lambda: False)))
    runner = WorkflowEngine(root)
    run = runner.execute(runner.load_workflow("speckit"), {"spec": "Lean feature"})
    assert run.status == RunStatus.PAUSED
    assert run.current_step_id == "review-spec"
    assert run.step_results["specify"]["output"]["feature_directory"] == feature
    resumed = runner.resume(run.run_id, {"speckit_review_spec_verdict": "approve"})
    assert resumed.step_results["clarify"]["status"] == "completed"
    assert (root / spec).read_text(encoding="utf-8") == "# Lean clarify"
    assert not checklist.exists()


@pytest.mark.parametrize("override", [False, True], ids=["pointer", "env"])
@pytest.mark.parametrize(
    ("script", "legacy"),
    [("python", False), ("powershell", False), ("bash", False), ("python", True)],
    ids=["python", "powershell", "bash", "legacy-checkpoint"],
)
def test_interleaved_resume_keeps_feature(engine, monkeypatch, override, script, legacy):
    root = engine.project_root
    feature_names = {"alpha": "features/alpha café", "beta": "specs/002-beta"}
    paths_only = {
        "python": [sys.executable, "scripts/python/check_prerequisites.py", "--json", "--paths-only"],
        "powershell": [
            shutil.which("powershell.exe"), "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", "scripts/powershell/check-prerequisites.ps1", "-Json", "-PathsOnly",
        ],
        "bash": [
            shutil.which("bash.exe" if os.name == "nt" else "bash"),
            "scripts/bash/check-prerequisites.sh", "--json", "--paths-only",
        ],
    }[script]
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    if os.name == "nt" and script == "bash":
        paths_only[0] = str(git_bash) if git_bash.is_file() else None
    if not paths_only[0]:
        pytest.skip(f"{script} unavailable")
    shutil.copytree(ROOT / "scripts", root / ".specify/scripts", ignore=shutil.ignore_patterns("__pycache__"))
    paths_only = [".specify/" + arg if arg.startswith("scripts/") else arg for arg in paths_only]
    # Only the agent is substituted. The real Codex dispatch path and process
    # capture launch the shim, whose helper inherits its environment.
    agent = root / "agent.py"
    agent.write_text(
        f"""
import hashlib, json, os, re, subprocess, sys
from pathlib import Path

root = Path.cwd()
command, args = sys.argv[1].split(' ', 1)
nonce = re.search(r"completion_nonce=([a-f0-9]+)", args)[1]
if command.endswith("-constitution"):
    path = root / ".specify/memory/constitution.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text("# Constitution", encoding="utf-8")
elif command.endswith("-specify"):
    name = args.split()[0]
    directory = {feature_names!r}[name]
    path = root / directory / "spec.md"
    path.parent.mkdir(parents=True)
    path.write_text(name, encoding="utf-8")
    (root / ".specify/feature.json").write_text(
        json.dumps({{"feature_directory": directory}}), encoding="utf-8"
    )
elif command.endswith("-clarify"):
    selected = subprocess.run({paths_only!r}, capture_output=True, encoding="utf-8")
    if selected.returncode:
        sys.exit(selected.stderr)
    selected_path = json.loads(selected.stdout)["FEATURE_SPEC"]
    if os.name == "nt" and {script!r} == "bash":
        selected_path = subprocess.check_output(
            ["C:/Program Files/Git/usr/bin/cygpath.exe", "-w", selected_path], encoding="utf-8"
        ).strip()
    path = Path(selected_path).resolve()
    path.write_text(path.read_text(encoding="utf-8") + " clarified for " + args.split()[0],
                    encoding="utf-8")
else:
    print("Agent stopped after clarification")
    sys.exit(1)
print("SPECKIT_RESULT " + json.dumps({{
    "nonce": nonce, "status": "completed",
    "artifacts": {{path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()}}
}}))
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        CodexIntegration, "build_exec_args",
        lambda self, prompt, **kwargs: [sys.executable, str(agent), prompt],
    )
    definition = WorkflowDefinition.from_yaml(BUNDLED)
    with monkeypatch.context() as legacy_engine:
        if legacy:
            definition.data.pop("completion_contract")
            legacy_engine.setattr(engine_module, "uses_speckit_contract", lambda _: False)
        alpha = engine.execute(definition, {"spec": "alpha", "integration": "codex"})
        beta = engine.execute(definition, {"spec": "beta", "integration": "codex"})
    assert alpha.status == beta.status == RunStatus.PAUSED
    assert alpha.current_step_id == beta.current_step_id == "review-spec"
    if override:
        monkeypatch.setenv("SPECIFY_FEATURE_DIRECTORY", (root / feature_names["beta"]).as_posix())

    pointer = root / ".specify/feature.json"
    saved_pointer = pointer.read_bytes()
    loaded = RunState.load(alpha.run_id, root)
    resumed = WorkflowEngine(root).resume(loaded.run_id, {"speckit_review_spec_verdict": "approve"})

    clarify = resumed.step_results["clarify"]
    assert clarify["status"] == "completed", clarify
    assert (root / feature_names["alpha"] / "spec.md").read_text(encoding="utf-8") == "alpha clarified for alpha"
    assert (root / feature_names["beta"] / "spec.md").read_text(encoding="utf-8") == "beta"
    assert pointer.read_bytes() == saved_pointer
    binding = resumed.step_results["specify"]["output"].get("feature_directory")
    assert binding == (None if legacy else feature_names["alpha"])


@pytest.mark.parametrize(
    ("mode", "expected", "error"),
    [
        ("analyze-input", "analyze", "analysis.md"),
        ("analyze-neighbor", "analyze", "analysis.md"),
        ("coding-pending", "impcode", "CODE_COMPLETE"),
        ("legacy-analyze-input", "test", "analysis.md"),
        ("legacy-coding-pending", "test", "CODE_COMPLETE"),
        ("coding-deleted", None, None),
    ],
)
def test_principal_artifacts_and_coding_status(engine, monkeypatch, mode, expected, error):
    root = engine.project_root
    feature = "features/login"
    dispatched = []
    documents = {
        "constitution": ".specify/memory/constitution.md",
        "specify": f"{feature}/spec.md",
        "clarify": f"{feature}/spec.md",
        "architecture": ".specify/memory/architecture.md",
        "environment": ".specify/memory/environment.md",
        "plan": f"{feature}/plan.md",
        "taskscode": f"{feature}/tasks-code.md",
        "analyze": f"{feature}/analysis.md",
        "impcode": f"{feature}/code-progress.json",
        "deployment": f"{feature}/deployment.md",
        "test": f"{feature}/test-report.md",
    }

    def progress(*args):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts/python/code_progress.py"), *args],
            cwd=root, capture_output=True, check=False, encoding="utf-8",
            env={**os.environ, "SPECIFY_FEATURE_DIRECTORY": feature},
        )
        assert completed.returncode == 0, completed.stderr
        return json.loads(completed.stdout)

    def dispatch(command, integration, model, args, context, *rest, **kwargs):
        stage = command.removeprefix("speckit.")
        dispatched.append(stage)
        path = documents[stage]
        if stage == "architecture":
            inventory(root, path, components=[{"id": "API"}])
        elif stage == "environment":
            inventory(root, path, assets=[{
                "id": "APP01", "components": ["API"], "os": "Linux",
                "os_version": "24.04", "runtime": "Python 3.11",
                "minimum": {"vcpu": 1, "memory_gib": 1},
                "recommended": {"vcpu": 1, "memory_gib": 1},
            }])
        elif stage == "taskscode":
            write(root, "src/old.py", "obsolete = True")
            inventory(root, path, tasks=[{
                "id": "T001", "title": "Remove obsolete code", "category": "code",
                "requirement_ids": ["FR-001"], "component": "API",
                "deployment_targets": ["APP01"], "depends_on": [],
                "files": ["src/old.py"], "delete_files": ["src/old.py"],
                "done_when": "Remove obsolete module",
            }])
            assert progress("sync")["code_complete"] is False
        elif stage == "analyze" and mode.endswith("analyze-input"):
            path = documents["plan"]
        elif stage == "analyze" and mode == "analyze-neighbor":
            path = "features/other/analysis.md"
            write(root, path, "# Analysis for an unrelated feature")
        elif stage == "impcode":
            if mode == "coding-deleted":
                progress("start", "--task", "T001")
                (root / "src/old.py").unlink()
                outcome = progress("complete", "--task", "T001", "--note", "Removed obsolete module")
                assert outcome["code_complete"] is True
                assert outcome["tests_run"] is False
            else:
                assert progress("status")["code_complete"] is False
        elif stage == "test" and mode.startswith("legacy-"):
            return {"exit_code": 1, "stderr": "Transient test stage failure", "stdout": ""}
        else:
            write(root, path, f"# {stage}")
        if stage == "specify":
            write(root, ".specify/feature.json", json.dumps({"feature_directory": feature}))
        nonce = re.search(r"completion_nonce=([a-f0-9]+)", args)[1]
        return {
            "exit_code": 0, "stderr": "",
            "stdout": "SPECKIT_RESULT " + json.dumps(receipt(nonce, root, [path])),
        }

    monkeypatch.setattr(CommandStep, "_try_dispatch", staticmethod(dispatch))
    definition = WorkflowDefinition.from_yaml(BUNDLED)
    inputs = {
        "spec": "Remove outdated code", "integration": "codex",
        "speckit_review_spec_verdict": "approve", "speckit_review_plan_verdict": "approve",
        "deploy": mode == "coding-pending",
    }
    if mode.startswith("legacy-"):
        definition.data.pop("completion_contract")
        with monkeypatch.context() as legacy_engine:
            legacy_engine.setattr(engine_module, "uses_speckit_contract", lambda _: False)
            run = engine.execute(definition, inputs)
        assert run.current_step_id == "test"
        assert run.step_results["test"]["output"]["stderr"] == "Transient test stage failure"
        dispatched.clear()
        run = engine.resume(run.run_id)
        assert dispatched == []
    else:
        run = engine.execute(definition, inputs)
    if expected is None:
        assert run.status == RunStatus.COMPLETED, run.error
        assert run.step_results["test"]["status"] == "completed"
        assert not (root / "src/old.py").exists()
    else:
        assert run.status == RunStatus.FAILED
        assert run.current_step_id == expected
        assert error in run.error
        assert "deployment" not in dispatched
        assert "test" not in dispatched
