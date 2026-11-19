"""Run snapshots and checkpoints have a single owner across invocations."""

import json
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml

from specify_cli.workflows.base import RunStatus
from specify_cli.workflows.engine import RunState, WorkflowDefinition, WorkflowEngine


def _workflow(workflow_id):
    return WorkflowDefinition({
        "workflow": {"id": workflow_id, "name": workflow_id},
        "inputs": {"verdict": {"type": "string", "default": ""}},
        "steps": [
            {
                "id": "review",
                "type": "gate",
                "message": "Review",
                "verdict_input": "verdict",
            },
            {"id": "write", "type": "shell", "run": "echo once>>effects.txt"},
        ],
    })


def _snapshot(directory):
    return {path.name: path.read_bytes() for path in directory.iterdir()}


def _cli(project, *args):
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-c", "from specify_cli import app; app()", *args],
        cwd=project,
        input="",
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )


def test_reused_run_id_preserves_original_cli_run(tmp_path, monkeypatch):
    monkeypatch.setenv("SPECKIT_WORKFLOW_RUN_ID", "nightly-review")
    original = tmp_path / "alpha.yml"
    next_run = tmp_path / "beta.yml"
    for source in (original, next_run):
        source.write_text(yaml.safe_dump(_workflow(source.stem).data), encoding="utf-8")
    result = _cli(tmp_path, "workflow", "run", str(original), "--json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["run_id"] == "nightly-review"
    assert payload["status"] == "paused"
    state = RunState.load(payload["run_id"], tmp_path)
    before = _snapshot(state.runs_dir)

    result = _cli(tmp_path, "workflow", "run", str(next_run), "--json")

    assert _snapshot(state.runs_dir) == before
    assert result.returncode == 1
    assert "nightly-review" in result.stderr and "already exists" in result.stderr
    definition = _cli(tmp_path, "workflow", "definition", state.run_id, "--json")
    assert definition.returncode == 0, definition.stderr
    assert json.loads(definition.stdout)["definition"]["workflow"]["id"] == "alpha"


def test_simultaneous_reservations_have_one_winner(tmp_path, monkeypatch):
    destination = tmp_path / ".specify" / "workflows" / "runs" / "shared"
    destination.parent.mkdir(parents=True)
    arriving = threading.Barrier(2, timeout=10)
    reservation = threading.local()
    original_mkdir = Path.mkdir

    def mkdir(path, *args, **kwargs):
        if path == destination and not getattr(reservation, "attempted", False):
            reservation.attempted = True
            arriving.wait()
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mkdir)

    def reserve(workflow_id):
        try:
            return WorkflowEngine(tmp_path).execute(_workflow(workflow_id), run_id="shared")
        except ValueError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(reserve, ("alpha", "beta")))

    winners = [outcome for outcome in outcomes if isinstance(outcome, RunState)]
    conflicts = [outcome for outcome in outcomes if isinstance(outcome, ValueError)]
    assert len(winners) == len(conflicts) == 1
    assert str(conflicts[0]) == "Workflow run 'shared' already exists."
    persisted = RunState.load("shared", tmp_path)
    assert persisted.workflow_id == persisted.load_definition().id == winners[0].workflow_id
    assert persisted.status == RunStatus.PAUSED


def test_generated_run_id_retries_an_occupied_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("SPECKIT_WORKFLOW_RUN_ID", raising=False)
    engine = WorkflowEngine(tmp_path)
    first = engine.execute(_workflow("alpha"), run_id="11111111")
    before = _snapshot(first.runs_dir)
    generated = iter(("11111111-0000", "22222222-0000"))
    monkeypatch.setattr("specify_cli.workflows.engine.uuid.uuid4", lambda: next(generated))

    second = engine.execute(_workflow("beta"))

    assert second.run_id == "22222222"
    assert second.status == RunStatus.PAUSED
    assert _snapshot(first.runs_dir) == before


def test_invalid_input_does_not_reserve_an_explicit_run_id(tmp_path):
    engine = WorkflowEngine(tmp_path)
    workflow = _workflow("alpha")
    workflow.inputs["verdict"] = {"type": "string", "required": True}
    with pytest.raises(ValueError, match="Required input 'verdict' not provided"):
        engine.execute(workflow, run_id="review-run")
    assert not (tmp_path / ".specify/workflows/runs/review-run").exists()

    resumed = engine.execute(workflow, {"verdict": "approve"}, run_id="review-run")
    assert resumed.status == RunStatus.COMPLETED


_BLOCK_RESUME_AFTER_LOADING_STATE = """
from pathlib import Path
import time

from specify_cli import app
from specify_cli.workflows.engine import RunState

load_definition = RunState.load_definition

def wait_for_release(self):
    definition = load_definition(self)
    Path("resume-ready").touch()
    deadline = time.monotonic() + 30
    while not Path("resume-release").exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("The test did not release the resume")
        time.sleep(0.02)
    return definition

RunState.load_definition = wait_for_release
app()
"""


@pytest.mark.parametrize("legacy", [False, True])
def test_concurrent_processes_resume_only_one_side_effect(tmp_path, monkeypatch, legacy):
    monkeypatch.setenv("SPECKIT_WORKFLOW_RUN_ID", "review-run")
    source = tmp_path / "alpha.yml"
    source.write_text(yaml.safe_dump(_workflow("alpha").data), encoding="utf-8")
    started = _cli(tmp_path, "workflow", "run", str(source), "--json")
    assert started.returncode == 0, started.stderr
    assert json.loads(started.stdout)["status"] == "paused"
    if legacy:
        state_path = RunState.load("review-run", tmp_path).runs_dir / "state.json"
        stored = json.loads(state_path.read_text(encoding="utf-8"))
        del stored["installed_workflow_id"]
        del stored["installed_registry_root"]
        state_path.write_text(json.dumps(stored), encoding="utf-8")

    args = ["workflow", "resume", "review-run", "--input", "verdict=approve", "--json"]
    ready = tmp_path / "resume-ready"
    with subprocess.Popen(
        [sys.executable, "-X", "utf8", "-c", _BLOCK_RESUME_AFTER_LOADING_STATE, *args],
        cwd=tmp_path,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    ) as owner:
        try:
            deadline = time.monotonic() + 20
            while not ready.exists():
                assert owner.poll() is None, owner.communicate()
                assert time.monotonic() < deadline, "The first resume did not reach the barrier"
                time.sleep(0.02)
            competing = _cli(tmp_path, *args)
        finally:
            (tmp_path / "resume-release").touch()
        stdout, stderr = owner.communicate(timeout=20)

    assert (tmp_path / "effects.txt").read_text().splitlines() == ["once"]
    assert owner.returncode == 0, stderr
    assert json.loads(stdout)["status"] == "completed"
    assert competing.returncode == 1
    assert "review-run" in competing.stderr and "already being executed" in competing.stderr
    state = RunState.load("review-run", tmp_path)
    assert state.status == RunStatus.COMPLETED
    assert state.installed_origin_tracked
