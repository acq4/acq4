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

- **Python**: Use the interpreter specified in local configuration (see `AGENTS.local.md`) and format with `black -S -l 100` (language guidelines).
- UI and acquisition stacks are Qt-heavy with lots of scientific/ML dependencies
- **Qt Framework**: ACQ4 uses PyQtGraph for GUI. Import Qt from unified wrapper: `from acq4.util.Qt import ...` for cross-backend compatibility.
- Requirements are stored in `tools/requirements/acq4-torch*`; keep those environment files as the source of truth when new packages are needed.
- **Source Control**: use concise Conventional Commit messages written in present-tense imperative. Avoid destructive git commands; prefer safe alternatives like `git revert`, backup branches, and `git push --force-with-lease` when absolutely necessary (source-control guidelines).

## Configuration & Utilities

- Runtime configuration is discovered via the search paths defined in `acq4/__init__.py` (local `config/`, system installs such as `/etc/acq4`, then bundled examples). Mirror the structure in `config/example/` when adding new configs.
- Helper scripts for data inspection and maintenance live in `tools/`; respect the existing entry points rather than duplicating functionality.

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
- Variable names use **camelCase** in any class/context that touches Qt, **snake_case** otherwise
- Documentation uses numpy docstring format
- Pull requests should be made against the `main` branch
- All values stored internally in **unscaled SI units** (meters, seconds, volts, amperes)
- Use unit constants from `acq4.util.functions` for readable scales in config and code (e.g., `470*nm`, `100*um/s`)
- All code files should start with a 2-line comment/docstring explaining the file's purpose

## Configuration System

ACQ4 uses PyQTGraph's configfile module for parsing configurations:

- **Format**: YAML-like with Python expression evaluation
- **Unit expressions**: Config values can use unit constants (e.g., `wavelength: 470*nm`, `speed: 100*um/s`)
- **Available in expressions**: `hostname`, `username`, `environ`, and all unit constants from `pyqtgraph.units`
- **Device configs**: Stored in `config/devices/DeviceName_config/` directories
  - Access via `Device.readConfigFile(filename)`, `Device.writeConfigFile(data, filename)`
  - Contains calibrations, stored positions, reference frames

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

**Dependency management**: Use `getConfigOrder()` and `getStartOrder()` to declare task dependencies.

## Data Formats and I/O

### MetaArray (Primary Data Format)

Labeled multi-dimensional arrays stored in `.ma` files:

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
- Each FileType declares `extensions`, `dataTypes`, and `priority`
- Implements `read(fileHandle)` and `write(data, dirHandle, fileName)`
- System automatically selects appropriate handler based on priority

## Logging

ACQ4 uses JSON-formatted logging:

```python
from acq4.logging_config import get_logger

logger = get_logger(__name__)
logger.info("Operation started", extra={'device': 'Camera1'})
```

- Logs written to JSON file for structured analysis
- GUI log window available for real-time monitoring
- Module-specific loggers follow pattern: `acq4.device.ModuleName.DeviceName`

## Common Development Tasks

When working with this codebase:

1. Follow existing patterns for adding new devices or modules
2. Use the Interface system for component discovery
3. For UI work, check existing modules for patterns and conventions
4. Use device locking when extended operations require continuous guaranteed hardware control 
5. Be careful with the Qt gui thread. Keep as much processing in bg threads as possible and otherwise use `Qt.QApplication.processEvents()` in long loops
6. Access files through DataManager handles, not direct file operations
7. Use unit constants in configs and calculations, store values in unscaled SI units internally
8. DeviceTask lifecycle: configure → start → isDone → getResult

### Launch Options

```bash
python -m acq4                      # Normal mode
python -m acq4 -x                  # Exit on error (recommended)
python -m acq4 -c /path/to/config  # Custom config file
python -m acq4 --profile           # cProfile profiling
python -m acq4 --callgraph         # Callgraph profiling
python -m acq4 --teleprox 9999     # Remote RPC debugging
```

## Documentation

- Documentation is generated with Sphinx
- Online documentation: https://acq4.readthedocs.io/en/latest
- Source files in `doc/source/` and inline docstrings
