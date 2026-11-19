---
description: Create a specification and store it in spec.md.
scripts:
  sh: scripts/bash/workflow.sh context specify --json --paths-only
  ps: scripts/powershell/workflow.ps1 context specify --json --paths-only
  py: scripts/python/workflow_context.py specify --json --paths-only
---

## User Input

```text
$ARGUMENTS
```

## Outline

1. **Ask the user** for the feature directory path (e.g., `specs/my-feature`). Do not proceed until provided.

2. Before creating artifacts or changing `.specify/feature.json`, run `{SCRIPT}` from the project root with `--feature-directory "<provided directory>"`. Pass the directory as one argument in the current shell. If the helper fails, stop and report its error. For a destination outside the project, ask for an in-project path.

3. Create `FEATURE_DIR` and write the specification to `SPEC`, using the helper's validated paths.
   - Overview, functional requirements, user scenarios, success criteria
   - Every requirement must be testable
   - Make informed defaults for unspecified details

4. After writing the spec, persist the helper's actual `FEATURE_DIRECTORY` value in `.specify/feature.json`:
   ```json
   { "feature_directory": "<FEATURE_DIRECTORY value>" }
   ```

Report `spec.md` as the principal artifact when a workflow requests a completion
receipt. Lean creates a single requirements artifact and leaves existing
checklists alone. Clarify can proceed if there is no requirements checklist.
