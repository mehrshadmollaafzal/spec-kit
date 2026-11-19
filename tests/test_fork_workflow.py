"""Behavioral evidence for artifact validation, coding resume and shell parity."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
NAMES = {
    "constitution",
    "specify",
    "clarify",
    "architecture",
    "environment",
    "plan",
    "taskscode",
    "analyze",
    "impcode",
    "deployment",
    "test",
}


def inventory(path, value):
    path.write_text(
        "# Design\n\n```json\n" + json.dumps(value) + "\n```\n", encoding="utf-8"
    )


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project [one] café"
    memory = root / ".specify/memory"
    memory.mkdir(parents=True)
    feature = root / "specs/001-feature"
    feature.mkdir(parents=True)
    (root / ".specify/feature.json").write_text(
        '{"feature_directory":"specs/other"}', encoding="utf-8"
    )
    (memory / "constitution.md").write_text(
        "# Principles\nCoding and testing are separate.\n", encoding="utf-8"
    )
    (feature / "spec.md").write_text(
        "# Spec\nFR-001: expose a service\n", encoding="utf-8"
    )
    (feature / "plan.md").write_text(
        "# Plan\nImplement API contracts.\n", encoding="utf-8"
    )
    inventory(
        memory / "architecture.md", {"schema_version": 1, "components": [{"id": "API"}]}
    )
    inventory(
        memory / "environment.md",
        {
            "schema_version": 1,
            "assets": [
                {
                    "id": "APP01",
                    "components": ["API"],
                    "os": "Linux",
                    "os_version": "24.04",
                    "runtime": "Python 3.11",
                    "minimum": {"vcpu": 1, "memory_gib": 1},
                    "recommended": {"vcpu": 2, "memory_gib": 2},
                }
            ],
        },
    )
    task = {
        "id": "T001",
        "title": "Write API service",
        "category": "code",
        "requirement_ids": ["FR-001"],
        "component": "API",
        "deployment_targets": ["APP01"],
        "depends_on": [],
        "files": ["src/api.py"],
        "done_when": "API implementation connected to contract",
    }
    dependent = {
        **copy.deepcopy(task),
        "id": "T002",
        "depends_on": ["T001"],
        "files": ["src/consumer.py"],
    }
    independent = {**copy.deepcopy(task), "id": "T003", "files": ["src/independent.py"]}
    inventory(
        feature / "tasks-code.md",
        {"schema_version": 1, "tasks": [task, dependent, independent]},
    )
    shutil.copytree(ROOT / "templates", root / ".specify/templates")
    shutil.copytree(
        ROOT / "scripts",
        root / ".specify/scripts",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    return root, feature


def invoke(project, helper, *args, shell="python", use_pointer=False):
    root, feature = project
    env = {
        **os.environ,
        "SPECIFY_INIT_DIR": str(root),
        "SPECIFY_FEATURE_DIRECTORY": feature.relative_to(root).as_posix(),
        "SPECKIT_PYTHON_EXECUTABLE": sys.executable,
    }
    if use_pointer:
        for key in ("SPECIFY_FEATURE_DIRECTORY", "SPECIFY_FEATURE"):
            env.pop(key, None)
    if shell == "python":
        cmd = [
            sys.executable,
            str(root / ".specify/scripts/python" / (helper + ".py")),
            *args,
        ]
    elif shell == "powershell":
        ps = shutil.which("powershell.exe")
        if not ps:
            pytest.skip("Windows PowerShell 5.1 unavailable")
        cmd = [
            ps,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(root / ".specify/scripts/powershell/workflow.ps1"),
            "context" if helper == "workflow_context" else "progress",
            *args,
        ]
    else:
        bash = (
            Path("C:/Program Files/Git/bin/bash.exe")
            if os.name == "nt"
            else shutil.which("bash")
        )
        if not bash or not Path(bash).is_file():
            pytest.skip("Bash unavailable")
        cmd = [
            str(bash),
            (root / ".specify/scripts/bash/workflow.sh").as_posix(),
            "context" if helper == "workflow_context" else "progress",
            *args,
        ]
    return subprocess.run(
        cmd,
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )


def progress(project, *args):
    result = invoke(project, "code_progress", *args)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def output(project, name):
    path = project[0] / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Component: API; Deployment assets: APP01; Tasks: T001\nvalue = 1\n",
        encoding="utf-8",
    )


def test_resume_dependency_and_complete_without_touching_tasks(project):
    root, feature = project
    definition = (feature / "tasks-code.md").read_bytes()
    assert progress(project, "sync")["ready"] == ["T001", "T003"]
    assert invoke(project, "code_progress", "start", "--task", "T002").returncode == 1
    progress(project, "start", "--task", "T001")
    # Fresh subprocess resumes the current attempt; no reset or extra attempt.
    assert (
        progress(project, "start", "--task", "T001")["tasks"]["T001"]["attempts"] == 1
    )
    assert (
        invoke(
            project, "code_progress", "complete", "--task", "T001", "--note", "written"
        ).returncode
        == 1
    )
    output(project, "src/api.py")
    assert progress(project, "complete", "--task", "T001", "--note", "implemented API")[
        "ready"
    ] == ["T002", "T003"]
    for key, name in [("T002", "src/consumer.py"), ("T003", "src/independent.py")]:
        progress(project, "start", "--task", key)
        output(project, name)
        result = progress(
            project, "complete", "--task", key, "--note", "implementation connected"
        )
    assert result["code_complete"] is True
    assert result["tests_run"] is False
    assert (feature / "tasks-code.md").read_bytes() == definition
    assert (
        json.loads((root / ".specify/feature.json").read_text())["feature_directory"]
        == "specs/other"
    )


def test_failures_are_bounded_and_independent_tasks_remain_ready(project):
    progress(project, "sync")
    for _ in range(3):
        progress(project, "start", "--task", "T001")
        progress(
            project,
            "block",
            "--task",
            "T001",
            "--note",
            "missing essential contract detail",
        )
    result = invoke(project, "code_progress", "start", "--task", "T001")
    assert result.returncode == 1 and "exhausted" in result.stderr
    assert progress(project, "status")["ready"] == ["T003"]
    assert progress(project, "sync")["tasks"]["T001"]["attempts"] == 3


def test_changed_inputs_require_reconciliation_and_preserve_history(project):
    progress(project, "sync")
    progress(project, "start", "--task", "T001")
    output(project, "src/api.py")
    progress(project, "complete", "--task", "T001", "--note", "written")
    (project[1] / "plan.md").write_text("# Revised approved design", encoding="utf-8")
    assert invoke(project, "code_progress", "status").returncode == 1
    assert progress(project, "sync")["tasks"]["T001"]["status"] == "NEEDS_REVIEW"
    assert (
        json.loads((project[1] / "code-progress.json").read_text())["history"][0][
            "tasks"
        ]["T001"]["status"]
        == "CODE_COMPLETE"
    )
    assert (project[0] / "src/api.py").is_file()


def test_external_source_change_requires_review_without_status_writes(project):
    progress(project, "sync")
    progress(project, "start", "--task", "T001")
    output(project, "src/api.py")
    progress(project, "complete", "--task", "T001", "--note", "written")
    before = (project[1] / "code-progress.json").read_bytes()
    (project[0] / "src/api.py").write_text(
        "# user changes\nvalue = 2\n", encoding="utf-8"
    )
    assert progress(project, "status")["tasks"]["T001"]["status"] == "NEEDS_REVIEW"
    assert (project[1] / "code-progress.json").read_bytes() == before


def test_schema_one_windows_input_keys_preserve_completion_and_detect_changes(project):
    progress(project, "sync")
    progress(project, "start", "--task", "T001")
    output(project, "src/api.py")
    completed = progress(project, "complete", "--task", "T001", "--note", "written")
    ledger = project[1] / "code-progress.json"
    old = json.loads(ledger.read_bytes())
    portable_inputs = {
        key.replace("\\", "/"): value for key, value in old["inputs"].items()
    }
    assert old["inputs"] == portable_inputs
    old["inputs"] = {
        key.replace("/", "\\"): value for key, value in portable_inputs.items()
    }
    ledger.write_text(json.dumps(old), encoding="utf-8")
    before = ledger.read_bytes()

    assert progress(project, "status") == completed
    assert ledger.read_bytes() == before
    assert progress(project, "sync") == completed
    synced = json.loads(ledger.read_bytes())
    assert synced["inputs"] == portable_inputs
    assert synced["history"] == old["history"]

    (project[1] / "plan.md").write_text("# Changed design", encoding="utf-8")
    result = invoke(project, "code_progress", "status")
    assert (
        result.returncode == 1 and "Design or task definitions changed" in result.stderr
    )
    assert progress(project, "sync")["tasks"]["T001"]["status"] == "NEEDS_REVIEW"


def test_schema_one_rejects_ambiguous_input_key_aliases(project):
    progress(project, "sync")
    ledger = project[1] / "code-progress.json"
    state = json.loads(ledger.read_bytes())
    key, value = next(iter(state["inputs"].items()))
    state["inputs"].update(
        {key.replace("\\", "/"): value, key.replace("/", "\\"): value}
    )
    ledger.write_text(json.dumps(state), encoding="utf-8")
    before = ledger.read_bytes()

    for action in ("status", "sync"):
        result = invoke(project, "code_progress", action)
        assert (
            result.returncode == 1 and "Ambiguous progress input paths" in result.stderr
        )
        assert ledger.read_bytes() == before


def test_completed_source_reviews_get_fresh_attempts_and_preserve_prior_evidence(project):
    progress(project, "sync")
    for _ in range(2):
        progress(project, "start", "--task", "T001")
        progress(project, "block", "--task", "T001", "--note", "prior obstacle")
    progress(project, "start", "--task", "T001")
    output(project, "src/api.py")
    completed = progress(project, "complete", "--task", "T001", "--note", "written")
    assert completed["tasks"]["T001"]["attempts"] == 3
    prior_reviews = [completed["tasks"]["T001"]]
    source = project[0] / "src/api.py"

    for revision in range(2, 6):
        source.write_text(f"value = {revision}\n", encoding="utf-8")
        # Exercise both a stored NEEDS_REVIEW and a read-only invalidation.
        status = progress(project, "sync" if revision == 2 else "status")
        assert status["tasks"]["T001"]["status"] == "NEEDS_REVIEW"
        assert status["ready"] == ["T001", "T003"]
        started = progress(project, "start", "--task", "T001")
        assert started["tasks"]["T001"]["attempts"] == 1
        completed = progress(
            project, "complete", "--task", "T001", "--note", f"reviewed revision {revision}"
        )
        assert completed["ready"] == ["T002", "T003"]
        prior_reviews.append(completed["tasks"]["T001"])

    source.write_text("value = 6\n", encoding="utf-8")
    for attempt in range(1, 4):
        started = progress(project, "start", "--task", "T001")
        assert started["tasks"]["T001"]["attempts"] == attempt
        progress(project, "block", "--task", "T001", "--note", "review obstacle")
    source.write_text("value = 7\n", encoding="utf-8")
    assert progress(project, "sync")["ready"] == ["T003"]
    result = invoke(project, "code_progress", "start", "--task", "T001")
    assert result.returncode == 1 and "exhausted" in result.stderr
    state = json.loads((project[1] / "code-progress.json").read_bytes())
    for review in prior_reviews:
        assert any(item["tasks"].get("T001") == review for item in state["history"])


def test_task_regeneration_preserves_work_and_rejects_retired_id_reuse(project):
    progress(project, "sync")
    path = project[1] / "tasks-code.md"
    data = json.loads(path.read_text().split("```json\n")[1].split("```")[0])
    removed = data["tasks"].pop()
    inventory(path, data)
    progress(project, "sync")
    before = (project[1] / "code-progress.json").read_bytes()
    data["tasks"].append(removed)
    inventory(path, data)
    result = invoke(project, "code_progress", "sync")
    assert result.returncode == 1 and "Retired task IDs" in result.stderr
    assert (project[1] / "code-progress.json").read_bytes() == before


def test_shared_file_tasks_cannot_start_concurrently(project):
    path = project[1] / "tasks-code.md"
    data = json.loads(path.read_text().split("```json\n")[1].split("```")[0])
    data["tasks"][2]["files"] = ["src/api.py"]
    inventory(path, data)
    progress(project, "sync")
    progress(project, "start", "--task", "T001")
    result = invoke(project, "code_progress", "start", "--task", "T003")
    assert result.returncode == 1 and "shares files" in result.stderr


@pytest.mark.parametrize("external_change", [False, True])
@pytest.mark.parametrize("blocked_retry", [False, True])
def test_shared_dependency_edits_resume_but_external_changes_block(
    project, external_change, blocked_retry
):
    path = project[1] / "tasks-code.md"
    data = json.loads(path.read_text().split("```json\n")[1].split("```")[0])
    data["tasks"][0]["files"].append("src/model.py")
    data["tasks"][1]["files"] = ["src/api.py"]
    inventory(path, data)
    progress(project, "sync")
    progress(project, "start", "--task", "T001")
    output(project, "src/api.py")
    output(project, "src/model.py")
    progress(project, "complete", "--task", "T001", "--note", "API implemented")
    progress(project, "start", "--task", "T002")
    (project[0] / "src/api.py").write_text(
        "# Integrated API\nvalue = 2\n", encoding="utf-8"
    )
    if blocked_retry:
        progress(
            project, "block", "--task", "T002", "--note", "integration needs correction"
        )
        assert "T002" in progress(project, "status")["ready"]
        progress(project, "start", "--task", "T002")
    if external_change:
        (project[0] / "src/model.py").write_text(
            "# User changed model\nvalue = 3\n", encoding="utf-8"
        )
        result = invoke(
            project,
            "code_progress",
            "complete",
            "--task",
            "T002",
            "--note",
            "integrated",
        )
        assert result.returncode == 1 and "prerequisite changed" in result.stderr
        assert progress(project, "status")["tasks"]["T001"]["status"] == "NEEDS_REVIEW"
    else:
        assert "T002" in progress(project, "status")["ready"]
        assert "T001" not in progress(project, "status")["ready"]
        assert progress(project, "start", "--task", "T002")["tasks"]["T002"][
            "attempts"
        ] == (2 if blocked_retry else 1)
        result = progress(project, "complete", "--task", "T002", "--note", "integrated")
        assert result["tasks"]["T001"]["status"] == "CODE_COMPLETE"
        assert result["tasks"]["T002"]["status"] == "CODE_COMPLETE"


@pytest.mark.parametrize(
    "problem",
    [
        "cycle",
        "unknown_dependency",
        "unknown_target",
        "test_file",
        "escape",
        "bad_category",
        "duplicate",
        "missing_done",
        "non_normalized",
        "wildcard",
    ],
)
def test_invalid_tasks_are_rejected_without_state_mutation(project, problem):
    progress(project, "sync")
    path = project[1] / "tasks-code.md"
    data = json.loads(path.read_text().split("```json\n")[1].split("```")[0])
    first = data["tasks"][0]
    if problem == "cycle":
        first["depends_on"] = ["T002"]
    if problem == "unknown_dependency":
        first["depends_on"] = ["T999"]
    if problem == "unknown_target":
        first["deployment_targets"] = ["GHOST"]
    if problem == "test_file":
        first["files"] = ["src/api.test.ts"]
    if problem == "non_normalized":
        first["files"] = ["src/./api.py"]
    if problem == "wildcard":
        first["files"] = ["src/*.py"]
    if problem == "escape":
        first["files"] = ["../outside.py"]
    if problem == "bad_category":
        first["category"] = "deployment"
    if problem == "duplicate":
        data["tasks"].append(first.copy())
    if problem == "missing_done":
        first.pop("done_when")
    inventory(path, data)
    before = (project[1] / "code-progress.json").read_bytes()
    result = invoke(project, "code_progress", "sync")
    assert result.returncode == 1 and "ERROR" in result.stderr
    assert (project[1] / "code-progress.json").read_bytes() == before
    # Analyze still receives paths so it can report invalid task inventories.
    assert invoke(project, "workflow_context", "analyze").returncode == 0


@pytest.mark.parametrize(
    ("shell", "encoding"),
    [("python", "utf-8"), ("python", "utf-8-sig"),
     ("powershell", "utf-8"), ("powershell", "utf-8-sig")],
)
def test_context_resolves_persisted_feature_with_or_without_bom(project, shell, encoding):
    root, feature = project
    pointer = root / ".specify/feature.json"
    selection = json.dumps({"feature_directory": feature.relative_to(root).as_posix()})
    if shell == "powershell" and encoding == "utf-8-sig":
        powershell = shutil.which("powershell.exe") if os.name == "nt" else None
        if not powershell:
            pytest.skip("Native Windows PowerShell 5.1 unavailable")
        written = subprocess.run(
            [powershell, "-NoProfile", "-Command",
             "if ($PSVersionTable.PSVersion.ToString() -notlike '5.1.*') { exit 2 }; "
             "$env:SPECKIT_TEST_FEATURE_JSON | Set-Content -LiteralPath "
             "$env:SPECKIT_TEST_FEATURE_POINTER -Encoding UTF8"],
            cwd=root, env={
                **os.environ, "SPECKIT_TEST_FEATURE_JSON": selection,
                "SPECKIT_TEST_FEATURE_POINTER": str(pointer),
            },
            capture_output=True, check=False,
        )
        assert written.returncode == 0, written.stderr
    else:
        pointer.write_text(selection, encoding=encoding)
    before = pointer.read_bytes()
    assert before.startswith(bytes.fromhex("EF BB BF")) == (encoding == "utf-8-sig")

    result = invoke(project, "workflow_context", "architecture", "--json",
                    shell=shell, use_pointer=True)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["FEATURE_DIR"] == str(feature)
    assert pointer.read_bytes() == before


@pytest.mark.parametrize("shell", ["python", "powershell", "bash"])
def test_context_and_progress_shell_parity_and_missing_inputs(project, shell):
    root, feature = project
    before = {
        str(p.relative_to(root)): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }
    result = invoke(project, "workflow_context", "plan", "--json", shell=shell)
    assert result.returncode == 0, result.stderr
    parsed = json.loads(result.stdout)
    assert parsed["PLAN"] == str(feature / "plan.md")
    assert "Implementation plan" in parsed["TEMPLATE_CONTENT"]
    after = {
        str(p.relative_to(root)): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }
    assert after == before
    assert invoke(project, "code_progress", "sync", shell=shell).returncode == 0
    assert (
        invoke(
            project, "code_progress", "start", "--task", "T002", shell=shell
        ).returncode
        == 1
    )
    (root / ".specify/memory/environment.md").unlink()
    result = invoke(project, "workflow_context", "plan", shell=shell)
    assert result.returncode == 1 and "ENVIRONMENT" in result.stderr


def test_invalid_resources_and_unmapped_components(project):
    path = project[0] / ".specify/memory/environment.md"
    inventory(
        path,
        {
            "schema_version": 1,
            "assets": [
                {
                    "id": "APP01",
                    "components": ["API"],
                    "os": "Linux",
                    "os_version": "24.04",
                    "runtime": "Python",
                    "minimum": {"vcpu": 4},
                    "recommended": {"vcpu": 2},
                }
            ],
        },
    )
    assert invoke(project, "workflow_context", "plan").returncode == 1


def test_corrupt_progress_and_lock_are_preserved(project):
    path = project[1] / "code-progress.json"
    path.write_text("{broken", encoding="utf-8")
    assert invoke(project, "code_progress", "sync").returncode == 1
    assert path.read_text() == "{broken"
    path.unlink()
    lock = path.with_suffix(".lock")
    lock.write_text("active writer", encoding="utf-8")
    assert invoke(project, "code_progress", "sync").returncode == 1
    assert not path.exists() and lock.read_text() == "active writer"


@pytest.mark.parametrize("shell", ["python", "powershell", "bash"])
def test_github_task_resolution_prefers_coding_tasks_with_legacy_fallback(
    project, shell
):
    root, feature = project
    env = {
        **os.environ,
        "SPECIFY_INIT_DIR": str(root),
        "SPECIFY_FEATURE_DIRECTORY": "specs/001-feature",
    }
    if shell == "python":
        cmd = [
            sys.executable,
            str(ROOT / "extensions/github/scripts/python/resolve_tasks.py"),
            "--json",
        ]
    elif shell == "powershell":
        executable = shutil.which("powershell.exe")
        if not executable:
            pytest.skip("Windows PowerShell 5.1 unavailable")
        cmd = [
            executable,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "extensions/github/scripts/powershell/resolve-tasks.ps1"),
            "-Json",
        ]
    else:
        executable = (
            Path("C:/Program Files/Git/bin/bash.exe")
            if os.name == "nt"
            else shutil.which("bash")
        )
        if not executable or not Path(executable).is_file():
            pytest.skip("Bash unavailable")
        cmd = [
            str(executable),
            (ROOT / "extensions/github/scripts/bash/resolve-tasks.sh").as_posix(),
            "--json",
        ]
    legacy = feature / "tasks.md"
    legacy.write_text("- [ ] T001 Legacy coding task\n", encoding="utf-8")
    for expected in ["tasks-code.md", "tasks.md"]:
        result = subprocess.run(cmd, cwd=root, env=env, capture_output=True, timeout=30)
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert Path(data["TASKS"]).name == expected
        assert expected in data["AVAILABLE_DOCS"]
        (feature / expected).unlink()
    result = subprocess.run(cmd, cwd=root, env=env, capture_output=True, timeout=30)
    assert result.returncode == 1


def test_exact_inventory_and_generated_codex_skill_contracts(tmp_path):
    from specify_cli.integrations.codex import CodexIntegration
    from specify_cli.integrations.manifest import IntegrationManifest
    from specify_cli.shared_infra import install_shared_infra
    from rich.console import Console

    assert {p.stem for p in (ROOT / "templates/commands").glob("*.md")} == NAMES
    install_shared_infra(
        tmp_path,
        "ps",
        version="test",
        core_pack=None,
        repo_root=ROOT,
        console=Console(),
    )
    CodexIntegration().setup(
        tmp_path, IntegrationManifest("codex", tmp_path), script_type="ps"
    )
    generated = tmp_path / ".agents/skills"
    assert {p.name.removeprefix("speckit-") for p in generated.iterdir()} == NAMES
    assert (tmp_path / ".specify/scripts/python/code_progress.py").is_file()
    assert (tmp_path / ".specify/templates/tasks-code-template.md").is_file()
    for name in NAMES:
        text = (generated / ("speckit-" + name) / "SKILL.md").read_text(
            encoding="utf-8"
        )
        assert "{SCRIPT}" not in text and "__SPECKIT_COMMAND_" not in text
    text = (generated / "speckit-impcode/SKILL.md").read_text(encoding="utf-8")
    assert "$speckit-taskscode" in text and "CODE_COMPLETE" in text
    assert "do not run unit, integration, end-to-end" in text


@pytest.mark.parametrize("customized", [False, True])
def test_upgrade_retires_managed_old_skills_and_preserves_customizations(
    tmp_path, monkeypatch, customized
):
    from typer.testing import CliRunner
    from specify_cli import app
    from specify_cli.integrations.manifest import IntegrationManifest

    root = tmp_path / "upgrade"
    result = CliRunner().invoke(
        app,
        [
            "init",
            str(root),
            "--integration",
            "codex",
            "--script",
            "ps",
            "--ignore-agent-tools",
        ],
    )
    assert result.exit_code == 0, result.output
    manifest = IntegrationManifest.load("codex", root)
    retired = ".agents/skills/speckit-tasks/SKILL.md"
    manifest.record_file(retired, "# Old managed task generator\n")
    manifest.save()
    if customized:
        (root / retired).write_text("# User customized skill\n", encoding="utf-8")
    monkeypatch.setenv("SPECIFY_INIT_DIR", str(root))
    result = CliRunner().invoke(app, ["integration", "upgrade", "codex"])
    if customized:
        assert result.exit_code != 0
        assert (root / retired).read_text() == "# User customized skill\n"
    else:
        assert result.exit_code == 0, result.output
        assert not (root / retired).exists()
        assert (root / ".agents/skills/speckit-taskscode/SKILL.md").is_file()


def task_inventory(project):
    path = project[1] / "tasks-code.md"
    return path, json.loads(path.read_text().split("```json\n")[1].split("```")[0])


@pytest.mark.parametrize("revision", ["definition", "source"])
def test_durable_dependent_review(project, revision):
    path, data = task_inventory(project)
    data["tasks"].append(
        {
            **data["tasks"][1],
            "id": "T004",
            "depends_on": ["T002"],
            "files": ["src/client.py"],
        }
    )
    inventory(path, data)
    progress(project, "sync")
    for task in data["tasks"]:
        progress(project, "start", "--task", task["id"])
        output(project, task["files"][0])
        complete = progress(
            project, "complete", "--task", task["id"], "--note", "implemented"
        )
    independent = complete["tasks"]["T003"]
    if revision == "definition":
        data["tasks"][0]["done_when"] = "API emits display_name"
        inventory(path, data)
        progress(project, "sync")
    else:
        (project[0] / "src/api.py").write_text("reply = {'display_name': 'Alice'}")
    for key, descendants in [
        ("T001", ["T002", "T004"]),
        ("T002", ["T004"]),
        ("T004", []),
    ]:
        progress(project, "start", "--task", key)
        progress(project, "sync")
        result = progress(
            project,
            "complete",
            "--task",
            key,
            "--note",
            "reviewed against the revised contract",
        )
        assert result["tasks"]["T003"] == independent
        assert result["code_complete"] == (not descendants)
        assert all(
            result["tasks"][child]["status"] == "NEEDS_REVIEW" for child in descendants
        )
        state = project[1] / "code-progress.json"
        before = state.read_bytes()
        assert progress(project, "status") == result
        assert state.read_bytes() == before


@pytest.mark.parametrize("rename", [False, True])
def test_explicit_deletion_reconciles_completed_owner(project, rename):
    path, data = task_inventory(project)
    old, new = "src/api.py", "src/replacement.py"
    data["tasks"] = data["tasks"][:2]
    task = data["tasks"][1]
    task.update(files=[old, new] if rename else [old], delete_files=[old])
    inventory(path, data)
    progress(project, "sync")
    progress(project, "start", "--task", "T001")
    output(project, old)
    original = progress(project, "complete", "--task", "T001", "--note", "created")
    progress(project, "start", "--task", "T002")
    args = ("complete", "--task", "T002", "--note", "removed obsolete module")
    if rename:
        output(project, new)
    assert invoke(project, "code_progress", *args).returncode == 1
    (project[0] / old).unlink()
    (project[0] / old).mkdir()
    assert invoke(project, "code_progress", *args).returncode == 1
    (project[0] / old).rmdir()
    if rename:
        (project[0] / new).unlink()
        assert invoke(project, "code_progress", *args).returncode == 1
        output(project, new)
    progress(project, "sync")
    assert progress(project, *args)["code_complete"]
    status = progress(project, "status")
    assert status["code_complete"]
    assert (
        status["tasks"]["T001"]["file_hashes"]
        == original["tasks"]["T001"]["file_hashes"]
    )
    assert status["tasks"]["T002"]["file_hashes"][old] == "absent"
    if rename:
        (project[0] / new).write_text("changed")
        assert not progress(project, "status")["code_complete"]
        (project[0] / new).unlink()
        assert not progress(project, "status")["code_complete"]
        output(project, new)
    output(project, old)
    assert progress(project, "status")["tasks"]["T002"]["status"] == "NEEDS_REVIEW"
    progress(project, "start", "--task", "T002")
    (project[0] / old).unlink()
    assert progress(project, *args)["code_complete"]


def test_delete_records_absence(project):
    path, data = task_inventory(project)
    first = data["tasks"][0]
    first["delete_files"] = first["files"]
    inventory(path, data)
    output(project, "src/api.py")
    progress(project, "sync")
    progress(project, "start", "--task", "T001")
    (project[0] / "src/api.py").unlink()
    progress(project, "complete", "--task", "T001", "--note", "retired")
    assert progress(project, "status")["tasks"]["T001"]["file_hashes"] == {
        "src/api.py": "absent"
    }


@pytest.mark.parametrize(
    "bad",
    [
        "../legacy",
        "/absolute",
        "C:/escape",
        ".specify/memory/a",
        "specs/001-feature/plan.md",
        "specs/001-feature/contracts/api.json",
        "tests/unit.py",
        "src/./api.py",
    ],
)
def test_deletion_endpoints_obey_source_policy(project, bad):
    path, data = task_inventory(project)
    data["tasks"][0].update(files=[bad, "src/new.py"], delete_files=[bad])
    inventory(path, data)
    assert invoke(project, "code_progress", "validate").returncode == 1


@pytest.fixture
def custom_feature(project):
    root, standard = project
    feature = root / "features/login"
    feature.parent.mkdir()
    standard.rename(feature)
    return root, feature


@pytest.mark.parametrize(
    "artifact,operation",
    [
        ("plan.md", "output"),
        ("spec.md", "rename-source"),
        ("analysis.md", "rename-destination"),
        ("contracts/api/schema.json", "delete"),
        ("checklists/requirements.md", "output"),
        ("code-progress.json", "output"),
        ("code-progress.lock", "delete"),
        pytest.param(
            "analysis.md.", "rename-destination", id="windows-trailing-dot",
            marks=pytest.mark.skipif(os.name != "nt", reason="Windows path alias"),
        ),
        pytest.param(
            "contracts /api/schema.json", "delete", id="windows-trailing-space",
            marks=pytest.mark.skipif(os.name != "nt", reason="Windows path alias"),
        ),
    ],
)
def test_custom_feature_artifacts_cannot_be_coding_endpoints(custom_feature, artifact, operation):
    root, feature = custom_feature
    path, data = task_inventory(custom_feature)
    endpoint = (feature / artifact).relative_to(root).as_posix()
    task = data["tasks"][0]
    if operation == "rename-destination":
        task.update(files=["src/api.py", endpoint], delete_files=["src/api.py"])
    elif operation == "rename-source":
        task.update(files=[endpoint, "src/api.py"], delete_files=[endpoint])
    elif operation == "delete":
        task.update(files=[endpoint], delete_files=[endpoint])
    else:
        task.update(files=[endpoint])
    inventory(path, data)
    for action in ("validate", "sync"):
        result = invoke(custom_feature, "code_progress", action)
        assert result.returncode == 1 and endpoint in result.stderr
    assert not (feature / "code-progress.json").exists()
    assert not (feature / "code-progress.lock").exists()


@pytest.mark.parametrize("shell", ["python", "powershell", "bash"])
def test_custom_layout_allows_source_beside_feature_artifacts(custom_feature, shell):
    root, feature = custom_feature
    path, data = task_inventory(custom_feature)
    source = (feature / "src/api.py").relative_to(root).as_posix()
    task = data["tasks"][0]
    task["files"] = [source]
    data["tasks"] = [task]
    inventory(path, data)
    result = invoke(custom_feature, "code_progress", "sync", shell=shell)
    assert result.returncode == 0, result.stderr
    progress(custom_feature, "start", "--task", "T001")
    output(custom_feature, source)
    result = invoke(
        custom_feature, "code_progress", "complete", "--task", "T001", "--note", "Implemented API", shell=shell
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["code_complete"] is True


def test_deletion_requires_owned_path_and_serializes_both_endpoints(project):
    path, data = task_inventory(project)
    task = data["tasks"][2]
    task.update(files=["src/new.py"], delete_files=["src/api.py"])
    inventory(path, data)
    assert invoke(project, "code_progress", "validate").returncode == 1
    task["files"].append("src/api.py")
    data["tasks"][1].update(depends_on=[], files=["src/new.py"])
    inventory(path, data)
    progress(project, "sync")
    progress(project, "start", "--task", "T003")
    for key in ("T001", "T002"):
        failed = invoke(project, "code_progress", "start", "--task", key)
        assert failed.returncode == 1 and "shares files" in failed.stderr


def test_dangling_link_is_not_a_deletion(project):
    path, data = task_inventory(project)
    data["tasks"][0]["delete_files"] = ["src/api.py"]
    inventory(path, data)
    progress(project, "sync")
    progress(project, "start", "--task", "T001")
    link = project[0] / "src/api.py"
    link.parent.mkdir()
    try:
        link.symlink_to(project[0] / "missing")
    except OSError as exc:
        pytest.skip(f"Cannot create symlink: {exc}")
    failed = invoke(
        project, "code_progress", "complete", "--task", "T001", "--note", "removed"
    )
    assert failed.returncode == 1 and "Symlinked" in failed.stderr


def test_approved_shared_revision_requires_review_of_other_consumer(project):
    path, data = task_inventory(project)
    data["tasks"][2].update(depends_on=["T001"], files=["src/api.py"])
    inventory(path, data)
    progress(project, "sync")
    for task in data["tasks"][:2]:
        progress(project, "start", "--task", task["id"])
        output(project, task["files"][0])
        progress(project, "complete", "--task", task["id"], "--note", "implemented")
    progress(project, "start", "--task", "T003")
    (project[0] / "src/api.py").write_text("reply = {'display_name': 'Alice'}")
    result = progress(
        project, "complete", "--task", "T003", "--note", "integrated producer"
    )
    assert (
        result["tasks"]["T001"]["status"]
        == result["tasks"]["T003"]["status"]
        == "CODE_COMPLETE"
    )
    assert result["tasks"]["T002"]["status"] == "NEEDS_REVIEW"


def test_schema_one_interrupted_creation_then_new_deletion(project):
    path, data = task_inventory(project)
    producer, cleanup = data["tasks"][:2]
    data["tasks"] = [producer]
    inventory(path, data)
    original = progress(project, "sync")
    ledger = project[1] / "code-progress.json"
    old = json.loads(ledger.read_bytes())
    # Schema-1 start checkpoint before the fork understood absence evidence.
    old["tasks"]["T001"].update(
        status="IN_PROGRESS", attempts=1, starting_hashes={"src/api.py": "missing"}
    )
    ledger.write_text(json.dumps(old))
    assert (
        progress(project, "start", "--task", "T001")["tasks"]["T001"]["attempts"] == 1
    )
    output(project, "src/api.py")
    done = progress(project, "complete", "--task", "T001", "--note", "original output")
    assert done["code_complete"]
    assert (
        done["tasks"]["T001"]["definition_hash"]
        == original["tasks"]["T001"]["definition_hash"]
    )
    cleanup.update(files=["src/api.py"], delete_files=["src/api.py"])
    data["tasks"].append(cleanup)
    inventory(path, data)
    progress(project, "sync")
    progress(project, "start", "--task", "T002")
    (project[0] / "src/api.py").unlink()
    progress(project, "complete", "--task", "T002", "--note", "superseded")
    producer["title"] = "Review revised producer contract"
    inventory(path, data)
    progress(project, "sync")
    for key in ("T001", "T002"):
        progress(project, "start", "--task", key)
        result = progress(project, "complete", "--task", key, "--note", "reviewed")
    assert result["code_complete"]
    assert (
        result["tasks"]["T001"]["file_hashes"] == done["tasks"]["T001"]["file_hashes"]
    )
    assert not (project[0] / "src/api.py").exists()
    assert json.loads(ledger.read_bytes())["history"][0]["tasks"] == done["tasks"]


def test_deletion_cannot_supersede_preexisting_unreviewed_edit(project):
    path, data = task_inventory(project)
    data["tasks"][2].update(files=["src/api.py"], delete_files=["src/api.py"])
    inventory(path, data)
    progress(project, "sync")
    progress(project, "start", "--task", "T001")
    output(project, "src/api.py")
    progress(project, "complete", "--task", "T001", "--note", "created")
    (project[0] / "src/api.py").write_text("unreviewed")
    progress(project, "start", "--task", "T003")
    (project[0] / "src/api.py").unlink()
    result = invoke(
        project, "code_progress", "complete", "--task", "T003", "--note", "removed"
    )
    assert result.returncode == 1 and "Prior evidence" in result.stderr


@pytest.mark.skipif(os.name != "nt", reason="Windows directory junction")
def test_deletion_rejects_junction_alias_of_protected_path(project):
    root, _ = project
    alias = root / "app-config"
    import _winapi

    _winapi.CreateJunction(str(root / ".specify"), str(alias))
    try:
        path, data = task_inventory(project)
        endpoint = "app-config/feature.json"
        data["tasks"][0].update(files=[endpoint], delete_files=[endpoint])
        inventory(path, data)
        assert invoke(project, "code_progress", "validate").returncode == 1
    finally:
        alias.rmdir()


def test_rename_over_previous_destination_retains_both_revisions(project):
    path, data = task_inventory(project)
    source, destination = "src/api.py", "src/consumer.py"
    inventory(path, data)
    progress(project, "sync")
    for key, name in (("T001", source), ("T002", destination)):
        progress(project, "start", "--task", key)
        output(project, name)
        (project[0] / name).write_text(f"module = '{key}'")
        prior = progress(project, "complete", "--task", key, "--note", "implemented")
    data["tasks"][2].update(
        files=[source, destination], delete_files=[source], depends_on=["T002"]
    )
    inventory(path, data)
    progress(project, "sync")
    progress(project, "start", "--task", "T003")
    (project[0] / source).replace(project[0] / destination)
    result = progress(
        project,
        "complete",
        "--task",
        "T003",
        "--note",
        "renamed and reviewed both owners",
    )
    assert result["code_complete"]
    ledger = json.loads((project[1] / "code-progress.json").read_bytes())
    assert any(
        revision["tasks"]["T002"]["file_hashes"]
        == prior["tasks"]["T002"]["file_hashes"]
        and revision["tasks"]["T003"]["status"] == "IN_PROGRESS"
        for revision in ledger["history"]
    )
