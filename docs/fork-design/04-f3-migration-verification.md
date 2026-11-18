# F3 migration verification

Reviewed on 2026-11-18 against baseline
`6fa8e63fa91844d957c56fb4c1d0653febb20ac7`.

## Reviewed scope

The changes cover integration-upgrade consistency and custom workflow compatibility.
The production changes reuse the existing integration write journal, workflow
installer, registry, overlay resolver, and recursive workflow validator.

- Built-in upgrades enter the existing lifecycle transaction. Workflow
  compatibility is checked before infrastructure or skills change and checked
  again before workflow publication. Success messages wait for commit.
- Native built-in skill preflight checks template availability and untracked
  destination conflicts. The upgrade checks the resulting manifest inventory.
- Upgrade manifest reconciliation and failures deleting selected stale owned
  files propagate to rollback. Installation timestamps survive repeated upgrades.
- Compatible custom workflow definitions and their provenance are preserved.
  Retired or unverifiable command references and missing completion verification
  produce explicit conflicts. Validation covers nested steps, active overlays,
  and installed child workflow calls.
- Rollback distinguishes the last observed write from concurrent or incomplete
  writes. Conflicts report the retained original snapshot for each affected path.

The seven production files are
`integrations/_command_upgrade_layout.py`, `integrations/_helpers.py`,
`integrations/_lifecycle.py`, `integrations/command_upgrade.py`,
`integrations/manifest.py`, `workflows/_bundled.py`, and `workflows/engine.py`
under `src/specify_cli/`.
Regression coverage lives in `tests/workflows/test_fork_workflow_install.py`.
The default recursive validator behavior and optional manifest-helper behavior
are preserved for callers that omit the new options.

## Verification evidence

The initial reproduction produced 12 failures and 3 passes before production
changes. Failure injection now checks installed file bytes after infrastructure,
skill, manifest, stale-file cleanup, workflow replacement, and registry failures.
It also exercises retry, repeated upgrades, concurrent edits, incomplete writes,
custom workflow ownership, custom skills, and historical run preservation.

The final focused run reported **177 passed, 3 skipped**. The skips require
Windows symlink privileges or meaningful POSIX execute bits. It includes the
fork artifact/progress, bundled orchestration, completion receipt, migration,
integration upgrade/layout, and external-adapter recovery regressions.
A fresh pre-commit run of the migration module reported **34 passed**.

The broad selection reported **4,564 passed, 165 skipped, 157 failed** on
Windows with Python 3.11.6. The command used the checkout interpreter:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -n 6 -rf --tb=line tests/test_fork_workflow.py tests/workflows tests/test_workflows.py tests/specify_cli/integrations tests/specify_cli/workflows tests/contract/test_wheel_bundled_workflows.py tests/contract/test_wheel_core_pack_scripts.py tests/contract/test_catalog_schema.py tests/contract/test_firstparty_bundle_catalog_consistency.py tests/test_agent_config_consistency.py tests/integrations/test_manifest.py
```

The baseline broad selection, excluding the separately run manifest module,
reported 4,470 passed, 165 skipped, and 144 failed. The baseline manifest module
reported 64 passed and 20 failed. All **157 current failing test IDs** occur
in the union of those baseline failures. Seven baseline failure IDs passed in
the current broad run. The remaining failures comprise:

| Remaining failure group | Count |
| --- | ---: |
| Windows symlink creation privilege errors, WinError 1314 | 107 |
| External initialization rollback assertions involving persistent lock files | 48 |
| Workflow composition assertions | 2 |

This comparison was rechecked before commit. The baseline was extracted with
`git archive`; its ZIP commit comment identifies the full baseline SHA above.
All 702 extracted source and test files matched their archive bytes. Baseline
logs identify that extracted directory as the pytest root, and the baseline
interpreter check resolved `specify_cli` from its `src/` directory.

The SHA-256 of sorted current failing node IDs, joined with LF and a trailing LF,
is `c67718c55ccbc96538dca5b39eba16dc697fcc30b25faa423e3980ba8b90916d`.
Detailed logs remain local under `.venv/`. Their byte-level SHA-256 values are:

| Local log | SHA-256 |
| --- | --- |
| `f3-reviewed-broad.log` | `d0dfd3b0a2a65650092007ba138d2c84a60cab52bfa3fb33b3fbf79a3e6b08dc` |
| `f3-reviewed-manifest.log` | `d19fbe32a900c320220e557c402842953fcceda11bef0fab00626ef6a2e2badb` |
| `f3-verified-broad.log` | `2795a0a677136fe277f0bf8990408def795d3f11196aa1b683598efbdb1b70e8` |
| `f3-migration-and-cli.log` | `a7d79b1478761d39db244264caf9ead02e9296a7ce8f7a2589db61bbcfa818c7` |
| `f3-wheel-release.log` | `9b03ef11399b83173cd448939f2541ec31251e9c2099929c8646fe8f8a44e667` |

Repository-pinned Ruff 0.15.0 lint, targeted formatting checks, and
`git diff --check` passed. The wheel built and installed into an isolated
environment using offline dependency resolution.

## Verified recovery

Windows PowerShell 5.1 exercised the installed wheel against the upstream-wheel
Codex project fixture. The recognized bundle upgraded directly:

```powershell
specify integration upgrade codex
```

A catalog-owned legacy definition returned exit 1 before installation changes.
After backing up `.specify/workflows/speckit/` and
`.specify/workflows/workflow-registry.json`, explicit replacement and upgrade
succeeded:

```powershell
specify workflow add speckit --bundled
specify integration upgrade codex
```

The replacement command overwrites the base workflow definition and changes its
registry ownership to bundled. Active overlays require their own review if they
cause a compatibility conflict.

Both paths produced exactly eleven skills, workflow version `2.0.0`, and clean
Codex/shared manifests. Repeated upgrades left 47 installed project files
byte-identical, excluding the advisory workflow lock.

## Remaining limitations

- The journal covers observed writes for the requested integration. Filesystem
  changes become visible individually. A hard process kill or power loss can
  bypass in-process rollback.
- Concurrent edits and incomplete writes with unobserved bytes are preserved.
  The operation fails and retains original snapshots. Back up the current edits,
  reconcile the reported paths, then retry. This manual recovery was tested.
- Explicit workflow replacement and integration upgrade are separate operations.
  A workflow can be used between them. Backups are required before choosing
  replacement of custom content.
- Compatibility validation checks declared workflow structure, resolvable
  command targets, and completion verification. Arbitrary shell, prompt, or
  custom step semantics cannot be proven by this static check. Dynamic command
  or workflow targets that cannot be resolved during preflight are rejected.
- Adapters with custom installation layouts retain their own preflight rules.
  Extension and preset registration retains its existing best-effort policy.
- The broad suite retains the baseline failures listed above. Linux/macOS and
  unattended agent execution were not exercised in this F3 verification.
