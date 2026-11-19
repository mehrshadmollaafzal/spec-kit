# Fork quickstart

[Install this fork](fork-workflow.md#install-from-this-fork), then initialize a project
with the fork's `specify` executable. For an editable checkout, prefix the command
with `uv run` and use a target path outside the checkout.

```bash
specify init taskify --integration codex --script py
cd taskify
```

Launch Codex in the project directory. Invoke the skills below in the agent's chat
and review each result before moving on. Other integrations use their
[native invocation syntax](integrations/cli.md#command-invocation).

| Skill | What to review |
| --- | --- |
| `$speckit-constitution` | Project-wide principles and constraints |
| `$speckit-specify` | The feature spec, user scenarios, and success criteria |
| `$speckit-clarify` | Resolved ambiguities in the spec |
| `$speckit-architecture` | Shared system decisions and component boundaries |
| `$speckit-environment` | Shared runtime and deployment target requirements |
| `$speckit-plan` | The implementation design for this feature |
| `$speckit-taskscode` | Dependency-ordered coding tasks in `tasks-code.md` |
| `$speckit-analyze` | Design and task consistency before coding |
| `$speckit-impcode` | Application source and coding completion evidence |
| `$speckit-deployment` | Release and operational evidence when deployment is authorized |
| `$speckit-test` | Test results, defects, and acceptance evidence |

For example, start a feature with
`$speckit-specify Build a team task board with assignment and status tracking`.
The active feature is recorded in `.specify/feature.json`. Choose an in-project
feature directory. For an existing project, see the
[fork migration guide](fork-workflow.md#migration-and-customization).

`CODE_COMPLETE` records completion of the scoped coding deliverables. Test
results and deployment evidence belong to their respective stages. You can run
local tests without deployment. When target-dependent tests need infrastructure
that is unavailable, record them as blocked.

The [eleven command workflow](fork-workflow.md) documents file ownership, review
gates, and bundled automation. The [archived upstream command reference](reference/agentic-sdd.md)
describes the previous upstream workflow.
