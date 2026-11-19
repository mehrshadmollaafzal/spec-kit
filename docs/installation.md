# Installation Guide

## Prerequisites

- **Linux/macOS** (or Windows; PowerShell scripts now supported without WSL)
- A [supported AI coding agent](integrations/index.md#choose-an-integration).
  See your integration's page for its installation requirements, or use
  [`none`](integrations/none.md) for agent-neutral scaffolding.
- [uv](https://docs.astral.sh/uv/) for package management (recommended) or [pipx](https://pipx.pypa.io/) for persistent installation
- [Python 3.11+](https://www.python.org/downloads/)
- [Git](https://git-scm.com/downloads) to clone the fork or use the optional Git extension

## Installation

### Install from the fork checkout

Follow [Install from this fork](fork-workflow.md#install-from-this-fork) for
Windows and POSIX setup. For a development checkout, clone the fork branch and
run `uv sync` from the checkout.

```bash
git clone --branch codex/eleven-command-workflow https://github.com/mehrshadmollaafzal/spec-kit.git
cd spec-kit
uv sync
uv run specify init ../my-product --integration codex --script py
```

Run `uv run specify version` from the checkout to verify the CLI. For a
persistent tool install using a published fork tag, select a tag from
[the fork's releases](https://github.com/mehrshadmollaafzal/spec-kit/releases)
and follow the [upgrade guide](upgrade.md). A wheel built from the checkout can
also be installed locally.

### Archived upstream installation routes

The original [PyPI](install/pypi.md), [pipx](install/pipx.md) and
[one-time usage](install/one-time.md) guides describe upstream releases.
Use the [fork installation instructions](fork-workflow.md#install-from-this-fork)
for the eleven command workflow.

### Specify Integration

Interactive terminals prompt you to choose a coding agent integration during initialization. Non-interactive sessions, such as CI or piped runs, default to GitHub Copilot unless you pass `--integration`.

You can proactively specify your coding agent integration during initialization:

```bash
specify init <project_name> --integration claude
specify init <project_name> --integration gemini
specify init <project_name> --integration copilot
specify init <project_name> --integration codebuddy
specify init <project_name> --integration pi
specify init <project_name> --integration omp
```

The README examples use GitHub Copilot's default skills mode. To use another
supported agent, replace `copilot` with its
[integration key](integrations/index.md). See
[Command Invocation](integrations/cli.md#command-invocation) for the
syntax used by each agent and mode.

### Specify Script Type (Shell, PowerShell, or Python)

Automation scripts are available as Bash (`.sh`), PowerShell (`.ps1`), and Python (`.py`) variants.

Auto behavior:

- Windows default: `ps`
- Other OS default: `sh`
- Interactive mode: you'll be prompted unless you pass `--script`

Force a specific script type:

```bash
specify init <project_name> --script sh
specify init <project_name> --script ps
specify init <project_name> --script py
```

### CI and AI Agent Harnesses

For environments without a keyboard, or a PTY that cannot send arrow keys, pass
`--non-interactive` so initialization never waits on a picker:

```bash
specify init my-project --non-interactive --ignore-agent-tools
```

`--ignore-agent-tools` skips the agent executable check when the agent will run
elsewhere; omit it when you want that check. Non-interactive initialization
defaults to Copilot unless you select another integration explicitly. Run these commands from the fork checkout with `uv run`, or use an installed fork executable.

For a non-empty directory, `--force` acknowledges the merge warning. Review the
[existing-project guide](how-to/existing-projects.md) and commit or back up local
changes before initializing:

```bash
specify init --here --force --non-interactive --integration claude
```

### Ignore Agent Tools Check

If you prefer to get the templates without checking for the right tools:

```bash
specify init <project_name> --integration claude --ignore-agent-tools
```

## Verification

After installation, run the following command as a local version/runtime check:

```bash
specify version
```

Run it through `uv run` from a development checkout. A successful initialization
installs the core skills listed in the [fork quickstart](quickstart.md). Invoke
them from the coding agent's chat.

`specify self check` checks for a fork release. See the [Upgrade Guide](upgrade.md)
for checkout and release updates.

Scripts are installed into a variant subdirectory matching the chosen script type:

- `.specify/scripts/bash/` — contains `.sh` scripts (default on Linux/macOS)
- `.specify/scripts/powershell/` — contains `.ps1` scripts (default on Windows)
- `.specify/scripts/python/` — contains `.py` scripts (chosen with `--script py`; also installs the platform shell fallback)

## Choose a Process

After initialization, launch your coding agent in the project directory and
follow the [SDD quickstart](quickstart.md),
[bug-fixing quickstart](guides/bugfix.md), or
[idea assessment quickstart](guides/assessment.md). These are independent entry
points. SDD is available immediately; the other guides show how to install their
bundled, opt-in extensions.

## Troubleshooting

### Enterprise / Air-Gapped Installation

If your environment blocks access to PyPI or GitHub, see the [Enterprise / Air-Gapped Installation](install/air-gapped.md) guide for step-by-step instructions on creating portable wheel bundles.

### Git Credential Manager on Linux

If you're having issues with Git authentication on Linux, see the [Air-Gapped Installation guide](install/air-gapped.md#git-credential-manager-on-linux) for Git Credential Manager setup instructions.

> Agent invocation examples on this page use GitHub Copilot's default skills syntax (`/speckit-*`). For other integrations and modes, see [Command invocation](integrations/cli.md#command-invocation).
