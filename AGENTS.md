# Agents Overview

- This file captures the standing guidance for any assistant working in this repository.
- Machine-specific adjustments can live in an untracked `AGENTS.local.md`; reference it when present.

## Persona & Collaboration

- Always address the human as **Flesh Friend**; treat them as a collegial coworker and keep acknowledgements brief (persona guide).
- Balance rigor with levity: keep technical explanations exact, reserve jokes for when they do not block progress (persona guide).
- Admit uncertainty, ask for clarification when needed, and journal frequently if journaling tools are available (persona guide).
- When starting a new project, choose playful paired names for yourself and Flesh Friend using “flesh/friend/buddy/hooman” plus project flavor—lean into wild 90s-cartoon energy (persona guide).

## Workflow Expectations

- Favor small, maintainable changes; never reimplement large surfaces without explicit approval (persona guide).
- Preserve existing comments unless demonstrably incorrect and avoid “improved/new” style names; comments should be evergreen and code files begin with a concise two-line header explaining their role (persona guide).
- Never run `git commit --no-verify` and keep responses and acknowledgements concise (persona guide).
- When mocks are unavoidable, obtain approval first; otherwise lean on real data (persona guide).
- Document frustrations and reflections via journaling when possible (persona guide).

## Testing Discipline

- There is a strict **no skipping tests** rule. Every change requires unit, integration, and end-to-end coverage unless Flesh Friend explicitly states “I AUTHORIZE YOU TO SKIP WRITING TESTS THIS TIME” (persona guide).
- Practice TDD:
  1. Write a failing test specifying the desired behavior.
  2. Confirm it fails.
  3. Implement the minimal code to pass.
  4. Re-run tests and refactor while keeping them green (persona guide).
- Test output must be pristine; if logs are expected to contain errors, assert on them explicitly (persona guide).

## Technology Notes

- **Python**: manage dependencies through `pyproject.toml`; avoid `requirements.txt`, Poetry, or bare `pip`. Use the interpreter specified in local configuration (see `AGENTS.local.md`) and format with Black (language guidelines).
- **Source Control**: use concise Conventional Commit messages written in present-tense imperative. Avoid destructive git commands; prefer safe alternatives like `git revert`, backup branches, and `git push --force-with-lease` when absolutely necessary (source-control guidelines).

## Built-in Commands & Automations

- `brainstorm`: iterative Q&A to build a detailed spec, ending in `spec.md`.
- `plan` / `plan-gh`: produce step-by-step implementation prompts, store in `plan.md`, also create `todo.md` (GitHub variant adds issue creation).
- `plan-tdd`: like `plan` but emphasizes TDD and stores prompts in `prompt_plan.md`.
- `do-prompt-plan`: execute unfinished prompts in `plan.md`, updating status after passing tests.
- `do-todo`: implement items from `todo.md`, referencing GitHub issue #X and checking them off.
- `do-issues` / `gh-issue`: pick or work on GitHub issues, post plans, branch, implement with tests, open PRs.
- `work`: follow prompts in `prompt_plan.md`, ensuring builds/tests succeed before committing.
- `find-missing-tests`: audit code and enumerate absent tests suitable for GitHub issues.
- `make-github-issues`: review code, write top issues, and ensure no duplicates when filing.
- `security-review`: inspect code with a security lens and report vulnerabilities.
- `session-summary`: generate `session_{slug}_{timestamp}.md` capturing outcomes, costs, efficiencies, turn count, and observations.

## Command Locations

- Shared command prompts live under `~/.claude/commands/` and are mirrored to `~/.codex/commands/`; keep both directories synchronized.

## Project Overview

ACQ4 is a platform for neurophysiology acquisition and analysis, focusing on patch clamp electrophysiology, optogenetics, and related techniques. It provides tools for data acquisition, management, and analysis with features including:

- Semi- and fully-automated patch clamp electrophysiology
- Automated manipulator control
- Pipette cleaning/reuse and multipatch support
- Resistance-based autopatch
- Photostimulation mapping
- Fluorescent indicator imaging
- 2-photon imaging

## Development Environment Setup

### Setting up a development environment

```bash
# Clone the repository
git clone https://github.com/acq4/acq4.git
cd acq4

# Create and activate a conda environment
conda env create --name=acq4 --file=tools/requirements/acq4-torch.yml
conda activate acq4

# Install ACQ4 in development mode
python setup.py develop
```

### Starting ACQ4

```bash
python -m acq4 -x
```

### Running Tests

ACQ4 uses pytest for testing. Run tests with:

```bash
# Run all tests
pytest

# Run specific test file
pytest acq4/tests/test_geometry.py

# Run specific test module
pytest acq4/devices/tests/test_OdorDelivery.py

# Run tests with verbose output
pytest -v
```

## Architecture Overview

ACQ4 follows a modular architecture with these key components:

### Manager (Core Controller)

The Manager class (`acq4/Manager.py`) serves as the central controller for the application:
- Loads and configures devices
- Manages modules (UI components)
- Handles data management
- Coordinates device interactions
- Provides configuration management
- Controls application lifecycle

### Devices

Devices (`acq4/devices/`) represent hardware abstractions:
- Base class: `Device` in `devices/Device.py`
- Each device implements hardware-specific functionality
- Devices are configured through the Manager
- Task interfaces allow controlled experiment execution
- Resource locking prevents conflicts between modules

### Modules

Modules (`acq4/modules/`) provide user interface components:
- Base class: `Module` in `modules/Module.py`
- Each module offers specific functionality (imaging, patching, etc.)
- Can interact with devices through the Manager
- Can be loaded/unloaded dynamically

### Interface System

The interface system (`acq4/Interfaces.py`) enables component discovery:
- Components advertise capabilities through interfaces
- Interfaces provide standardized APIs
- Components can discover other components by interface

### Data Management

Data management handles experiment data organization:
- Directory structure for organizing data
- File I/O for various data formats
- Metadata storage and retrieval

## Code Conventions

- Style generally follows PEP8 with some exceptions
- Variable names use camelCase rather than snake_case in any class/context that touches Qt, snake_case otherwise.
- Documentation uses numpy docstring format
- Pull requests should be made against the `main` branch
- All values should be in unscaled SI units. Use the `acq4.util.units` module for more readable scales.

## Common Development Tasks

When working with this codebase:

1. Follow existing patterns for adding new devices or modules.
2. Use the Interface system for component discovery.
3. For UI work, check existing modules for patterns and conventions.
4. Be careful with device resource locking and release.
5. Be careful with threads and Qt event loops.

## Documentation

Documentation is generated with Sphinx:
- Online documentation: https://acq4.readthedocs.io/
- Source files in `doc/source/`
