# Agents Overview

- This file captures agent-specific instructions. Shared project conventions now live in `CONTRIBUTING.md`.
- Machine-specific adjustments can live in an untracked `AGENTS.local.md`; reference it when present.

## Testing

* acq4 uses pytest-style testing; place tests in a `tests/` directory adjacent to the relevant code.

## Project Overview

ACQ4 is a platform for neurophysiology acquisition and analysis, focusing on patch clamp electrophysiology, optogenetics, and related techniques. It provides tools for data acquisition, management, and analysis with features including:

* Semi- and fully-automated patch clamp electrophysiology
* Automated manipulator control
* Pipette cleaning/reuse and multipatch support
* Resistance-based autopatch
* Photostimulation mapping
* Fluorescent indicator imaging
* 2-photon imaging

## Shared Guidance

- Workflow, testing, technology, and architecture expectations are detailed in `CONTRIBUTING.md`; follow them unless explicitly directed otherwise.
- Consult `CONTRIBUTING.md` for environment setup, configuration search paths, and common development patterns before improvising.
- Use `AGENTS.local.md` for any local overrides and note deviations in your journal when they occur.
