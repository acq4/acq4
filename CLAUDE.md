# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
python -m acq4
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
- Pull requests should be made against the "main" branch
- All values should be in unscaled SI units. Use the `acq4.util.units` module for more readable scales. 

## Common Development Tasks

When working with this codebase:

1. Follow existing patterns for adding new devices or modules
2. Use the Interface system for component discovery
3. For UI work, check existing modules for patterns and conventions
4. Be careful with device resource locking and release
5. Be careful with threads and Qt event loops

## Documentation

Documentation is generated with Sphinx:
- Online documentation: https://acq4.readthedocs.io/
- Source files in `doc/source/`

## Git Commit Standards
- When committing changes that Claude wrote, include "(claude)" in an explicit --author
- Use the standard commit message format:
```
<type>: <description>

<optional detailed explanation>

🤖 Generated with [Claude Code](https://claude.ai/code)
```
- Commit types: feat, fix, docs, style, refactor, perf, test, chore
