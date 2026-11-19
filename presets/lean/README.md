# Lean Workflow

Lean supplies concise constitution and specification prompts for the
[eleven command workflow](../../docs/fork-workflow.md).

| Command | Output |
| --- | --- |
| `speckit.constitution` | `.specify/memory/constitution.md` |
| `speckit.specify` | `spec.md` and the active feature selection |

Lean specify creates one requirements artifact, `spec.md`. The bundled
workflow uses that file to verify completion and bind the run to the feature.
Clarify proceeds without a requirements checklist and revalidates an existing
checklist when present. The remaining stages use their core command contracts.

## Installation

```bash
# Lean is a bundled preset — no download needed
specify preset add lean
```

## Development

```bash
# Test from local directory
specify preset add --dev ./presets/lean

# Verify commands resolve
specify preset resolve speckit.specify

# Remove when done
specify preset remove lean
```

## License

MIT
