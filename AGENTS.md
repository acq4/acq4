# Agents Overview

- This file captures agent-specific instructions. Shared project conventions now live in `CONTRIBUTING.md`.
- Machine-specific adjustments can live in an untracked `AGENTS.local.md`; reference it when present.

## Error handling

* Unguarded exceptions are the expected norm in acq4. Let them bubble up to the user.
* Only catch an exception when the catching block can actually deal with the situation usefully and in spec. "Usefully" means the handler restores a valid state or substitutes a correct result — not that it keeps the program running.
* Never write `except Exception: pass`, and do not convert a failure into a plausible-looking default (an empty list, a `None`, a "?"). A swallowed error becomes a silent wrong answer, which is worse than a traceback: the user loses both the failure and the reason for it.
* This applies with particular force to safety and config-loading code, where a swallowed exception can cache a wrong state or overwrite good data.

## Testing

* acq4 uses pytest-style testing; place tests in a `tests/` directory adjacent to the relevant code.

## Shared Guidance

- Workflow, testing, technology, and architecture expectations are detailed in `CONTRIBUTING.md`; follow them unless explicitly directed otherwise.
- Use `AGENTS.local.md` for any local overrides and note deviations in your journal when they occur.
