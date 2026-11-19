# Phase 1 — Upstream source audit

Audit date: 2026-11-16. Baseline: `2ee2b1e8005905db05f5717300a469b3068b908f`.

## 1. Executive summary

This checkout contains a substantially broader system than an initializer plus slash-command prompts. It combines a Python CLI, agent command renderers, three parallel helper-script implementations, layered presets and extensions, a resumable workflow engine, executable workflow plugins, packaging/catalog infrastructure, and a partially migrated experimental MCP surface.

The most consequential findings for a future eleven-command workflow are:

1. **There are nine core agent commands:** constitution, specify, clarify, plan, tasks, analyze, implement, converge, and checklist. These are Markdown programs for an LLM, not nine Python CLI handlers. `specify plan` is not a registered CLI command. Their authoritative behavior is in `templates/commands/*.md`; deterministic helpers implement only portions of that behavior.
2. **Codex delivery is project-local skills:** `.agents/skills/speckit-<name>/SKILL.md`, invoked as `$speckit-<name>`. Core skills are generated copies. Codex's integration explicitly disables development symlinks. Editing upstream command templates does not automatically update an initialized project's skills. See `CodexIntegration`, `SkillsIntegration.setup`, and `integration_upgrade`.
3. **Feature identity is independent of Git.** Helpers select `SPECIFY_FEATURE_DIRECTORY`, then `.specify/feature.json`, and fail if neither supplies a usable value. They do not discover the feature by querying the Git branch. Branch creation and automatic commits belong to the optional Git extension. See `scripts/python/common.py:get_feature_paths` and `extensions/git/extension.yml`.
4. **Artifact ownership is largely instructional.** Constitution-only, analyze-read-only, converge-append-only, checklist ownership, and implementation gates are prompt contracts. They are not a filesystem authorization system. Even prerequisite checks can persist `.specify/feature.json`; hooks can introduce additional writes.
5. **Existing customization mechanisms are substantial but not interchangeable.** Extensions add namespaced commands and hooks; their normal installer rejects shadowing core commands. Presets can add, replace, prepend, append, or wrap command/template content. Workflows coordinate execution, with overlays and custom step/function packages. None of these automatically makes an LLM obey an artifact contract.
6. **The default automated workflow is smaller than the command inventory.** `workflows/speckit/workflow.yml` runs specify → review gate → plan → review gate → tasks → implement. It does not run constitution, clarify, checklist, analyze, or converge.
7. **There are material implementation/documentation differences.** Agent-context command prose omits current feature-pointer precedence and target self-seeding; the MCP architecture describes a migration whose full inventory is not implemented; script-side template resolution is not identical to the Python CLI resolver. These are detailed below, not treated as verified runtime failures.

This report supplies the source baseline and change-impact map. It does not select an architecture or define the eleven future commands.

## 2. Exact version, source baseline, and audit method

### 2.1 Observed checkout

| Property | Observed value |
|---|---|
| Repository root | `C:\Users\Mehrshad\Codex Project\spec-kit` |
| HEAD | `2ee2b1e8005905db05f5717300a469b3068b908f` |
| Branch | `main` |
| Commit subject | `fix(powershell): treat bracketed project paths literally in create-new-feature (#5399)` |
| Commit timestamp | `2026-11-12 10:30:46 -0600` |
| Tags at HEAD | None in the local repository |
| Local tags | `git tag --list` returned none |
| `git describe --tags --always --dirty` before report creation | `2ee2b1e8` |
| Shallow checkout | `git rev-parse --is-shallow-repository` returned `false` |
| Working tree before audit | `git status --short` and porcelain inspection returned no changes |
| Configured remote | `origin`: `https://github.com/mehrshadmollaafzal/spec-kit` for fetch and push |
| Declared package/version | `specify-cli`, `1.4.1.dev0` (`pyproject.toml`) |
| Local project virtual environment | `.venv/Scripts/python.exe` absent |

The remote is the user's fork, despite the task's description of an official checkout. The inspected tree is the authority; this audit does **not** establish that HEAD equals the present `github/spec-kit` remote branch or a published release. No fetch, remote change, branch switch, install, commit, or deployment was performed. The version is a development version, not evidence of a release tag.

`src/specify_cli/_assets.py:get_speckit_version` prefers installed distribution metadata and only then reads checkout `pyproject.toml`. Consequently, invoking an unrelated installed CLI would not prove the version of this tree. No installed CLI was used as a substitute for source inspection.

### 2.2 Evidence conventions and limits

References use exact repository-relative paths with either line numbers or precise symbols. Markdown command references identify the exact file and named execution section; these files are executable instructions to an agent, not merely explanatory documentation.

- **Deterministic:** behavior implemented in Python/Bash/PowerShell, inferred by tracing source. This does not mean it was executed in this audit.
- **Agent contract:** behavior requested by command Markdown; compliance depends on the agent and its tools.
- **Inference/risk:** a consequence of confirmed coupling, identified explicitly where the consequence was not reproduced.
- **Documentation:** supporting prose or architecture intent; not sufficient evidence that a feature is implemented.

Inspection covered registration inventories, all nine core command templates, helper paths and validation, optional command families/manifests, renderers, lifecycle operations, resolvers, workflow orchestration/state, and representative tests/CI. Large subsystems were traced by their relevant execution paths; this is not a claim that every line or every third-party catalog package was audited. No agent command, application test suite, workflow, installer, or Git-mutating script was executed. No test pass rate or coverage percentage is claimed. Missing `.venv` was left unchanged under the no-install restriction. Runtime behavior of external coding agents and services remains unverified.

### 2.3 Languages, packaging, dependencies, and entry points

| Area | Implementation |
|---|---|
| Main runtime | Python >=3.11, `src/specify_cli/` |
| Agent programs / artifacts | Markdown with YAML frontmatter; Markdown document scaffolds |
| Project helper scripts | Bash, Windows PowerShell 5.1, Python; corresponding six-file sets under `scripts/{bash,powershell,python}/` |
| Configuration | YAML manifests/workflows, JSON state/catalogs, agent-specific TOML/JSON/YAML/Markdown |
| Packaging | Hatchling; wheel package `src/specify_cli`; force-included assets in `specify_cli/core_pack/` |
| Executable | `[project.scripts] specify = "specify_cli:main"` |
| Root module | `src/specify_cli/__init__.py:main`, Typer `app`; direct-file `__name__ == "__main__"` guard present |
| Package `__main__.py` | Absent; do not assume `python -m specify_cli` is provided |
| Script executables | Each Python helper has `main()` and a direct-execution guard; Bash/PowerShell are standalone script entry points |

Declared runtime dependencies: `typer>=0.24.0`, `click>=8.2.1`, `rich`, `readchar`, `pyyaml>=6.0`, `packaging>=23.0`, `pathspec>=0.12.0`, `json5>=0.13.0`, `mcp>=2.2.0,<3.0.0`, `pydantic>=2.13.0,<3.0.0`, `lark>=1.3.1,<2.0.0`. Test extra: cryptography, pytest >=7, pytest-cov >=4, pytest-xdist >=3. These are declarations, not observed installed versions (`pyproject.toml`).

Wheel force-includes six page/settings files, all core command templates, all three script variants, five extensions (`git`, `agent-context`, `assess`, `bug`, `github`), three workflows (`speckit`, `bugfix`, `assess`), two presets (`lean`, `constitution-sync`), and bundle catalog snapshots. Source fallback is explicit in `src/specify_cli/_assets.py` and `IntegrationBase.shared_commands_dir`. Core initialization can therefore use local bundled assets without downloading a release archive. Optional catalog operations can still use the network.

Installed Python helpers are not guaranteed to use the CLI's Python environment. `src/specify_cli/integrations/base.py:IntegrationBase.resolve_python_interpreter` prefers the project's `.venv`, then runnable `python3`/`python`, then the running interpreter fallback. Script-side preset composition needs PyYAML; `scripts/python/common.py:_import_yaml` can delegate parsing to `SPECKIT_PYTHON_EXECUTABLE` (deprecated alias `SPECKIT_PYTHON`) if the chosen interpreter lacks it. Without a usable parser, manifest-based composition fails explicitly. A CLI package containing PyYAML therefore does not by itself prove that every generated script invocation can import it.

## 3. Repository architecture and subsystem responsibilities

| Source location / principal symbols | Actual responsibility |
|---|---|
| `src/specify_cli/__init__.py:app, main` | Root Typer assembly, compatibility re-exports, shared-install wrappers, project requirement helper. Windows stdout/stderr UTF-8 adjustment in `main`. |
| `src/specify_cli/command_init.py:register, ensure_constitution_from_template` | Initialization validation/options, agent setup, shared infrastructure, bundled workflow, optional preset/extensions, initial constitution. Much orchestration remains CLI-owned. |
| `src/specify_cli/command_check.py`, `src/specify_cli/command_version.py`, `selfs/` | Tool checks, local version/runtime information, self-update checking/upgrading. Tool checking can launch installed executables. |
| `src/specify_cli/_assets.py`, `src/specify_cli/shared_infra.py` | Wheel/source asset discovery; shared scripts/templates installation, command-reference rendering, file tracking, hash-aware preservation and refresh, managed `.specify/.gitignore`. |
| `src/specify_cli/_project.py`, `src/specify_cli/_init_options.py`, `src/specify_cli/integration_state.py`, `src/specify_cli/integration_runtime.py` | Project targeting, persisted initialization preferences, selected/installed integrations and per-integration runtime options. |
| `src/specify_cli/integrations/__init__.py:INTEGRATION_REGISTRY` | Explicit built-in adapter registry; lookup can use project-scoped dispatch registry. Catalog metadata is separate from executable registration. |
| `src/specify_cli/integrations/base.py` | Base adapter contract, argument construction and subprocess dispatch, template processing, Markdown/TOML/YAML/skills renderers. |
| `integrations/<agent>/__init__.py` | Agent-specific output, native invocation, executable arguments, event format, and setup/teardown choices. |
| `src/specify_cli/agents.py:CommandRegistrar` | Register contributed extension/preset commands into agent layouts; frontmatter, path rewriting, rendering and naming. Distinct from the core `SkillsIntegration.setup` path. |
| `src/specify_cli/integrations/manifest.py:IntegrationManifest`; `_lifecycle.py`, `_file_changes.py` | Owned-file manifests and hashes, guarded lifecycle operations and rollback/file-change tracking, cleanup. |
| `src/specify_cli/integrations/installer.py` | External executable adapter packages, trust/provenance, loading and project dispatch scope. |
| `src/specify_cli/extensions/__init__.py` | `ExtensionManifest`, `ExtensionRegistry`, `ExtensionManager`, `ExtensionCatalog`, `ConfigManager`, `HookExecutor`; a large combined domain module. `command_*.py` expose management. |
| `src/specify_cli/presets/_manifest.py`, `_registry.py`, `_resolver.py`, `_manager*.py` | Preset schema, priority/state, layered content composition, materialization and agent reconciliation. Public API re-exported through `src/specify_cli/presets/__init__.py`. |
| `src/specify_cli/artifacts/catalog.py`, `resolution.py`, `models.py` | Read-only inventory/provenance of **commands, templates, scripts**, with hook inventory as well. This is not a database tracking generated feature specs/tasks. |
| `src/specify_cli/workflows/engine.py:WorkflowDefinition, RunState, WorkflowEngine` | YAML definitions, validation, typed inputs, persisted execution and resume. |
| `src/specify_cli/workflows/_execution.py`, `base.py` | Execution tree/checkpoints, nested control flow, step context/result/status contracts. |
| `src/specify_cli/workflows/step/`, `function/`, `expressions/` | Built-in and installed executable steps; expression grammar/evaluation, interpolation, built-in/custom filters. |
| `src/specify_cli/workflows/overlay/` | Layer sources and structural edits to workflow step lists; separate from textual prompt composition. |
| `src/specify_cli/workflows/_package_install.py`, `_package_registry.py`, `_archive_install.py` | Shared workflow plugin staging, safe copying, locks, registry updates and rollback, external archive acquisition. |
| `src/specify_cli/events/__init__.py` | Native agent runtime events, configuration emission, generated dispatcher, deterministic supporting-script execution. Separate from before/after command hooks. |
| `bundles/`; `src/specify_cli/bundler.py` | Bundle manifests, validation, references, packaging, installation/update/removal and component coordination; compatibility facade. |
| `src/specify_cli/catalogs.py`, `authentication/`, `src/specify_cli/_download_security.py`, `src/specify_cli/_install_ignore.py` | Catalog stacks/cache/trust, HTTP/authentication, download/archive limits and validation, install exclusions. |
| `src/specify_cli/file_helper.py`, `src/specify_cli/_file_handles.py`, `src/specify_cli/_file_policy.py`, `src/specify_cli/_windows_abi.py` | Scoped filesystem operations and platform-specific safety. These protect participating host operations, not arbitrary agent edits. |
| `mcp_server/`, root/domain `mcp_*.py`, `_operation_*.py` | Experimental stdio service plus selected shared typed operations and adapters. Migration is incomplete. |
| `templates/commands/` | Nine core agent instruction programs; hooks, script calls, human interaction and artifact write contracts. |
| `templates/*-template.md` | Constitution/spec/plan/tasks/checklist scaffolds. Research, data model, contracts and quickstart are specified in instructions rather than separate bundled page templates. |
| `scripts/` | Feature/path resolution, scaffold creation, prerequisite validation and template resolution; installation copies them into projects. |
| `extensions/`, `presets/`, `workflows/`, `bundles/`, `integrations/` at root | First-party content/packages, examples, catalogs and supporting documentation. Root `integrations/` is not the Python registry. |
| `docs/`, `design/`, `spec-driven.md` | User documentation, architecture contracts and methodology. Useful context, but may describe intended/newer boundaries than implementation. |
| `tests/`, `.github/scripts/`, `.github/workflows/` | Automated tests, submission/security/version validators, CI, releases and agentic maintainer workflows. |
| `.devcontainer/`, `media/`, `newsletters/` | Development environment, presentation/documentation assets and communications; not command execution. |

The important architectural boundary is **host infrastructure versus LLM work**. A rendered skill is a prompt instructing the agent to run a helper, parse JSON, read artifacts, make judgments and edit files. The host does not itself implement the specification writer, planner, task decomposer, analyzer, or convergence assessor.

## 4. CLI and agent execution lifecycle

### 4.1 Initialization

`pyproject.toml` → `specify_cli.main()` → Typer root registration → `src/specify_cli/command_init.py:register`'s `init` handler:

1. Validate target/`--here`, existing-directory policy, integration, script selection and tool requirements. Noninteractive choices use configured/default integration (Copilot by default) and platform shell; Python scripts are opt-in. `--ignore-agent-tools` bypasses tool availability checks, not command generation.
2. Resolve the integration and its options, preflight setup, create an `IntegrationManifest`, and call adapter `setup`. Reinitialization also reconciles enabled extension/preset contributions.
3. Persist `.specify/integration.json`; install shared scripts/page templates with invocation spelling appropriate to the selected default integration.
4. Install bundled `speckit` workflow if absent. This is an installation, not execution of the workflow.
5. Save `.specify/init-options.json`, including selected integration/agent, script type, feature numbering and skills mode.
6. Install explicitly requested preset and extensions. URL extensions have explicit trust handling. Optional-install failures may be reported as warnings while initialization continues; initialization success must not be mistaken for successful installation of every optional component.
7. Seed `.specify/memory/constitution.md` through the resolved constitution template when appropriate. Existing project content is protected by the seeding logic. This is a scaffold, not completion of a governance interview.
8. Set executable permissions on applicable POSIX scripts and print agent-specific next actions.

Evidence: `src/specify_cli/command_init.py:ensure_constitution_from_template`, `register` (especially setup/install/finalization phases around lines 708–1000), `src/specify_cli/__init__.py:_install_shared_infra`, `src/specify_cli/shared_infra.py:install_shared_infra`. No unconditional core Git initialization is in this lifecycle; Git behavior is optional extension work.

### 4.2 Core command generation

`IntegrationBase.list_command_templates` enumerates Markdown files from wheel `core_pack/commands` or checkout `templates/commands`, with a preferred order and fallback for additional filenames. `process_template`:

- selects frontmatter `scripts.sh`, `.ps`, or `.py`, using supported fallbacks;
- replaces `{SCRIPT}` and removes the script metadata block;
- substitutes `{ARGS}`, `$ARGUMENTS`, and `__AGENT__` for the adapter's conventions;
- rewrites project paths through `src/specify_cli/agents.py:CommandRegistrar.rewrite_project_relative_paths` (`scripts/`, `templates/`, `/memory/` become project `.specify` resources);
- resolves `__SPECKIT_COMMAND_<NAME>__` to the target agent's prefix/separator.

For Codex, `SkillsIntegration.setup` rebuilds frontmatter with name, description, compatibility, author/source metadata and writes each `SKILL.md`, recording ownership. Original handoff frontmatter is not preserved as Codex skill handoff controls. Hooks receive an invocation-normalization note. For other agents, format bases and specialized adapters may preserve or transform different metadata; TOML and YAML are not skills in disguise (`src/specify_cli/integrations/base.py:process_template, SkillsIntegration.setup, TomlIntegration, YamlIntegration`).

### 4.3 Invocation and artifact handoff

Interactive flow: user invokes the installed agent command → agent interprets its instructions → agent runs selected project helper → helper emits JSON paths/template content → agent reads/writes artifacts → command's hook instructions run or offer follow-ups → agent reports completion. User arguments remain natural-language input to the agent; `$ARGUMENTS` in a Codex skill is not Python argument parsing or shell expansion performed by Specify.

Automated flow: `specify workflow run` → `WorkflowEngine` → `CommandStep.execute` → adapter `dispatch_command` → agent CLI with a native invocation string. The command step **does not** load the prompt file body and directly run its instructions. It relies on command/skill discovery in the child agent. Exit status and optional captured stdout/stderr are step outputs; success does not establish semantic artifact correctness (`src/specify_cli/workflows/step/command/__init__.py:CommandStep`, `src/specify_cli/integrations/base.py:dispatch_command`).

### 4.4 Generated project structures and ownership

```text
<project>/
  .agents/skills/speckit-<command>/SKILL.md       # Codex generated commands
  .codex/config.toml                            # native events when emitted
  .specify/
    init-options.json
    integration.json
    integrations/<agent>.manifest.json
    integrations/speckit.manifest.json
    memory/constitution.md
    memory/.constitution-template.json          # seed provenance
    templates/*-template.md
    templates/overrides/...
    scripts/{bash|powershell|python}/...
    feature.json                               # current feature pointer
    .gitignore
    extensions.yml                             # command hooks/config
    extensions/<extension>/...
    presets/<preset>/...
    workflows/<workflow>/workflow.yml
    workflows/runs/<run-id>/...
    workflows/{overlays,steps,functions}/...
    events.py                                  # native-event dispatcher when needed
  specs/<feature>/
    spec.md, plan.md, tasks.md
    research.md, data-model.md, quickstart.md
    contracts/...
    checklists/requirements.md, <domain>.md
```

This is a possible composed layout, not a claim that init creates every optional directory. `--script py` installs Python plus platform shell fallback; selecting one shell does not necessarily install all variants. `SPECIFY_FEATURE_DIRECTORY` can place feature artifacts outside the default `specs/<feature>` convention. Installer manifests track infrastructure; they do not own or hash every generated feature document (`src/specify_cli/shared_infra.py`, `IntegrationManifest`, `scripts/python/common.py:FeaturePaths`).

## 5. Complete command inventory

### 5.1 Core agent commands

| Logical name | Codex invocation | Canonical source | Default automation |
|---|---|---|---|
| `speckit.constitution` | `$speckit-constitution` | `templates/commands/constitution.md` | Manual |
| `speckit.specify` | `$speckit-specify` | `templates/commands/specify.md` | First command |
| `speckit.clarify` | `$speckit-clarify` | `templates/commands/clarify.md` | Manual |
| `speckit.plan` | `$speckit-plan` | `templates/commands/plan.md` | After spec review gate |
| `speckit.tasks` | `$speckit-tasks` | `templates/commands/tasks.md` | After plan review gate |
| `speckit.analyze` | `$speckit-analyze` | `templates/commands/analyze.md` | Manual |
| `speckit.implement` | `$speckit-implement` | `templates/commands/implement.md` | Last command |
| `speckit.converge` | `$speckit-converge` | `templates/commands/converge.md` | Manual |
| `speckit.checklist` | `$speckit-checklist` | `templates/commands/checklist.md` | Manual |

There is no core `taskstoissues.md` in this checkout. Issue conversion is `speckit.github.taskstoissues`, an optional extension command. There is no dedicated core test/build/review/release command. Generic implementation/testing can be instructed through implement or other optional workflows, but these are not extra core command names.

### 5.2 Optional local agent command inventory

All names below come from the corresponding `extension.yml`; command sources are under that extension's `commands/` directory. Codex replaces dots with hyphens and prepends `$`.

| Package | Version in source | Commands | Delivery |
|---|---|---|---|
| `extensions/git/` | 1.0.4 | `speckit.git.feature`, `.validate`, `.remote`, `.initialize`, `.commit` | Bundled, opt-in |
| `extensions/agent-context/` | 1.0.3 | `speckit.agent-context.update` | Bundled, opt-in |
| `extensions/github/` | 1.0.5 | `speckit.github.taskstoissues` | Bundled, opt-in |
| `extensions/bug/` | 1.0.2 | `speckit.bug.assess`, `.fix`, `.test` | Bundled, opt-in |
| `extensions/assess/` | 1.0.2 | `speckit.assess.intake`, `.research`, `.define`, `.shape`, `.decide` | Bundled, opt-in |
| `extensions/selftest/` | 1.0.0 | `speckit.selftest.extension` (`commands/selftest.md`) | Source utility; not wheel force-included |
| `extensions/template/` | Example manifest | `speckit.my-extension.example`, alias `.example-short` | Authoring scaffold, not a production built-in |

Thus there are 15 actual commands in the five wheel-bundled optional extensions, in addition to nine core commands. Catalog listings can advertise more packages, but are discovery records, not locally inspected executable command implementations. Presets may also add commands; bundled `lean` replaces five existing commands, and `constitution-sync` wraps constitution rather than adding a tenth core name.

### 5.3 Python CLI inventory and management effects

The following is the full registered CLI leaf inventory found through `src/specify_cli/__init__.py`, domain `_commands.py`/nested `src/specify_cli/__init__.py` registration and `command_*.py` decorators. Within a row, each comma-separated item is a separate command.

| CLI prefix | Registered leaves | Behavior / main state affected |
|---|---|---|
| `specify` | `init`, `check`, `version`, `mcp` | Project scaffold; executable/tool checks; version/runtime data; local stdio server |
| `specify self` | `check`, `upgrade` | Installed CLI update discovery and package upgrade; not project skill synchronization |
| `specify extension` | `add`, `remove`, `list`, `search`, `info`, `update`, `enable`, `disable`, `set-priority` | Extension packages, registries, contributed commands, hooks/events/config, priority/reconciliation; search/update can use catalogs/network |
| `specify extension catalog` | `add`, `list`, `remove` | Extension catalog configuration |
| `specify preset` | `add`, `remove`, `list`, `search`, `info`, `update`, `enable`, `disable`, `set-priority`, `resolve` | Preset packages/registry; generated command overrides/skills; resolved template contents or paths |
| `specify preset catalog` | `add`, `list`, `remove` | Preset catalog configuration |
| `specify integration` | `list`, `search`, `info`, `scaffold`, `install`, `uninstall`, `switch`, `use`, `upgrade`, `status` | Adapter discovery/scaffolding; installed commands/manifests/events; default selection; file-change status; external packages/trust where relevant |
| `specify integration catalog` | `add`, `list`, `remove` | Adapter discovery/install-source configuration |
| `specify artifact` | `list`, `info`, `lookup` | Inspect available command/template/script and hook inventory, composition and provenance; no generation of feature documents |
| `specify event` | `run` | Execute an event command's supporting script, passing event input; effects belong to the handler |
| `specify bundle` | `init`, `validate`, `build`, `add`, `install`, `remove`, `list`, `search`, `info`, `update` | Bundle manifest authoring/validation/archive creation; installed bundle and component lifecycle |
| `specify bundle catalog` | `add`, `list`, `remove` | Bundle catalog configuration |
| `specify workflow` | `add`, `remove`, `list`, `search`, `info`, `update`, `enable`, `disable`, `run`, `resume`, `status`, `resolve`, `definition` | Installed definitions/registry; composed definition; execution state/logs/snapshot; status and persisted definition introspection |
| `specify workflow catalog` | `add`, `list`, `remove` | Workflow catalog configuration |
| `specify workflow step` | `add`, `remove`, `list`, `search`, `info` | Executable step packages and step registry |
| `specify workflow step catalog` | `add`, `list`, `remove` | Step catalog configuration |
| `specify workflow function` | `add`, `remove`, `list` | Executable expression-function packages and registry |
| `specify workflow overlay` | `add`, `remove`, `list`, `enable`, `disable`, `set-priority` | Overlay YAML and priority/enabled state |

`--version`/`-V` is a root callback option, not another leaf. Registration is explicit; the presence of a file named `command_*.py` alone does not register a command. CLI management operations are not substitutes for similarly named agent commands. Detailed per-option semantics remain in each named command module; this audit focuses command file-operation detail on the agent workflow and its helpers, while retaining the complete management inventory and affected state.

## 6. Detailed core command behavior

All nine commands have `$ARGUMENTS` input and before/after extension-hook instructions. Source frontmatter resolves the helper variants shown below. Hook effects are additional to the command's own scope; section 9 explains their limits. Unless stated otherwise, no machine-enforced checkpoint or automatic test/build command is provided for the agent's work.

### 6.1 Constitution

Source: `templates/commands/constitution.md`, Scope Guard and Outline; helper: `scripts/python/resolve_template.py:main` and corresponding `resolve-template.sh/.ps1`.

Accepts governance principles or amendments. Resolves `constitution-template` to `TEMPLATE_CONTENT`, reads existing `.specify/memory/constitution.md` if present, and uses repository context to fill values. Writes/overwrites that constitution only. Requires semantic version/date reasoning, a temporary HTML Sync Impact Report, placeholder checks, and a summary with suggested commit message. Unrelated implementation/build/deploy intent must be deferred and reported, not executed. These are agent instructions.

No prior feature is required. Resolution failure must stop the command. Missing governance data can become documented TODOs or questions. No application code/tests/builds are requested. No Git commit is performed by core; the Git extension's mandatory `before_constitution` hook can initialize a repository and optional after hook can commit. A rerun reads existing governance but there is no resume token. Core deliberately does not propagate changes into templates; the opt-in constitution-sync preset changes that contract.

### 6.2 Specify

Source: `templates/commands/specify.md`, Outline and Mandatory Post-Execution Hooks. Helper: `resolve-template` for `spec-template`.

Accepts a natural-language feature description, optional explicit directory/branch intent, and existing project governance. Empty input errors. Generates a short name and selects a feature directory: explicit `SPECIFY_FEATURE_DIRECTORY`, otherwise `specs/<NNN>-<short-name>` or timestamp prefix according to `init-options.json`. Deprecated `branch_numbering` is consulted only when `feature_numbering` is absent and triggers a warning. Sequential numbering is instructed to scan existing spec directories.

The **agent**, not the current frontmatter helper, creates the feature directory, writes resolved template content into `spec.md`, and persists `feature_directory` in `.specify/feature.json`. It then fills user stories/requirements/success criteria and creates `checklists/requirements.md`. It reviews and updates spec/checklist, with up to three quality iterations and at most three critical clarification markers/questions. User answers resolve those markers. Feature branch creation is an optional extension hook and does not select the spec directory.

The existing `create-new-feature` helper is still shipped but is **not** called by this core template. It must not be used as evidence that current specify has programmatic collision protection or branch behavior. The template starts by writing scaffold content to `spec.md`; it does not provide the helper's `--allow-existing-branch` preservation semantics. Reusing an explicit directory therefore requires care: preservation is not an enforced transactional update. No application implementation/tests/builds are requested; checklist “validation” is an LLM review.

### 6.3 Clarify

Source: `templates/commands/clarify.md`, Outline. Helper: `check-prerequisites --json --paths-only` (`-Json -PathsOnly` for PowerShell).

Requires a selected feature and an existing spec by instruction. Paths-only deliberately skips prerequisite existence validation and pointer persistence; the agent must detect missing spec and instruct specify first. Optional constitution informs the ambiguity scan. Asks up to five questions, one at a time, and integrates accepted answers into `spec.md`, adding `## Clarifications` / `### Session YYYY-MM-DD` and editing affected sections. The instructions say to save after each answer, with atomic overwrite, but the CLI does not implement this write.

If `checklists/requirements.md` exists, reevaluates checkbox items outside code fences and toggles only changed markers; no regeneration of surrounding content. It does not create a missing checklist. User can terminate questioning early. No plan/code/tests/build changes are authorized by the command itself. Incremental saved answers aid recovery, but question/session state is not durably managed by Specify. The expected pre-plan ordering is advisory, not an engine prerequisite.

### 6.4 Plan

Source: `templates/commands/plan.md`; `scripts/python/setup_plan.py:main` and shell equivalents.

Helper resolves feature paths, creates the feature directory, and copies the composed `plan-template` into `plan.md` **only if the plan file does not already exist**. Missing/empty template causes failure when creating a new plan. Existing plan is preserved by the helper. The helper does not require spec contents or perform governance checks; the agent then reads spec, constitution and plan.

The agent fills technical context and constitution gates, researches unknowns into `research.md`, writes `data-model.md`, appropriate `contracts/*` for external interfaces, and `quickstart.md` as a runnable validation guide. It rechecks constitution compliance. It ends after design, not implementation. Research-agent dispatch is requested in the template; no Python planner enforces how that research is performed. Quickstart explicitly excludes full implementation bodies, migrations and full test suites. Contracts may be skipped for purely internal projects. No mandatory build/test execution is prescribed. Agent-context updating is an optional extension hook, not a core plan script. Replanning can modify existing design artifacts; no stale-task invalidation or multi-file transaction is provided.

### 6.5 Tasks

Source: `templates/commands/tasks.md`; `scripts/python/setup_tasks.py:main`.

Helper requires existing `plan.md` and `spec.md`, enumerates optional design docs and resolves `tasks-template`. It returns `FEATURE_DIR`, `AVAILABLE_DOCS`, `TASKS_TEMPLATE_CONTENT`, and compatibility path `TASKS_TEMPLATE`; it does not create tasks. Unlike `check_prerequisites`, its explicit checks are file existence, not nonempty-plan validation.

Agent reads required plan/spec, optional research/model/contracts/quickstart/constitution, and generates `tasks.md` grouped by setup, foundational work, user story priority and final polish. Format: `- [ ] T001 [P?] [USn?] Description with file path`. Dependencies/parallel opportunities and independently testable story increments are required. Tests are **optional**, generated when requested by spec or user/TDD request. Model field constraints are to be quoted into tasks. This command generates test *tasks*, not executable test files. It provides no preservation/merge contract for existing task completion or convergence phases; regenerating tasks can replace progress. No code, test execution, build or core Git mutation is prescribed.

### 6.6 Analyze

Source: `templates/commands/analyze.md`; helper `check-prerequisites --json --require-spec --require-tasks --include-tasks`.

Helper requires feature directory, nonempty plan, existing spec/tasks, and emits optional-doc inventory. Agent performs read-only semantic analysis of spec/plan/tasks and constitution: duplication, ambiguity, underspecification, governance, coverage and inconsistency. FR/SC identifiers are preferred stable keys; SC coverage excludes post-launch business metrics that do not require buildable work. Output is an in-session Markdown report, capped at 50 findings plus overflow, with coverage/severity and suggested next actions.

No report file is requested. Remediation requires explicit approval before follow-up editing. There is no source-code assessment or test/build execution requirement here. “STRICTLY READ-ONLY” governs the agent's own edits; helper pointer persistence and configured hooks remain separate possible mutations. Semantic determinism and stable findings are requested, not proven by a deterministic analyzer.

### 6.7 Implement

Source: `templates/commands/implement.md`; helper `check-prerequisites --json --require-tasks --include-tasks`.

Helper requires feature directory, nonempty plan and tasks; it does **not** require spec. Agent reads plan/tasks, optional design docs and constitution, and checks all feature checklists as a read-only gate. Any unchecked item requires asking whether to proceed; all-checked proceeds automatically. It must not mark checklist items complete. Custom checklists are reviewer-owned, whereas requirements.md is maintained by specify/clarify.

Agent inspects project setup and creates/updates relevant ignore files (`.gitignore`, `.dockerignore`, `.eslintignore`, `.prettierignore`, `.npmignore`, `.terraformignore`, `.helmignore`) or ESLint flat config ignore entries. It runs `git rev-parse --git-dir` to decide Git ignore handling. It executes tasks by phase/dependency, writes application code/config/docs/tests as required, runs test tasks before implementation, verifies outcomes, and marks completed tasks `[X]`. Nonparallel failures halt; successful independent parallel tasks can continue. Tests and coverage are requested at completion, but exact executable commands/builds depend on the project/task content.

The set of application files is intentionally open-ended and cannot be enumerated before inspecting that project's tasks. No core automatic commit/deployment step exists. Checkboxes and actual files provide progress for reruns, but no deterministic per-task execution journal or rollback exists outside optional workflow state.

### 6.8 Converge

Source: `templates/commands/converge.md`, Operating Constraints and Steps 1–9; helper uses the same require-spec/require-tasks flags as analyze.

Requires spec/plan/tasks by helper; additionally instructs that implement must already have run. **No helper verifies prior implement execution.** Reads artifacts as intent and inspects current code scoped by plan/task paths and concept searches. Includes every prior task regardless of checkbox state and every convergence phase. Classifies missing/partial/contradicts/unrequested work; constitution violations rank highest. An unfilled constitution scaffold is skipped gracefully.

For actionable findings, appends one `## Phase N: Convergence` section at the end of tasks, choosing highest existing phase+1 and maximum task ID+1, with source reference and gap type. It must not rewrite old tasks, spec, plan or code. When converged, tasks must remain byte-for-byte unchanged. It reports findings before appending, but does not require a separate approval for the append. No dedicated findings file, convergence-state JSON or test/build runner is provided. No Git comparison/history is used. Repeating before implementation can yield additional tasks for still-unmet work; there is no programmatic finding-ID deduplication ledger. Append-only and byte preservation are agent contracts, not enforced APIs. Helper pointer writes/hooks still need separate consideration.

### 6.9 Checklist

Source: `templates/commands/checklist.md`, Execution Steps; helper `check-prerequisites --json --template checklist-template`.

Accepts quality-review domain, scope/audience/depth; can ask three initial and up to two follow-up questions. Reads spec plus relevant optional plan/tasks and constitution. Creates `checklists/<domain>.md` or appends to an existing file, continuing CHK IDs. Newly generated items stay unchecked; the command must never replace/delete existing checklist content or mark items complete. It checks the **quality of written requirements**, not application behavior. Template content comes from the resolver, with an instructional fallback structure if unavailable.

Important mismatch: the command describes `plan.md` as optional context, but its helper requires a nonempty plan before returning. The helper will also fail for a missing required checklist template before an agent can use the prose fallback. These are source-level control-flow differences, not runtime reproductions. No code/test/build/Git work is requested. File contents permit append on later invocations, but no resume state exists.

## 7. Command-by-command file operation matrix

`F` means the resolved feature directory; `C` means `.specify/memory/constitution.md`. “Update” includes replacement where explicitly stated. This matrix describes core work; installed overrides and hooks can broaden it.

| Command | Reads | Creates | Updates / replaces | Deletes | Auxiliary effects |
|---|---|---|---|---|---|
| constitution | resolved constitution scaffold, existing C, repository governance context, hooks | C if absent | C, including temporary HTML impact comment | None instructed | resolver reads layer registries; hooks may initialize/commit Git |
| specify | description, init options, specs directory names, resolved spec template, optional C, hooks | F, F/spec.md, F/checklists/requirements.md | spec content, requirements checkbox status, `.specify/feature.json`; explicit reused spec path gets initial scaffold write | None instructed | optional branch hook; pointer is agent-written |
| clarify | F/spec.md, optional C and requirements checklist, hooks; feature pointer | clarification section within spec | spec after answers; changed requirements checkbox markers | None instructed | paths-only helper intentionally does not persist pointer |
| plan | F/spec.md, C, existing plan or plan-template, hooks | F/plan.md if absent by helper; research/model/quickstart/contracts by agent | plan/design artifact contents by agent; helper preserves existing plan | None instructed | feature pointer can be persisted before work |
| tasks | spec, plan, optional design docs/C; tasks-template; hooks | F/tasks.md | regeneration of tasks; no preservation guarantee | None explicitly | feature pointer can be persisted |
| analyze | spec, plan, tasks, C, hooks | No analysis file | No own artifact edits | None instructed | feature pointer may change; hooks may mutate |
| implement | tasks, plan, checklists, optional design docs/C; code/config/files | task-selected application/tests/docs/config; missing ignore files | application files; ignore entries; tasks checkboxes | Only if required by actual implementation tasks, no fixed deletion list | Git read; dependency/test/build artifacts depend on executed project commands; hooks may commit |
| converge | spec, plan, tasks, optional C, scoped source code, hooks | No separate report; new phase inside tasks | Append tasks only if gaps | None instructed | helper pointer persistence; hooks; no Git assessment |
| checklist | spec, helper-required plan, optional tasks/C, existing domain checklist, resolved scaffold | F/checklists/<domain>.md | Append items/IDs only; never change checked state | None instructed | feature pointer can be persisted |

Common deterministic read inputs include `.specify/init-options.json`, `.specify/integration.json` for invocation messages, `.specify/presets/.registry`, `.specify/extensions/.registry`, and selected template layers where applicable. Most commands read `.specify/extensions.yml` through the agent, not by routing all execution through `HookExecutor`.

### 7.1 Helper-specific file contract

| Helper (Python basename; shell equivalents use hyphens) | Reads / prerequisites | Writes / output |
|---|---|---|
| `resolve_template.py` | project root and named template stack | `TEMPLATE_CONTENT` JSON/text; no feature scaffold write |
| `check_prerequisites.py` | selected feature; normally directory/nonempty plan; optional required spec/tasks flags; optional named template | JSON `FEATURE_DIR`, `AVAILABLE_DOCS`, optional `TEMPLATE_CONTENT`; feature pointer can persist before validation |
| `check_prerequisites.py --paths-only` | root and selected feature identity | `REPO_ROOT`, `BRANCH`, `FEATURE_DIR`, `FEATURE_SPEC`, `IMPL_PLAN`, `TASKS`; skips existence checks and pointer persistence |
| `setup_plan.py` | selected feature, plan-template only if plan absent | mkdir F; seed new plan; JSON paths/branch; pointer may persist |
| `setup_tasks.py` | existing plan/spec; optional docs; composed tasks-template | returns content and compatibility template path; no tasks write; pointer may persist |
| `create_new_feature.py` | description/options, existing specs, spec template | optional dry-run; creates default feature directory/spec, preserves existing spec with allow-existing, writes feature pointer unless opt-out; prints branch-label/spec/number JSON and shell persistence advice |
| `common.py` | environmental selectors, state, template registries | shared path/persistence/composition helpers, not a standalone workflow phase |

`create_new_feature.py` still uses branch terminology for generated identifiers, but contains no Git branch creation. If its spec template is unavailable it can create an empty spec with warning; `setup_plan.py` rejects missing/empty scaffold instead. These differing failure semantics matter when reusing helpers (`create_new_feature.py:main`, `setup_plan.py:main`).

### 7.2 Optional command behavior and file operations

Each row's source is `extensions/<package>/commands/<full.logical.name>.md`, except selftest's `commands/selftest.md`. These are independently installed agent programs. Their prose guards are not guaranteed by the core workflow engine.

| Command | Inputs and required/optional predecessors | Reads | Creates / updates / external effects | Validation, confirmation, recovery |
|---|---|---|---|---|
| `speckit.git.feature` | feature description, optional exact `GIT_BRANCH_NAME`, numbering/template/prefix | Git refs/status and Git extension configuration; branch helpers | Git branch creation/switch; branch metadata output, not spec directory creation | `create-new-feature-branch` scripts implement naming/collision behavior; no feature artifact completion checkpoint |
| `speckit.git.validate` | current branch | agent runs Git branch queries, checks `SPECIFY_FEATURE` fallback and matching spec directories | report only | final branch segment must have sequential or timestamp prefix; missing spec is a warning; validation is instructed in the prompt |
| `speckit.git.remote` | current repository | agent runs `git config --get remote.origin.url` | remote URL/report only | prompt accepts GitHub HTTPS/SSH forms; missing Git/remote returns empty; no issue creation |
| `speckit.git.initialize` | project and Git config | repository status/config, project contents | `.git/`, index and initial commit if initialization is needed | script-backed; stop/report failed initialization; no spec or plan generation |
| `speckit.git.commit` | event name, optional generated message file | config, status/diff, changed project files | when enabled, `git add .` and commit; index/objects/refs; conventional style uses a temporary message file | event-specific configuration gates commits; optional hooks offer invocation; no push instruction |
| `speckit.agent-context.update` | configured target file(s), optional plan path | extension config/default target map, init options, feature pointer, plans, existing context files | creates or upserts marker-delimited section in configured context files (Codex default `AGENTS.md`); can normalize `.mdc` frontmatter | scripts validate target paths; preserves surrounding content subject to normalization; rerun upserts rather than checkpoint resume |
| `speckit.github.taskstoissues` | selected feature with plan/tasks; Git origin; GitHub MCP tools | tasks/design inventory, optional C/hooks, remote, existing GitHub issues | creates remote GitHub issues; no requested local tasks rewrite; helper can persist feature pointer | requires GitHub target matching remote; paginates existing issue titles for `T\d{3,}` IDs; skips matching IDs; no durable local mapping or transaction |
| `speckit.bug.assess` | report text/URL and slug | source code, report, optional fetched evidence | `.specify/bugs/<slug>/assessment.md` | rejects unusable report; URL trust rules; asks before overwrite interactively; automated collision handling; no source fixes |
| `speckit.bug.fix` | required assessment for resolved slug | assessment's remediation/files/tests contract, relevant code | application code/tests plus `.specify/bugs/<slug>/fix.md`; runs relevant tests if available | stops if root-cause/remediation is wrong and records deviation; must not edit assessment; existing fix report requires approval or automated refusal |
| `speckit.bug.test` | required assessment and fix report | reports, changed implementation/tests | runs reproduction/relevant tests; `.specify/bugs/<slug>/test.md`; possible normal test byproducts | no silent repair phase; records not-run checks and partial evidence; overwrite approval/refusal; test success alone is insufficient if reproduction not exercised |
| `speckit.assess.intake` | raw idea/text/URL/ticket/code pointer, slug | input/evidence | `.specify/assessments/<slug>/intake.md` | slug/path/URL safety instructions, collision/overwrite handling; no implementation |
| `speckit.assess.research` | assessment context | intake/context and allowed external evidence | same directory `research.md` | evidence-based discovery; protected overwrite; no application edits |
| `speckit.assess.define` | optional intake/research or substantive direct problem input | existing assessment evidence | `problem.md` | can run directly; slug alone is insufficient; protected overwrite |
| `speckit.assess.shape` | required `problem.md`; optional intake/research | assessment evidence/problem | `concept.md` | shapes options/scope/appetite, not technical implementation; protected overwrite |
| `speckit.assess.decide` | required problem; concept needed for go; all available evidence | intake/research/problem/concept | `decision.md`, with go/needs-clarification/kill and handoff | weak/unknown evidence cannot yield go; no automatic spec creation; protected overwrite |
| `speckit.selftest.extension` | extension catalog ID | discovery/install/registration metadata | instructs discovery and installation attempts in the current workspace, not an automatically isolated test project | utility prompt, not the pytest suite; requires tools and may access catalogs; no guaranteed cleanup/resume transaction |

Git's actual scripts are in `extensions/git/scripts/{bash,powershell,python}/`, including `create_new_feature_branch.py`, `initialize_repo.py`, `auto_commit.py`, and shared Git helpers. Its command Markdown currently shows explicit shell commands rather than the core frontmatter routing pattern. Agent-context also shows explicit Bash/PowerShell invocations despite shipping a Python implementation. GitHub issue conversion does declare all three script variants, with `resolve_tasks.py` a deliberately self-contained copy of feature/task prerequisite logic.

Optional command scope is not implied by package category metadata. For example, an “assessment” can write reports and fetch URLs; Git commit can stage unrelated uncommitted files because it uses `git add .`. None of these optional commands was invoked for this audit.

Issue deduplication is scoped to matching task IDs in repository issue titles, not a composite feature/task identity. **Inference:** because separate feature task files commonly restart at T001, issue conversion can mistake an issue from another feature for the same task. The prompt/source establishes that possibility; no remote reproduction was attempted (`extensions/github/commands/speckit.github.taskstoissues.md:67`).

## 8. Artifact lifecycle, path resolution, and ownership

### 8.1 Project and feature path resolution

`scripts/python/common.py:get_repo_root` first honors `SPECIFY_INIT_DIR` and rejects an invalid override; otherwise it searches upward for `.specify` from cwd, then from the script location, then uses the installed-script relative fallback. CLI project-scoped operations normally require cwd to be the project root or `SPECIFY_INIT_DIR`; they do not all share the helper's ancestor-search behavior (`src/specify_cli/__init__.py:_require_specify_project`, `src/specify_cli/_project.py`).

`get_feature_paths` selects:

1. `SPECIFY_FEATURE_DIRECTORY` if nonempty (relative to the project root or absolute).
2. `.specify/feature.json` containing a nonempty string `feature_directory`.
3. Otherwise error and stop. There is no Git-branch or “latest feature” fallback here.

`SPECIFY_FEATURE` supplies a display/current-branch label; otherwise the directory basename is used. It does not replace the required feature-directory selector. `FeaturePaths` hardcodes spec, plan, tasks, research, model, quickstart and contracts basenames (`scripts/python/common.py:137–189`; shell twins `get_feature_paths` / `Get-FeaturePathsEnv`).

When an environment selector is present, ordinary helpers persist it before subsequent validation. They rewrite `feature.json` only when the normalized value differs; the writer stores just `feature_directory`, so unrecognized extra keys are not preserved during replacement. `SPECIFY_FEATURE_NO_PERSIST=1` or `true` suppresses helper persistence, and paths-only supplies `no_persist=True` explicitly. This opt-out protects helper calls, not the separate specify prompt instruction that directly writes feature.json. The feature pointer is checkout-wide mutable state, not per-agent/per-run state (`persist_feature_json`, `get_feature_paths`).

Core feature resolution accepts absolute paths; it does not impose the installed-package confinement contract on all feature locations. Whether future artifacts must stay under the project is a Phase 2 policy question, not an existing universal guarantee.

### 8.2 Ownership/dependency matrix

| Artifact / scope | Creator and format | Consumers | Authorized writers in default prompt contracts | Consistency mechanism / limitation |
|---|---|---|---|---|
| `.specify/memory/constitution.md`, project | init seeds; constitution fills `constitution-template.md`; Markdown governance/version/dates | all core phases as required/optional above; optional extensions | constitution; guarded initial seeding; constitution-sync changes dependent-template scope | Runtime reading, semantic governance checks; no automatic invalidation of old feature designs |
| `F/spec.md`, feature | specify; `templates/spec-template.md` | clarify, plan, tasks, analyze, converge, checklist; implementation verification | specify, clarify | FR/SC/story identifiers and clarification section; no enforced schema or version lock |
| Clarification results, feature | clarify inside spec | plan/tasks/analyze/converge | clarify; later spec edits can alter same text | Saved Q/A plus integrated requirements; no separate clarification JSON/file |
| `F/plan.md`, feature | setup-plan seeds `plan-template.md`; agent fills | tasks, implement, analyze, converge, checklist; agent-context links | plan | Helper avoids replacing an existing plan; LLM can revise it; related docs/tasks not automatically reconciled |
| `F/research.md`, feature | plan phase 0; decisions/rationale/alternatives | plan design, tasks, implement | plan | Markdown convention, no separate scaffold or machine contract |
| `F/data-model.md`, feature | plan phase 1; entities/relationships/constraints | tasks and implement, referenced by analyses | plan | Task prompt carries constraints forward; no generated validator |
| `F/contracts/*`, feature | plan for external interfaces; format follows interface kind | tasks, implement, quickstart, reviews | plan; application tasks may deliberately evolve contract files if requested | No fixed contract language; downstream consistency is review-driven |
| `F/quickstart.md`, feature | plan; runnable setup/validation guide | tasks, implement | plan; subsequent task-driven doc changes if assigned | Instructions exclude full implementation; not an automatically executed test suite |
| `F/tasks.md`, feature | tasks with `tasks-template.md` | analyze, implement, converge, checklist, GitHub issue conversion | tasks regenerates; implement checks off; converge appends | Shared mutable work ledger, no file-level enforcement, CAS/versioning or universal merge |
| `F/checklists/requirements.md`, feature | specify, scaffold embedded in command | clarify, implement, human reviewers | specify creates/repairs; clarify toggles changed states | Review-of-spec semantics; implementation reads only |
| `F/checklists/<domain>.md`, feature | checklist with `checklist-template.md` | reviewers; implement gate | checklist appends unchecked items; reviewer/explicit reviewer-authorized evaluation changes markers | CHK IDs locally incremental; no global ID registry |
| Agent context file(s), project | optional agent-context extension; managed marker block | coding agents | context-update within managed block; ordinary manual text outside block | Plan pointer/reference, not a complete synchronized copy of technical context |
| Application code/config/tests/docs | implement or bug.fix | actual application/toolchain, converge, bug.test | implementation tasks/bug remediation | Project-specific tests/builds; no fixed paths or transaction boundary |
| `.specify/feature.json`, checkout | specify or helper persistence; JSON pointer | downstream helpers, context update | specify, ordinary feature helpers, optional GitHub resolver | Last selected feature; intentionally ignored by managed `.specify/.gitignore` |
| `.specify/workflows/runs/<id>/...`, run | workflow engine | resume/status/definition | engine and step output recording | State snapshots/checkpoints; does not make feature documents transactional |
| `.specify/bugs/<slug>/*.md`, bug | assess → fix → test reports with inline structures | following bug phases | each corresponding command; previous report edits restricted | Slug and explicit report dependencies, prompt-enforced overwrite controls |
| `.specify/assessments/<slug>/*.md`, idea | intake/research/problem/concept/decision | next assessment phases, manual specify handoff | corresponding assessment command | Evidence references and verdict constraints; no automatic feature creation |

### 8.3 Infrastructure state is a separate ownership plane

| State | Owner / reference | Purpose |
|---|---|---|
| `init-options.json`, `integration.json` | `src/specify_cli/_init_options.py`, `src/specify_cli/integration_state.py` | Selected/default integration, installed set/settings, script/skills/numbering preferences |
| `.specify/integrations/<key>.manifest.json` | `IntegrationManifest.manifest_path` | Agent-owned generated paths/hashes; install/upgrade/uninstall |
| `.specify/integrations/speckit.manifest.json` | `src/specify_cli/shared_infra.py:load_speckit_manifest` | Shared infrastructure ownership, distinct from adapter files |
| `.specify/memory/.constitution-template.json` | `src/specify_cli/presets/_manager.py:_materialize_constitution_template` | Hash/source provenance for seeded constitution; guarded generated-content detection, not the live governance version |
| `.specify/extensions/.registry`, `.specify/presets/.registry` | `ExtensionRegistry`, `PresetRegistry` | JSON metadata, enabled/priority and registration bookkeeping |
| `.specify/extensions.yml` | `HookExecutor` | Installed extension/hook configuration used by command prompts |
| `.specify/extensions/<id>/<id>-config.yml`, `local-config.yml` | `ConfigManager` | Shareable and machine-local extension settings |
| `.specify/integration-events.yml`, agent native config, `.specify/events.py` | `events.resolve_events`, emission/dispatcher code | Runtime-event overrides and execution plumbing |
| `.specify/workflows/workflow-registry.json` | `WorkflowRegistry` in `src/specify_cli/workflows/catalog/_domain.py` | Installed workflow metadata and lifecycle state |
| `.specify/workflows/steps/`, `functions/` and package registries | Workflow package installer/registry | Installed executable plugins and provenance |
| `.specify/bundle-records.json` | `src/specify_cli/bundles/records.py` | Required vs contributed components, conflict detection/removal ownership |
| Catalog configuration/cache | `src/specify_cli/catalogs.py` and domain catalog modules | Discovery sources, precedence, install eligibility and cached metadata |

No generic feature-artifact ownership manifest mediates every spec/plan/tasks edit. Installer hash protection therefore must not be mistaken for protection of generated requirements or completed work.

## 9. Extension, preset, workflow, and customization capabilities

### 9.1 Extension packages

`ExtensionManifest` validates schema/version/requirements/provided entries. Conventional package root is `extension.yml`; commands can point to files whose names differ from the logical command. Templates/scripts/config/hook/event contributions are supported. `ExtensionManager` owns directory/archive installation, compatibility, command registration, configuration scaffolding, enable/disable/remove/update and reconciliation. Registries record installed metadata; updates have transactional paths and rollback tests, but not all downstream agent work is transactional.

Primary names are `speckit.<extension-id>.<command>`; alias normalization and `_validate_install_conflicts` prevent collisions with core and other installed extension commands, including on-disk dot/hyphen shadowing (`src/specify_cli/extensions/__init__.py:1094–1253`). **Use an extension to add a phase; do not assume it can normally replace `speckit.plan`.** Presets are the existing replacement mechanism. Extension template contributions can influence artifact scaffolds through resolution, with runtime caveats below.

Core-name discovery normally enumerates bundled/source command templates, but retains a hardcoded nine-name `_FALLBACK_CORE_COMMAND_NAMES`. Preferred rendering order in `src/specify_cli/integrations/base.py` and root `SKILL_DESCRIPTIONS` also contain known core names. An eleven-command core inventory therefore needs review of both discovery and fallback/descriptive inventories; adding Markdown files alone is not a complete compatibility audit. Hook names are stored as event keys by `ExtensionManifest`/`HookExecutor.register_hooks`; adding a new event key still needs a consumer that actually checks and dispatches it.

`ConfigManager.get_config` merges defaults → project config → local config → environment (`SPECKIT_<EXT_ID>_<KEY>`). This is an available API, not proof that every standalone extension shell/Python script invokes it; several bundled helpers parse their own files for CLI independence.

### 9.2 Presets and template/command precedence

`PresetManifest` uses `provides.templates` entries typed `template`, `command`, or `script`; supported strategies are replace/prepend/append/wrap. Scripts allow only replace/wrap (`src/specify_cli/presets/_manifest.py:29–32`). A preset can supply a self-contained new command, including namespaced names even when the matching extension is absent (`_manager_commands.py:_PresetCommandMethods._register_commands`).

`PresetResolver.resolve` returns a path. `resolve_content` composes content; a path to one contributor is **not** the complete output of a composed template. The priority stack is:

| Precedence, highest first | Lookup / behavior |
|---|---|
| Project override | `.specify/templates/overrides/<name>.md`; script overrides under `overrides/scripts/`; always replacement |
| Enabled presets | `.specify/presets/<id>/`, lower numeric priority wins, deterministic ID tie ordering; manifest-declared paths authoritative |
| Enabled extensions | `.specify/extensions/<id>/`; ordered priorities; CLI resolver honors manifests and conventional fallback; replacement layers |
| Core | installed `.specify/templates/` and appropriate command/script lookup, with bundled/source fallbacks in CLI resolver |

For command composition, the nearest higher-priority replacement stops lower layers from contributing; layers above it compose bottom-up. Wrap substitutes `{CORE_TEMPLATE}` (scripts `$CORE_SCRIPT`); missing required wrapper token is an error. Command frontmatter is handled separately, retaining needed script metadata rather than treating all frontmatter as plain concatenated text. The highest layer does not necessarily contain every byte in final output (`_resolver.py:collect_all_layers, resolve_content`).

Command registration can materialize composed content under preset `.composed` and write generated agent commands. Enable/disable/remove/reprioritize/update reconcile winning content. Changes made directly to installed content are not a watched build system. Core adapter setup initially enumerates core sources; command overlays are applied through contribution registration/reconciliation. A project override is meaningful to the resolver but should not be assumed to replace an already generated Codex skill immediately.

**Confirmed resolver difference:** `scripts/python/common.py:resolve_template_content` honors preset manifest layers but searches extensions with `_conventional_template`, whereas CLI `PresetResolver` has `_extension_manifest_declared_template`. Thus a nonconventional extension template `file:` can be visible through CLI artifact/preset resolution and absent from script-side runtime resolution. Bash/PowerShell have their own implementations as well. Prefer no claim of full equivalence without a concrete cross-variant fixture. Similarly CLI script convention lookup uses `.sh`; support for every desired `.ps1`/`.py` override route is not implied by the abstract `script` type.

Bundled examples:

- `presets/lean/preset.yml`: replaces specify, plan, tasks, implement and constitution with lean prompts. Installing it changes workflow contracts; the nine core descriptions above describe the unoverridden baseline.
- `presets/constitution-sync/preset.yml`: wraps constitution for opt-in propagation into dependent materialized templates/commands. Its special guarded install-time handling is in `src/specify_cli/presets/_manager.py`; this is an explicit exception to core constitution-only ownership, not default behavior.

### 9.3 Command hooks versus native runtime events

**Command hooks:** `.specify/extensions.yml` contains `hooks.before_<phase>` / `after_<phase>`. Core templates skip disabled hooks, offer optional hooks, and instruct actual invocation/waiting for mandatory hooks. They explicitly skip nonempty conditions instead of evaluating them. Invalid YAML is reported but the core command continues, including a warning that mandatory hooks were not checked. This is a fail-open instruction path for governance that relies on a mandatory hook.

`HookExecutor.get_hooks_for_event`, `should_execute_hook`, `_evaluate_condition` support config/env existence and equality/inequality conditions; evaluation failures mean do not execute. Crucially, `execute_hook` returns command/invocation/description metadata and says execution is delegated to the AI agent (`src/specify_cli/extensions/__init__.py:6174`). It is not a subprocess executor. Printing `EXECUTE_COMMAND:` alone does not execute anything. Conditional hook capability in Python is therefore not evidence that an ordinary installed skill automatically evaluates conditional hooks.

**Runtime events:** `events.resolve_events` and adapter event mappings emit native agent config plus `.specify/events.py`; `specify event run` resolves command script metadata and launches the supporting script with event payload, bounded timeout and output handling. Canonical events include session/tool/prompt/stop lifecycle events; Codex maps them to names such as `SessionStart`, `PreToolUse`, `PostToolUse`, `SessionEnd`, `UserPromptSubmit`, `Stop`. These execute deterministic script entry points, not the complete natural-language command workflow. Script-path confinement and `shell=False` handling apply to this dispatcher, not to all LLM tool actions.

### 9.4 Workflows, overlays, and executable packages

`WorkflowDefinition` parses YAML metadata, inputs, defaults, steps and outputs. `validate_workflow` checks definitions and delegates step validation. Direct `WorkflowEngine.execute` does not promise to run the full validation pass automatically; public CLI flows and each step's runtime guards matter. `StepBase` defines `execute`, `validate`, `can_resume`, with `StepContext` and `StepResult` (`src/specify_cli/workflows/base.py`, `engine.py`).

All 14 registered built-in step keys (`src/specify_cli/workflows/__init__.py:_register_builtin_steps`):

| Key | Responsibility / source package under `src/specify_cli/workflows/step/` |
|---|---|
| `command` | Dispatch an installed Spec Kit command through selected integration |
| `prompt` | Dispatch arbitrary agent prompt |
| `shell` | Execute supporting local command; explicit env/stdin bindings, timeout and output handling |
| `gate` | Human/explicit-input approval or pause; reject/abort behavior |
| `init` | Initialize project through existing Specify capabilities |
| `github` | Add a label to an issue or pull request (`operation: add-label`); not a general GitHub command runner |
| `if`, `switch` | Conditional branch selection (`if_then/`, `switch/`) |
| `while`, `do-while` | Iterative execution (`while_loop/`, `do_while/`) |
| `fan-out`, `fan-in` | Item execution/concurrency and aggregation (`fan_out/`, `fan_in/`) |
| `workflow` | Nested workflow call with bound inputs/outputs |
| `slot` | Named extension location/default nested steps |

Expressions use `{{ ... }}`, with inputs, earlier step outputs and iteration context. They are evaluated through `src/specify_cli/workflows/expressions/`, not unrestricted Python `eval`. Installed function packages can add whitelisted exports/filters; collision validation happens before import. Their Python code remains executable trusted code, not sandboxed expressions (`function/loader.py:load_workflow_functions`).

Custom step packages contain `step.yml` plus `src/specify_cli/__init__.py`, installed under `.specify/workflows/steps/<id>/`; the loader finds a matching `StepBase` subclass, does not replace a built-in key, unloads prior project custom registrations and skips broken packages. Loading imports executable Python. Shared step instances must be stateless/thread-safe for concurrent fan-out. Function packages similarly use `function.yml` under `.specify/workflows/functions/`.

Workflow overlays are **two-tier** in this implementation: project-local overlays at `.specify/workflows/overlays/<workflow-id>/*.yml` over an installed base `.specify/workflows/<id>/workflow.yml`. They are not the four-tier preset resolver. Operations are `insert_before`, `insert_after`, `replace`, `remove`, anchored by step ID; lower numeric priorities apply later and win. Resolution composes but does not itself prove workflow semantic validity (`overlay/resolver.py:WorkflowResolver`, `schema.py:VALID_OPERATIONS`, `composer.py:StepListComposer`). Renaming an upstream anchor can break an overlay.

The shipped workflows are:

- `speckit` 1.0.2: four core commands and two explicit review gates, with resumable verdict inputs.
- `bugfix` 1.0.1: bug.assess → assessment review gate → bug.fix → bug.test.
- `assess` 1.0.0: intake → research → define → shape → decide → verdict review gate; stops before a manual specify handoff.

Only speckit is installed by ordinary init. The others are opt-in first-party bundle content; workflow definitions alone do not install or implement missing extension commands (`pyproject.toml`, respective `workflow.yml`).

### 9.5 Persistence and resume semantics

`RunState.runs_dir` is `.specify/workflows/runs/<run-id>/`. It writes `state.json`, `inputs.json`, `log.jsonl`, and a `workflow.yml` definition snapshot. State includes statuses, inputs, step results, current position, origin and nested execution tree. JSON checkpoints use temporary files and `os.replace`; in-process locks coordinate fan-out updates/logging (`engine.py:RunState.save, _atomic_write_json, append_log`).

`WorkflowEngine.resume` accepts paused/failed runs, loads the snapshot (legacy fallback to source if absent), validates restored state, merges/revalidates supplied inputs and resumes the execution tree/current step. It does not promise to undo file changes made before a failed child process. An interrupted command can be reexecuted; idempotence belongs to that command/step. Current agent command text is not frozen merely because the workflow YAML was snapshotted: command steps invoke installed names. Changing skills before resume can therefore change behavior mid-run. This is a source-derived compatibility risk, not a tested incident.

### 9.6 Bundles and catalogs

`src/specify_cli/bundles/manifest.py` accepts schema 1.0/1.1, component references for extensions/presets/steps/workflows, optional integration selection and bundle dependencies. `build_bundle`, `install_bundle`, records and primitive adapters coordinate distribution/reuse; installed records distinguish required components from newly contributed ones for removal/conflict handling. Bundle packages organize existing mechanisms; they are not a new agent execution engine.

Catalog stacks separate discovery from install permission, apply priority/source/version resolution and cache metadata. External adapters, workflow steps and functions execute Python when loaded; digest/trust and safe extraction machinery are important boundaries. No catalog declaration proves code compatibility or safety. Avoid promising whole-system rollback based solely on a component installer transaction (`src/specify_cli/catalogs.py`, `src/specify_cli/_download_security.py`, `src/specify_cli/integrations/installer.py`, `src/specify_cli/workflows/_package_install.py`, `src/specify_cli/bundles/installer.py`).

### 9.7 Capability comparison

| Desired customization | Existing mechanism | Constraint |
|---|---|---|
| Add agent command | Extension or preset command contribution | Namespace/collision rules; generated naming and registration must match |
| Replace existing core prompt | Preset replace, or core template edit in fork | Extension installer rejects core shadowing; materialized skills need refresh |
| Add guidance around a prompt | Preset prepend/append/wrap | Text composition can create contradictory instructions; wrapping depends on stable lower content |
| Customize artifact structure | Page-template override/preset/extension | Runtime resolver route and caller must actually consume composed content |
| Add supporting script | Package script plus explicit command/event/workflow reference | Merely installing a script does not invoke it; shell/OS variants need consideration |
| Add or reorder workflow phases | Workflow YAML/overlay; nested workflow/slot | Direct manual skills remain callable independently; ordering does not imply artifact enforcement |
| Execute deterministic new step | Installed `StepBase` package | Trusted Python, validation/resume/thread-safety duties |
| Add expression transformation | Function package | Whitelist/collision/API contracts; trusted executable code |
| Add a coding agent adapter | Built-in fork adapter or external integration package | Output/install/dispatch/event contracts; trust and lifecycle requirements |
| Enforce universal artifact ownership | No existing universal enforcement | Custom deterministic steps can enforce their own writes/checks; universal interception of all agent edits needs additional architecture |
| Rename core artifact/state contract everywhere | Core/helper/consumer changes or consistent replacements of all consumers | No single declarative feature-artifact schema controls every reader |
| Preserve upstream compatibility | Version pins/manifests, wrappers, overlays, bundle records, targeted tests | These reduce coupling; they do not guarantee merge-free upgrades |

## 10. Codex integration findings

### 10.1 Exact delivery and arguments

`src/specify_cli/integrations/codex/__init__.py:CodexIntegration` inherits `SkillsIntegration`, declares `.agents/` / `skills`, registrar extension `/SKILL.md`, `$ARGUMENTS`, `dev_no_symlink=True`, and skills default true. `SkillsIntegration.is_skills_mode` always returns true. This source supports skills-only Codex delivery; do not design around older `.codex/prompts` installation instructions.

The explicit built-in registry contains these adapter keys: `agy`, `alquimia`, `amp`, `auggie`, `bob`, `claude`, `cline`, `codebuddy`, `codex`, `command-code`, `copilot`, `cursor-agent`, `devin`, `docker-agent`, `droid`, `dsh`, `firebender`, `forge`, `gemini`, `generic`, `goose`, `grok`, `hermes`, `junie`, `kilocode`, `kimi`, `kiro-cli`, `lingma`, `mcode`, `muse`, `none`, `omp`, `opencode`, `pi`, `qodercli`, `qwen`, `rovodev`, `shai`, `tabnine`, `trae`, `vibe`, `zcode`, `zed` (`src/specify_cli/integrations/__init__.py:_register_builtins`). This includes generic/no-agent routes; registry presence does not imply that every adapter supports noninteractive CLI dispatch.

`SkillsIntegration.build_command_invocation` maps `speckit.plan` to `$speckit-plan`, and `speckit.github.taskstoissues` to `$speckit-github-taskstoissues`. `src/specify_cli/_invocation_style.py:DOLLAR_SKILLS_AGENTS` owns the dollar-prefix distinction. Command template placeholders and hook output must use this mapping consistently; a literal `/speckit.plan` is not the canonical Codex invocation in this checkout.

`CodexIntegration.build_exec_args` builds `[resolved_executable, "exec", prompt]`, appends configured extra arguments, optional `--model`, requested `-c model_reasoning_effort=...` / `-c model_context_window=...`, and optionally `--json`. Executable override is `SPECKIT_INTEGRATION_CODEX_EXECUTABLE`; extra arguments use the base integration environment convention. `context_size` is validated as a positive integer token count without leading zeroes, at most signed i64 maximum. These are Spec Kit's constructed arguments, not validation of the installed Codex CLI's current external behavior.

`IntegrationBase.dispatch_command` passes the project as subprocess cwd. Rendered skills instruct helpers to run from repository root; path rewriting makes references project-relative to `.specify`, not relative to the nested SKILL.md directory. Project selection via `SPECIFY_INIT_DIR` and feature selection still need consistent environment across subprocesses. Setting an environment variable in a child shell cannot change the parent process; persistent feature.json is the intended handoff when no explicit environment selector is carried forward.

### 10.2 Updates and synchronization

| Change | Propagation behavior |
|---|---|
| Edit checkout `templates/commands/*.md` | Used on future rendering from that checkout; does not rewrite existing project skills automatically |
| Upgrade CLI package | Changes available bundled sources; does not alone synchronize every initialized project |
| `specify integration upgrade codex` | Re-renders installed integration, checks manifest modifications and cleans stale output; for the active integration also refreshes managed shared files and reconciles contributions; `--force` is explicit overwrite authority |
| Shared script/page change | Shared installer normally adds missing files; `refresh_managed` can replace hash-matching installed files; `force` overwrites eligible existing files. Exact caller flags matter |
| Preset/extension lifecycle operation | Registers/reconciles affected commands and metadata; may change installed skill body or winning layer |
| Direct project page-template override | Runtime template-consuming helpers see it on subsequent calls; existing spec/plan/tasks contents are not retroactively regenerated |
| Direct edit of generated SKILL.md | Local customization detectable by manifest hashes; can block upgrade without force; not an upstream source change |
| Codex dev install | Writes files instead of symlinking; source edits still require re-registration |

`integration_upgrade` blocks modified integration files unless forced. It first installs missing shared infrastructure, then, when upgrading the active/default integration, calls the shared installer with `refresh_managed=True`: unchanged tracked shared files refresh, customized ones are preserved unless forced. Contribution re-registration is also active-integration-only and best-effort after the core upgrade; failures warn rather than guarantee a fully reconciled project. Upgrading an inactive adapter therefore does not provide the same refresh semantics. Layout migrations have additional guards when presets cannot be safely reconciled (`src/specify_cli/integrations/command_upgrade.py:integration_upgrade`, `src/specify_cli/integrations/_command_upgrade_layout.py`, `src/specify_cli/shared_infra.py`).

Other integrations can share `.agents/skills`; Codex's `multi_install_safe=True` does not prove arbitrary overlapping adapters can coexist. Multi-install conflict/lifecycle checks and default-sensitive shared template rendering matter. Codex events use `.codex/config.toml`, independently of skill files. Core plan does not generate AGENTS.md; the optional agent-context extension owns that managed context update (`tests/integrations/test_integration_codex.py:TestCodexInitFlow`).

### 10.3 MCP is not the core Codex command transport

The actual local server registers seven tools in `src/specify_cli/mcp_server/server.py:create_server`:

- Legacy `specify_list_commands`, `specify_describe_command`, `specify_run_command`, whose catalog admits only `version`.
- First-class `specify_version`, `specify_artifact_list`, `specify_artifact_info`, `specify_workflow_list`.

`artifact.lookup` is explicitly unavailable; workflow inventory marks the other workflow operations unavailable with reasons. The server has no implemented `specify_plan`, `specify_implement`, `specify_init` or general workflow-run MCP equivalent. The legacy inventory does not enumerate the newer hierarchy-owned tools. Architecture documents describe the destination shared-operation/typed-adapter design; they are not an implemented full MCP inventory (`src/specify_cli/artifacts/_mcp.py`, `src/specify_cli/workflows/_mcp.py`, `src/specify_cli/mcp_server/catalog.py`).

## 11. Existing testing and validation infrastructure

### 11.1 Frameworks and relevant evidence

Pytest is configured in `pyproject.toml` with strict markers and tests under `tests/`; coverage targets `src`. Tests use Typer `CliRunner`, temporary projects, monkeypatched dispatch/network, generated file assertions, script subprocesses and package/archive fixtures. xdist is used in CI. Test helpers isolate HOME/USERPROFILE/XDG settings for integration tests (`tests/integrations/conftest.py`); shell availability can skip tests (`tests/conftest.py`, `tests/parity_helpers.py`).

| Change area | Existing tests that can detect regressions | What they establish / do not establish |
|---|---|---|
| Init/registration/options | `tests/specify_cli/test_command_init.py`, `test_agent_config.py`; `tests/integrations/test_registry.py`, `test_cli.py` | CLI and generated-state behavior under fixtures; not live agent adherence |
| Codex output and arguments | `tests/integrations/test_integration_codex.py`, `test_integration_base_skills.py`, `test_skill_frontmatter_quoting.py` | Skill paths/body/frontmatter/hook invocation and dispatch settings |
| Other format renderers | `test_integration_base_markdown.py`, `test_integration_base_toml.py`, `test_integration_base_yaml.py`, per-agent tests | Agent-specific rendering and setup expectations; not universal native CLI compatibility |
| Hook/placeholder scaffolding | `tests/test_command_template_hooks.py`, `test_command_template_py_scripts.py`, `test_registered_command_hook.py`, `test_skill_placeholder_py.py` | Required clauses/script references/rendering; does not execute an LLM hook decision |
| Converge ownership | `tests/test_converge_template_scaffold.py` | Explicitly says it checks scaffold text and does not execute an LLM or assert its response |
| Constitution/spec/tasks/clarify | `test_constitution_template_sync_report.py`, `test_specify_template_numbering.py`, `test_tasks_template_constraints.py`, `test_clarify_stage_gate.py` | Prompt content contracts and selected deterministic scaffolding checks |
| Path/state/creation helpers | `test_init_dir.py`, `test_init_dir_cli.py`, `test_check_prerequisites_paths_only.py`, `test_specify_no_persist.py`, `test_setup_plan_feature_json.py`, `test_setup_plan_no_overwrite.py`, `test_setup_tasks.py` | File preservation, selection and prerequisite behavior |
| Cross-language parity | `test_check_prerequisites_python_parity.py`, `test_create_new_feature_python_parity.py`, `test_resolve_template_python_parity.py`, `test_setup_plan_python_parity.py`, `test_setup_tasks_python_parity.py`; extension parity tests | Selected Bash/PowerShell/Python equivalent outcomes; platform availability can skip cases |
| Preset composition/reconciliation | `tests/specify_cli/presets/test_resolver.py`, `test_manager_commands.py`, `test_manager_skills.py`, `test_manifest.py`; `tests/integration/test_preset_update_workflow.py` | Layer priority, strategies, install/remove/update and generated files |
| Extension safety/update | `tests/test_extensions.py`, `test_extension_registration.py`, `test_extension_skills.py`; `tests/specify_cli/extensions/test_command_add_path_traversal.py`, `test_command_update_transaction.py` | Validation, collision/registration, transaction and path failure cases |
| Integration lifecycle | `tests/specify_cli/integrations/test_lifecycle.py`, `test_installed_adapters.py`, `test_command_upgrade_layout.py`, `test_preflight_setup.py`, `test_file_changes.py` | Adapter trust/load/rollback, file ownership and migration guards |
| Workflow execution/resume | `tests/test_workflows.py`; `tests/workflows/test_composition_execution.py`, `test_step_capture.py`, `test_dispatch_settings.py`; `tests/specify_cli/workflows/test_command_resume_state.py`, `test_command_run_ownership.py` | State/control-flow/dispatch/negative cases; child success still not semantic success |
| Overlays/plugins | `tests/workflows/test_overlay_*.py`, `test_resolver_integration.py`; `tests/specify_cli/workflows/test_custom_steps.py`, `test_plugin_loading.py`, function/step subtrees | Composition, validation, plugin lifecycle and collisions |
| Bundled workflows/packages | `tests/workflows/test_bundled_speckit_workflow.py`, `test_bundled_bugfix_assess_workflows.py`; `tests/contract/test_wheel_*.py`, `test_firstparty_bundle_catalog_consistency.py` | Shipped assets, expected gates/order and wheel inclusion |
| Optional commands | `tests/extensions/{git,github,bug,assess}/`, context parity/feature-json tests | Manifests/scripts/prompt contracts for those packages |
| Native runtime events | `tests/specify_cli/events/test_events.py`, `test_command_run.py` | Native config/dispatch/script execution contracts |
| Artifacts/MCP | `tests/specify_cli/artifacts/`, `tests/specify_cli/mcp_server/`, `tests/specify_cli/workflows/test_mcp.py` | Typed/shared operations, inventory, generated schemas, stdio protocol and failures |
| Filesystem/security | `tests/test_file_helper*.py`, `test_file_handles.py`, `test_download_security.py`, `test_registrar_path_traversal.py` | Host operation boundaries; not an agent filesystem sandbox |

Generated-file tests are primarily explicit content/path/hash assertions, not evidence of a universal golden-snapshot framework covering complete LLM output. `tests/hooks/TESTING.md` is a manual mock-project procedure for observing LLM hook handling, separate from automated pytest evidence.

### 11.2 CI and validators

`.github/workflows/test.yml` runs Ubuntu/Windows/macOS pytest with Python 3.11/3.14/3.15 for ordinary events, expanded 3.11–3.15 for scheduled/manual runs, with exclusions for Windows/macOS 3.11 except manual dispatch. It installs test dependencies with uv and runs `uv run pytest -n auto`. This audit did not run it. Repository guidance for local work explicitly requires this worktree's own venv to avoid another worktree's editable installation.

`.github/workflows/lint.yml` runs Ruff, pip-audit, committed dependency-audit-input validation, Git whitespace checks, Markdownlint for documentation, ShellCheck, and a Bash 3.2 incompatibility guard. Prompt templates/skills are deliberately excluded from documentation formatting. `codeql.yml`, `extension-version-guard.yml`, `docs.yml`, and release/PyPI workflows cover additional security, package-version and publication concerns. `.github/scripts/` includes `check_security_requirements.py`, `check_extension_version_bump.py`, `validate_community_preset.py`, and `validate_community_workflow_step.py`. Agentic assessment and catalog-submission `.md`/`.lock.yml` workflows are maintainer automation, not extra core application phases.

PowerShell 5.1 compatibility is required by AGENTS/CONTRIBUTING and design guidance. `tests/test_ps1_encoding.py` checks ASCII-only content for its enumerated script roots. **Coverage limitation:** `tests/parity_helpers.py:POWERSHELL_EXE` chooses `pwsh` if present, otherwise Windows PowerShell. Passing this parity suite on a machine with pwsh is not automatically Windows PowerShell 5.1 validation. No 5.1 behavioral validation was executed here.

### 11.3 Important gaps for future changes

- Prompt-text assertions cannot prove read-only/append-only behavior, correct ambiguity judgments, code quality, actual mandatory-hook execution or byte preservation by an LLM. The converge test explicitly documents this limit.
- CLI exit code zero does not prove correct spec/task completion. Existing workflow tests cover orchestration, not the truth of each agent's completion claim.
- No universal versioned feature-artifact schema or dependency invalidation mechanism was found. A modified spec need not invalidate plan/tasks automatically.
- Cross-resolver equivalence has specific tests but the manifest/convention difference above remains visible in source. New template paths need fixtures across the actual runtime route, not just `PresetResolver` tests.
- Existing tests cannot validate the unspecified future eleven-command contract. Ownership, phase transitions, retry behavior and migration outcomes must first be defined in Phase 2.
- Real Codex/other-agent acceptance, native event support and external GitHub issue behavior were not exercised. These remain empirical validation needs, not inferred failures.

## 12. Architectural risks, coupling, and discrepancies

| Finding | Evidence | Consequence and confidence |
|---|---|---|
| Hardcoded artifact basenames | `common.py:FeaturePaths/get_feature_paths`, core command templates, GitHub `resolve_tasks.py` | **Confirmed coupling.** Renaming/splitting spec/plan/tasks impacts scripts, commands, templates, issue conversion and tests |
| Prompt-only write limits | constitution Scope Guard; analyze Operating Constraints; converge Operating Constraints | **Confirmed boundary.** No host enforcement for all agent edits; violation frequency not measured |
| Read-only command can change pointer | `check_prerequisites.py:main` → `common.py:get_feature_paths` | **Confirmed code path.** Analyze/converge prerequisites can update metadata with explicit environment feature selection, even before a later missing-file error |
| Shared active feature | `.specify/feature.json`, `persist_feature_json` | **Confirmed state model; inferred race.** Concurrent tasks can select the wrong feature unless callers carry explicit selectors and helper no-persist policy |
| Helper no-persist is not universal | specify prompt's direct pointer write vs `SPECIFY_FEATURE_NO_PERSIST` in helpers | **Confirmed mismatch in control boundary.** Orchestration opt-out alone does not suppress all agent-written pointer changes |
| Repeated tasks generation can discard progress | tasks Generate tasks.md vs implement checkboxes/converge append | **Confirmed absence of preserve contract.** Potential loss of completion and remediation history on regeneration |
| Plan setup does not verify spec | `setup_plan.py:main` | **Confirmed.** Script success alone is not readiness to plan; agent must read/validate required context |
| Checklist optional-plan prose conflicts with helper | checklist Step 5 vs check-prerequisites default plan requirement | **Confirmed source discrepancy.** A spec-only project cannot pass that helper route |
| Checklist fallback may be unreachable | checklist fallback prose vs `--template checklist-template` failure | **Confirmed control-flow discrepancy.** Missing scaffold errors before fallback instructions are reached normally |
| Extension hooks are not middleware | `HookExecutor.execute_hook`, template hook blocks | **Confirmed.** Mandatory/conditional hooks depend on prompt interpretation; invalid YAML continues; no execution from merely printing a marker |
| Extensions cannot freely replace core | `ExtensionManager._validate_install_conflicts` | **Confirmed restriction.** A replacement strategy must use presets or core changes rather than command collision |
| CLI and script resolvers differ | `_resolver.py:_extension_manifest_declared_template` vs script `_conventional_template` | **Confirmed source discrepancy.** Manifest-only nonconventional paths can produce different effective scaffolds; not reproduced |
| Display command names are transformed | `src/specify_cli/_invocation_style.py`, `resolve_command_refs`, `SkillsIntegration` | **Confirmed.** Hardcoded dotted names in custom content can fail in Codex; normalize at all generation/hook/dispatch points |
| Existing skills are materialized | `SkillsIntegration.setup`, Codex `dev_no_symlink` | **Confirmed.** Source/package updates do not imply active-project updates |
| Workflow snapshot does not freeze skill bodies | `RunState.definition_path`, `CommandStep.execute` | **Confirmed mechanics; inferred upgrade risk.** Resume after integration update may run changed agent behavior |
| Built-in workflow omits five core commands | `workflows/speckit/workflow.yml` | **Confirmed.** Do not assume full quality lifecycle is automatically enforced |
| Prior implement requirement only instructional | converge Goal vs helper checks | **Confirmed.** Presence of artifacts does not prove implementation happened |
| Template/runtime artifact names repeated | page scaffolds, command prompts, all script variants, optional issue resolver | **Confirmed maintenance surface.** A new artifact shape requires coordinated consumers, not just a new page template |
| Agent-context prompt is stale | command Behavior/Execution vs Python `_collect_context_files`, `_resolve_plan_path`, shell twins | **Confirmed.** Empty target config can self-seed from integration defaults, and feature.json is preferred before mtime fallback; prose says otherwise |
| Source self-test registry path is stale | `extensions/selftest/commands/selftest.md`, Step 3 vs `src/specify_cli/extensions/__init__.py:ExtensionRegistry` | **Confirmed.** Prompt requests `.specify/extensions/.registry/<id>.json`, but `.registry` is one JSON file. This source utility is not reliable evidence of the current registry layout |
| MCP architecture is ahead of implementation | `design/shared.md`, `design/mcp.md` vs `src/specify_cli/mcp_server/server.py`, domain inventories | **Confirmed migration gap.** Do not build against hypothetical MCP tools or assume every CLI operation is already typed/shared |
| PowerShell version coverage can vary | `tests/parity_helpers.py:POWERSHELL_EXE`; `.github/workflows/test.yml` | **Confirmed test selection.** pwsh success does not by itself establish 5.1 compatibility |
| GitHub task IDs are feature-local but issue search repository-wide | task generation plus taskstoissues dedup logic | **Inferred collision risk.** Different features' T001 issues can suppress new issues |
| Workflow plugin import executes code | `load_custom_steps`, function loader, integration installer | **Confirmed extensibility cost.** Package trust and host privileges matter; cwd is not sandboxing |
| Multiple manifest/registry ownership planes | extension/preset/integration/bundle/workflow records | **Confirmed complexity.** Direct generated-file edits or manual deletes can desynchronize lifecycle bookkeeping |
| Broad modules and compatibility re-exports | large `src/specify_cli/extensions/__init__.py`, root re-exports, domain command modules | **Confirmed maintenance coupling.** Refactors must preserve public import/patch points, not merely user-visible CLI names |

Additional distinction: `/memory/constitution.md` in raw command sources is **not** by itself a broken absolute path; the rendering pipeline rewrites it to `.specify/memory/constitution.md`. Likewise a raw `scripts/...` reference is expected to be rewritten. Auditing raw prompts without their renderer would create false findings.

No claim is made that every potential risk above has caused a production defect. The source-backed mechanisms are confirmed; the report labels predicted consequences separately.

## 13. Core fork versus extension mechanisms versus hybrid

“Extension mechanisms” in this comparison includes presets, workflows, overlays and executable step packages, not just an `extension.yml` package. The intended product can remain a fork under all three approaches.

| Dimension | Modify core directly | Use existing mechanisms | Hybrid fork with existing mechanisms |
|---|---|---|---|
| Functionality | Can change every command, helper, state contract and renderer | Strong for additive commands, prompt replacement/composition and orchestration | Core changes for missing contracts; package supplied process/content where suitable |
| Limits | None imposed by existing extension API, but must maintain all affected consumers | Namespace/collision rules; runtime resolver differences; no universal artifact edit enforcement | Retains mechanism limitations unless deliberately changed in core |
| Maintenance cost | Higher merge surface in prompts/scripts/core; exact cost depends on touched subsystems | Lower direct diffs, but wrappers/anchors/version constraints still need maintenance | Can isolate core patches, but adds coordination between fork and packages |
| Compatibility | Existing projects/extensions can break if names/state change | Preserves host APIs when used correctly; changed prompts can still break semantic expectations | Requires explicit host/package version and migration policy |
| Integration complexity | Reuse core renderer; all changed semantics must reach every output flavor | Must manage registration, precedence and refresh; noncore names longer in Codex | Centralized delivery possible through bundles, with more ownership layers |
| Upgradeability | Upstream merges require deliberate conflict resolution and regression evidence | Core updates can alter wrap bases, overlay anchors or dispatch APIs | Can combine targeted merges with independently versioned workflow content |
| Extensive workflow customization | Suitable for new hard invariants or a changed artifact model | Suitable for eleven phases if current artifact/dispatch/state contracts are sufficient | Suitable when most changes are content/orchestration and a few require deterministic host support |
| Testing burden | All touched deterministic behavior plus generated agents and migration | Package schemas/composition/registration plus semantic acceptance | Both, with tests allocated by ownership boundary |

This comparison does not choose a winner. The number eleven is not itself a reason to modify core: actual required artifact contracts, enforcement, invocation compatibility and migration behavior determine the boundary.

## 14. Important design considerations for Phase 2

Before selecting an implementation approach, define the following decisions against the evidence above:

1. **Eleven-command contract:** exact names, purpose, required/optional inputs, writable artifacts, postconditions and failure results. Map each to an existing phase, addition, split or replacement.
2. **Canonical identifiers versus agent spelling:** retain or replace `speckit.*` logical names; decide backward-compatible aliases and generated Codex names without collisions.
3. **Artifact model:** keep spec/plan/tasks as the integration contract, or explicitly enumerate every changed helper/consumer if splitting/renaming them. Decide how FR/SC/task IDs survive regeneration and cross-feature issue export.
4. **Enforcement boundary:** distinguish prompt policy from invariants requiring deterministic validation/guarded writes. Decide which checks are machine-verifiable and which remain human/agent judgments.
5. **Ordering and entry modes:** specify whether phases can be invoked manually out of order, and whether workflows provide convenience or mandatory gating. Define what constitutes proof of an earlier phase's completion.
6. **State and concurrency:** determine selection per worktree/feature/run/agent, behavior of direct specify pointer writes, and whether multiple features can execute concurrently.
7. **Recovery:** define retry/idempotence, append deduplication, atomicity, stale artifacts, and whether resumable workflows pin command/package versions as well as workflow YAML.
8. **Ownership:** settle reviewers' checklist authority, task regeneration versus implementation progress, constitution propagation and optional hook write scopes.
9. **Distribution and update:** decide which content is core, preset, extension, workflow, plugin or bundle; document how initialized projects receive updates and how local customizations are preserved.
10. **Platform matrix:** Windows PowerShell 5.1 is mandatory for relevant PowerShell behavior; maintain Bash/Python parity and ensure generated paths/argv work with spaces, brackets, encodings and nondefault roots.
11. **Acceptance evidence:** separate host tests, generated-file assertions and real-agent workflow scenarios. Success criteria should verify artifact postconditions rather than accept process exit zero alone.

These are design inputs, not an eleven-command design or implementation plan. Phase 1 made no functionality changes.

## 15. Unanswered questions and investigation limits

| Open question | Why still open / what evidence would settle it |
|---|---|
| Is this exact HEAD present on the official upstream, and what release/tag should the fork track? | Only local Git metadata was inspected; origin is the user's fork and no tags are available. Official remote comparison/release selection is a separate authorized baseline task if needed |
| What are the intended eleven commands and their hard invariants? | Not specified in this phase; cannot decide core-vs-package boundary from command count |
| How will current Codex versions execute these generated skills/events in the intended environment? | Spec Kit source constructs files/argv; no live Codex acceptance run or external compatibility verification was performed |
| Which customization routes require strict CLI/script resolver equivalence? | Nonconventional extension path difference is confirmed by source; focused cross-variant fixtures should be executed in a later testing phase |
| What migration population exists? | Existing initialized projects, legacy Codex layouts, local customizations and installed presets/extensions were not inventoried as product migration requirements |
| Should optional hooks be mandatory governance controls? | Current prompt handling continues on invalid YAML and skips conditions. Product requirements must define whether that is acceptable |
| Must resume preserve old skill/package behavior exactly? | Current workflow snapshots freeze definitions, not all dispatched command text or external execution environment |
| Must feature artifacts be confined to the project? | Core directory selectors allow absolute paths; package installer confinement is a different contract |
| What real-agent semantic assurance is required? | Static prompt assertions cannot establish ownership compliance or output quality; acceptance scenarios and evaluation criteria are not yet defined |
| Does the checked-out suite pass, including Windows PowerShell 5.1? | Tests were inspected, not executed; no local venv exists and installations were forbidden |
| How should third-party catalog packages interact with new phase names? | Remote executable packages were not downloaded or audited. Their compatibility cannot be inferred from catalog metadata |

No required local source was inaccessible due to permissions. `src/specify_cli/__main__.py` is absent rather than unreadable; renderer/resolver implementations were located in `src/specify_cli/integrations/base.py`/`src/specify_cli/agents.py` and `src/specify_cli/presets/_resolver.py`, respectively. No unavailable guessed path was used as evidence. Runtime tests, external package inspection and live-agent validation are explicitly outside the evidence collected here.

The only repository change made for this phase is this report. No source code, existing commands, templates, scripts, tests, Git configuration, branches or commits were changed. No Phase 2 architecture decision or implementation was undertaken.
