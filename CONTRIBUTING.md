# Contributing to acq4

Contributions to acq4 are welcome! This document collects shared expectations for humans and robots
alike — workflow, testing, and technical context. Robot-specific notes live in `AGENTS.md`.

## Submitting Code Changes

* The preferred method for submitting changes is by github pull request against the "main" branch.
* Pull requests should include only a focused and related set of changes. Mixed features and
  unrelated changes are more likely to be rejected.
* For major changes, it is recommended to discuss your plans on the mailing list or in a github
  issue before putting in too much effort.
* Many changes (especially new devices and user interface modules) can be implemented as an
  extension module rather than modifying the acq4 codebase; this can be a faster way to make your
  code available to the world.
* Separate style-only changes (e.g., reformatting) from functional changes to make review easier.

## Documentation

* Update documentation alongside behavior changes and confirm that Sphinx builds remain healthy.
* Use the numpy docstring format for API documentation.
* Inline docstrings and `doc/source/` are the sources of truth for reference material.

## Style Guidelines

* acq4 prefers PEP8 and numpy for most style issues, balancing readability with practicality.
* Qt-adjacent names should use camelCase rather than snake_case for consistency.
* Automate python formatting with `black -S -l 100`

## Developer Documentation

For detailed information on development setup, architecture, utilities, and common development tasks,
please refer to the [Developer's Guide](doc/source/devGuide/index.rst):

* **[Getting Started](doc/source/devGuide/gettingStarted.rst)** - Development environment setup, running tests
* **[Internal Structure](doc/source/devGuide/internalStructure.rst)** - Architecture overview of Manager, Devices, Modules, and Interfaces
* **[Utilities](doc/source/devGuide/utilities.rst)** - Key utilities, patterns, data formats, and common development tasks
* **[Conventions](doc/source/devGuide/conventions.rst)** - Coding conventions and logging practices
