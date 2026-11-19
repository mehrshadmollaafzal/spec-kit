"""Exercise feature selection and template resolution in an initialized project."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from specify_cli import app
from tests.parity_helpers import clean_env


@pytest.fixture(params=["py", "sh", "ps"])
def installed(request, tmp_path, monkeypatch):
    variant = request.param
    if variant == "sh":
        bash = (
            Path("C:/Program Files/Git/bin/bash.exe")
            if os.name == "nt"
            else shutil.which("bash")
        )
        if not bash or not Path(bash).is_file():
            pytest.skip("Bash unavailable")
        shell = [str(bash)]
    elif variant == "ps":
        ps = shutil.which("powershell.exe" if os.name == "nt" else "pwsh")
        if not ps:
            pytest.skip("PowerShell unavailable")
        shell = [ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
    else:
        shell = [sys.executable]

    root = tmp_path / "project with spaces"
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SPECIFY_INIT_DIR", raising=False)
    runner = CliRunner()
    result = runner.invoke(app, [
        "init", str(root), "--integration", "codex", "--script", variant,
        "--ignore-agent-tools", "--non-interactive",
    ])
    assert result.exit_code == 0, result.output
    monkeypatch.chdir(root)
    monkeypatch.setenv("SPECIFY_INIT_DIR", str(root))
    return root, variant, shell, runner


def run_helper(installed, *args, standalone=False):
    root, variant, shell, _ = installed
    scripts = root / ".specify/scripts"
    env = clean_env()
    env["SPECKIT_PYTHON_EXECUTABLE"] = sys.executable
    env["PYTHONIOENCODING"] = "utf-8"
    if standalone:
        script = {
            "py": "python/resolve_template.py",
            "sh": "bash/resolve-template.sh",
            "ps": "powershell/resolve-template.ps1",
        }[variant]
        options = [*args, "-Json" if variant == "ps" else "--json"]
    else:
        script = {
            "py": "python/workflow_context.py",
            "sh": "bash/workflow.sh",
            "ps": "powershell/workflow.ps1",
        }[variant]
        options = [*([] if variant == "py" else ["context"]), *args, "--json"]
    return subprocess.run(
        [*shell, (scripts / script).as_posix(), *options], cwd=root, env=env,
        capture_output=True, text=True, encoding="utf-8", timeout=40,
    )


def test_extension_template_matches_artifact_inventory_and_shell_helpers(installed):
    root, variant, _, runner = installed
    extension = root.parent / "forms"
    (extension / "forms").mkdir(parents=True)
    (extension / "templates").mkdir()
    (extension / "extension.yml").write_text(
        'schema_version: "1.0"\n'
        'extension: {id: forms, name: Forms, version: "1.0.0", description: Forms}\n'
        'requires: {speckit_version: ">=1.0.0"}\n'
        'provides:\n  templates:\n'
        '    - {name: architecture-template, file: "forms/system design.md"}\n',
        encoding="utf-8",
    )
    agreed = b"# Manifest-defined system design\n\nFill in each component.\n"
    declared = "forms/system design.md"
    (extension / declared).write_bytes(agreed)
    (extension / "templates/architecture-template.md").write_bytes(b"# Decoy\n")
    result = runner.invoke(app, ["extension", "add", "--dev", str(extension)])
    assert result.exit_code == 0, result.output

    installed_ext = root / ".specify/extensions/forms"
    feature = root / "specs/selected"
    feature.mkdir(parents=True)
    (feature / "spec.md").write_text("# Selected\n", encoding="utf-8")
    (root / ".specify/memory/constitution.md").write_text("# Principles\n", encoding="utf-8")
    (root / ".specify/feature.json").write_text(
        '{"feature_directory":"specs/selected"}', encoding="utf-8"
    )

    def assert_resolves(path, source_id):
        result = runner.invoke(app, ["artifact", "info", "template:architecture-template", "--json"])
        assert result.exit_code == 0, result.output
        source = json.loads(result.stdout)["stack"][0]
        assert source["active"]
        assert source["sourceId"] == source_id
        if path == installed_ext / declared:
            assert (root / source["sourcePath"]).resolve() == path.resolve()
        expected = path.read_bytes()
        for result in (
            run_helper(installed, "architecture"),
            run_helper(installed, "architecture-template", standalone=True),
        ):
            assert result.returncode == 0, result.stderr
            assert json.loads(result.stdout)["TEMPLATE_CONTENT"].encode("utf-8") == expected

    assert_resolves(installed_ext / declared, "forms")
    assert (installed_ext / declared).read_bytes() == agreed

    # A missing declaration cannot silently activate the decoy conventional file.
    (installed_ext / declared).unlink()
    assert_resolves(root / ".specify/templates/architecture-template.md", None)

    # Conventional contributions still work without a manifest.
    manifest = installed_ext / "extension.yml"
    declaration = manifest.read_bytes()
    manifest.unlink()
    assert_resolves(installed_ext / "templates/architecture-template.md", "forms")

    if variant != "py":
        # Existing shell-only infrastructure still resolves conventional files.
        manifest.write_bytes(declaration.replace(b"architecture-template", b"unused-template"))
        (root / ".specify/scripts/python/resolve_template.py").unlink()
        result = run_helper(installed, "architecture-template", standalone=True)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["TEMPLATE_CONTENT"] == "# Decoy\n"


def test_specify_preflight_rejects_external_and_preserves_selection(installed):
    root, _, _, _ = installed
    pointer = root / ".specify/feature.json"
    retained = b'{"feature_directory":"specs/keep"}\n'
    pointer.write_bytes(retained)
    outside = root.parent / "outside project"
    existing = root.parent / "existing feature"
    existing.mkdir()
    external_spec = existing / "spec.md"
    external_spec.write_bytes(b"# Prior requirements\n")
    for candidate in (str(outside), "../outside project", str(existing), "."):
        result = run_helper(installed, "specify", "--feature-directory", candidate)
        assert result.returncode == 1
        assert "feature directory must be inside the project" in result.stderr
        assert result.stdout == ""
        assert not outside.exists()
        assert external_spec.read_bytes() == b"# Prior requirements\n"
        assert pointer.read_bytes() == retained

    if os.name != "nt":
        for candidate in ("features/with:colon", r"features/with\backslash"):
            result = run_helper(installed, "specify", "--feature-directory", candidate)
            assert result.returncode == 1
            assert "portable project-relative path" in result.stderr
            assert result.stdout == ""
            assert not (root / "features").exists()
            assert pointer.read_bytes() == retained

    for candidate in ("features/next feature", str(root / "features/next feature")):
        result = run_helper(installed, "specify", "--feature-directory", candidate)
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert Path(data["FEATURE_DIR"]) == root / "features/next feature"
        assert Path(data["SPEC"]) == root / "features/next feature/spec.md"
        assert data["FEATURE_DIRECTORY"] == "features/next feature"
        assert data["TEMPLATE_CONTENT"]
        assert not (root / "features").exists()
        assert pointer.read_bytes() == retained

    (root / ".specify/templates/spec-template.md").unlink()
    lean = run_helper(installed, "specify", "--paths-only", "--feature-directory", "features/lean")
    assert lean.returncode == 0, lean.stderr
    lean_paths = json.loads(lean.stdout)
    assert lean_paths["FEATURE_DIRECTORY"] == "features/lean"
    assert "TEMPLATE_CONTENT" not in lean_paths
    assert not (root / "features").exists()
    assert pointer.read_bytes() == retained
