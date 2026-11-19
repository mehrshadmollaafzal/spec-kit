"""Command handler for ``specify workflow resume``."""

from __future__ import annotations

from . import _command_resume_state as resume_state
from . import _commands as cli


@cli.workflow_app.command("resume")
def workflow_resume(
    run_id: str = cli.typer.Argument(..., help="Run ID to resume"),
    input_values: list[str] | None = cli.typer.Option(
        None, "--input", "-i", help="Updated input values as key=value pairs"
    ),
    json_output: bool = cli.typer.Option(
        False,
        "--json",
        help="Emit the resume outcome as a single JSON object instead of formatted text.",
    ),
):
    """Resume a paused or failed workflow run."""
    from ..integrations.installer import IntegrationInstallError
    from .engine import RunState, WorkflowEngine

    project_root = cli._require_specify_project(load_integrations=False)
    cli._load_project_workflow_plugins_or_exit(
        project_root, json_output=json_output, run_id=run_id
    )
    try:
        engine = WorkflowEngine(project_root)
        with cli._stdout_to_stderr_when(json_output):
            engine._load_integrations()
    except (IntegrationInstallError, OSError) as exc:
        cli._fail_integration_load(exc, json_output=json_output, run_id=run_id)
    if not json_output:
        # Escape the literal bracket (\[) so Rich renders `[<step id>]` instead
        # of parsing it as a style tag named after the step id -- which it
        # silently swallows (losing the only identifying content on the line),
        # applies as formatting when the id happens to be a real style such as
        # `bold`, or raises MarkupError when the id forms a closing tag (`/`),
        # failing the whole run. Escape the interpolated values too, since both
        # come from workflow YAML. Mirrors the `\[<type>]` step-graph precedent
        # in workflow_info below.
        engine.on_step_start = lambda sid, label: cli.console.print(
            f"  \u25b8 \\[{cli._escape_markup(str(sid))}] "
            f"{cli._escape_markup(str(label))} \u2026"
        )

    inputs = cli._parse_input_values(input_values, json_output=json_output)
    err = cli._error_console(json_output)

    # Preserve the CLI preflight error contract without opening state.json.
    # An open reader can block another process from replacing it on Windows.
    try:
        RunState._state_path(run_id, project_root).stat()
    except FileNotFoundError:
        err.print(f"[red]Error:[/red] Run not found: {run_id}")
        raise cli.typer.Exit(1)
    except ValueError as exc:
        err.print(f"[red]Error:[/red] {cli._escape_markup(str(exc))}")
        raise cli.typer.Exit(1)
    except OSError as exc:
        err.print(f"[red]Resume failed:[/red] {cli._escape_markup(str(exc))}")
        raise cli.typer.Exit(1)

    def check_installed_workflow(state: RunState) -> None:
        # Use the locked checkpoint for the disabled-workflow check. Legacy
        # ownership is saved with the resumed checkpoint, so a stale CLI read
        # cannot restore an earlier execution state over another resume.
        if state.installed_workflow_id is not None:
            owner_root = resume_state._resolve_run_owner_root(
                state.installed_registry_root, project_root
            )
            cli._require_enabled_workflow(owner_root, state.installed_workflow_id, err)
        elif not state.installed_origin_tracked:
            if cli._require_enabled_workflow(project_root, state.workflow_id, err):
                state.installed_workflow_id = state.workflow_id
            state.installed_origin_tracked = True

    engine._before_resume = check_installed_workflow
    try:
        with cli._stdout_to_stderr_when(json_output):
            state = engine.resume(run_id, inputs or None)
    except cli.typer.Exit:
        raise
    except FileNotFoundError as exc:
        if engine._execution_state.get() is not None:
            cli._fail_workflow_execution(
                exc, json_output=json_output, state=engine._execution_state.get(), resume=True,
            )
        cli._fail_integration_load(
            FileNotFoundError(f"Run not found: {run_id}"), json_output=json_output, run_id=run_id,
        )
    except IntegrationInstallError as exc:
        execution_state = engine._execution_state.get()
        if execution_state is None:
            cli._fail_integration_load(exc, json_output=json_output, run_id=run_id)
        cli._fail_workflow_execution(
            exc, json_output=json_output, state=execution_state, resume=True,
        )
    except OSError as exc:
        if engine._execution_state.get() is None:
            err.print(f"[red]Resume failed:[/red] {cli._escape_markup(str(exc))}")
            raise cli.typer.Exit(1)
        cli._fail_workflow_execution(
            exc, json_output=json_output, state=engine._execution_state.get(), resume=True,
        )
    except ValueError as exc:
        cli._fail_recorded_run(
            exc, json_output=json_output, state=engine._execution_state.get(), resume=True,
        )
        err.print(f"[red]Error:[/red] {cli._escape_markup(str(exc))}")
        raise cli.typer.Exit(1)
    except Exception as exc:
        cli._fail_recorded_run(
            exc, json_output=json_output, state=engine._execution_state.get(), resume=True,
        )
        err.print(f"[red]Resume failed:[/red] {cli._escape_markup(str(exc))}")
        raise cli.typer.Exit(1)

    if json_output:
        cli._emit_workflow_json(cli._workflow_run_payload(state))
        raise cli.typer.Exit(cli._run_outcome_exit_code(state.status.value))

    status_colors = {
        "completed": "green",
        "paused": "yellow",
        "failed": "red",
        "aborted": "red",
    }
    color = status_colors.get(state.status.value, "white")
    cli.console.print(f"\n[{color}]Status: {state.status.value}[/{color}]")

    err_msg = cli._failed_step_error(state)
    if err_msg:
        cli.console.print(f"[red]Error:[/red] {cli._escape_markup(err_msg)}")

    raise cli.typer.Exit(cli._run_outcome_exit_code(state.status.value))
