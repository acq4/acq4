# Contributing to acq4

Contributions to acq4 are welcome! This document collects shared expectations for humans and robots alike — workflow, testing, and technical context. Robot-specific notes live in `AGENTS.md`.

## Submitting Code Changes

* The preferred method for submitting changes is by github pull request against the "main" branch.
* Pull requests should include only a focused and related set of changes. Mixed features and unrelated changes are more likely to be rejected.
* For major changes, it is recommended to discuss your plans on the mailing list or in a github issue before putting in too much effort.
* Many changes (especially new devices and user interface modules) can be implemented as an extension module rather than modifying the acq4 codebase; this can be a faster way to make your code available to the world.

## Collaboration & Workflow

* Favor small, maintainable changes; avoid reimplementing large surfaces without explicit approval.
* Preserve existing comments unless demonstrably incorrect and avoid “improved/new” style names—comments should stay evergreen and code files begin with a concise two-line header explaining their role.
* Keep responses and acknowledgements concise; use levity only when it does not block progress.
* Prefer real data to mocks. If mocks are unavoidable, obtain buy-in before building them.
* Document frustrations or reflections via journaling utilities when available.

## Testing Discipline

* There is a strict no skipping tests rule. Every change requires unit, integration, and end-to-end coverage unless explicitly authorized otherwise.
* Follow test-driven development:
  1. Write a failing test specifying the desired behavior.
  2. Confirm it fails.
  3. Implement the minimal code to pass.
  4. Re-run tests and refactor while keeping them green.
* Test output must be pristine—if logs are expected to contain errors, assert on them explicitly.
* acq4 uses pytest-style testing; place tests in a `tests/` directory adjacent to the relevant code.

## Documentation

* Update documentation alongside behavior changes and confirm that Sphinx builds remain healthy.
* Use the numpy docstring format for API documentation.
* Inline docstrings and `doc/source/` are the sources of truth for reference material.

## Style Guidelines

* acq4 prefers PEP8 for most style issues, balancing readability with practicality.
* Qt-adjacent names should use camelCase rather than snake_case for consistency.
* Python formatting relies on `black -S -l 100` using the interpreter configured locally (see `AGENTS.local.md` for machine-specific notes).

## Source Control

* Use concise Conventional Commit messages written in present-tense imperative.
* Never run `git commit --no-verify`.
* Prefer safe remediation strategies such as `git revert`, backup branches, or `git push --force-with-lease` only when absolutely necessary.

## Development Environment

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

## Technology Notes

* The UI and acquisition stacks are Qt-heavy with many scientific and ML dependencies.
* Import Qt from the unified wrapper: `from acq4.util.Qt import ...` for cross-backend compatibility.
* Requirements are stored in `tools/requirements/acq4-torch*`; treat those environment files as the source of truth when new packages are needed.

## Configuration & Utilities

* Runtime configuration is discovered via the search paths defined in `acq4/__init__.py` (local `config/`, system installs such as `/etc/acq4`, then bundled examples). Mirror the structure in `config/example/` when adding new configs.
* Helper scripts for data inspection and maintenance live in `tools/`; use existing entry points rather than duplicating functionality.

## Project Overview

ACQ4 is a platform for neurophysiology acquisition and analysis, focusing on patch clamp electrophysiology, optogenetics, and related techniques. It provides tools for data acquisition, management, and analysis with features including:

* Semi- and fully-automated patch clamp electrophysiology
* Automated manipulator control
* Pipette cleaning/reuse and multipatch support
* Resistance-based autopatch
* Photostimulation mapping
* Fluorescent indicator imaging
* 2-photon imaging

## Architecture Overview

### Manager (Core Controller)

The Manager class (`acq4/Manager.py`) serves as the central controller for the application:

* Loads and configures devices
* Manages modules (UI components)
* Handles data management
* Coordinates device interactions
* Provides configuration management
* Controls application lifecycle

### Devices

Devices (`acq4/devices/`) represent hardware abstractions:

* Base class: `Device` in `devices/Device.py`
* Each device implements hardware-specific functionality
* Devices are configured through the Manager
* Task interfaces allow controlled experiment execution
* Resource locking prevents conflicts between modules

### Modules

Modules (`acq4/modules/`) provide user interface components:

* Base class: `Module` in `modules/Module.py`
* Each module offers specific functionality (imaging, patching, etc.)
* Can interact with devices through the Manager
* Can be loaded/unloaded dynamically

### Interface System

The interface system (`acq4/Interfaces.py`) enables component discovery:

* Components advertise capabilities through interfaces
* Interfaces provide standardized APIs
* Components can discover other components by interface

### Data Management

Data management handles experiment data organization:

* Directory structure for organizing data
* File I/O for various data formats
* Metadata storage and retrieval

## Key Utilities and Patterns

### Interface System (`acq4/Interfaces.py`)

Component discovery and capability declaration:

```python
# Register a component:
self.dm.declareInterface(name, ['device'], self)

# Discover components:
if hasattr(obj, 'implements') and obj.implements('my_api'):
    # Safe to use API methods
```

### DataManager (`acq4/util/DataManager/`)

Handle-based file/directory access (thread-safe):

```python
from acq4.util.DataManager import getManager, getDirHandle
dm = getManager()
dirHandle = dm.getDirHandle('/path/to/data')
fileHandle = dirHandle['filename.ext']
data = fileHandle.read()
dirHandle.writeFile(data, 'output.ma')
```

### Resource Locking (`acq4/util/Mutex.py`)

Prevent device conflicts using mutex locks:

```python
# Recommended context manager pattern:
with device.reserved():
    device.doSomething()

# Multiple device reservation:
manager.reserveDevices(['dev1', 'dev2'], block=True, timeout=20)
```

### Manager Access

```python
from acq4.Manager import getManager
manager = getManager()  # Get current manager singleton
# or often instances will keep a reference at `self.dm`
```

## Task Execution Patterns

Tasks coordinate multi-device operations:

```python
# Task creation:
task = manager.createTask(cmd)
task.execute()          # Run all device tasks
result = task.getResult()
```

Dependency management relies on `getConfigOrder()` and `getStartOrder()` to declare task sequencing.

## Data Formats and I/O

### MetaArray (Primary Data Format)

```python
from MetaArray import MetaArray as MA

# Create with metadata:
data = MA(array_data, info=[
    {'name': 'Time', 'units': 's', 'values': time_array},
    {'name': 'Channel', 'values': ['Voltage', 'Current']},
])

# Access with named indexing:
voltage = data['Channel', 'Voltage']
```

### File Type System

Custom file handlers in `acq4/filetypes/`:

* Each FileType declares `extensions`, `dataTypes`, and `priority`
* Implements `read(fileHandle)` and `write(data, dirHandle, fileName)`
* The system automatically selects appropriate handlers based on priority

## Logging

acq4 uses JSON-formatted logging:

```python
from acq4.logging_config import get_logger

logger = get_logger(__name__)
logger.info("Operation started", extra={'device': 'Camera1'})
```

Logs stream to JSON for structured analysis. The GUI log window supports real-time monitoring. Module loggers follow the pattern `acq4.device.ModuleName.DeviceName`.

## Common Development Tasks

When working with this codebase:

1. Follow existing patterns for adding new devices or modules.
2. Use the Interface system for component discovery.
3. For UI work, check existing modules for patterns and conventions.
4. Use device locking when extended operations require continuous hardware control.
5. Keep heavy processing off the Qt GUI thread; otherwise call `Qt.QApplication.processEvents()` in long loops.
6. Access files through DataManager handles, not direct file operations.
7. Use unit constants in configs and calculations; store values internally in unscaled SI units.
8. DeviceTask lifecycle: configure → start → isDone → getResult.

## Launch Options

```bash
python -m acq4                      # Normal mode
python -m acq4 -x                  # Exit on error (recommended)
python -m acq4 -c /path/to/config  # Custom config file
python -m acq4 --profile           # cProfile profiling
python -m acq4 --callgraph         # Callgraph profiling
python -m acq4 --teleprox 9999     # Remote RPC debugging
```
