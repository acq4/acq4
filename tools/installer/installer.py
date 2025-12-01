#!/usr/bin/env python3
"""Interactive installer wizard for ACQ4."""
from __future__ import annotations

import argparse
import dataclasses
import functools
import os
import queue
import re
import shutil
import shlex
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any, Callable, Dict, Iterable, List, Optional, Tuple, cast
from urllib.error import URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen

from PyQt6 import QtCore, QtGui, QtWidgets

try:
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover - fallback for Python < 3.11
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:  # pragma: no cover - last resort
        tomllib = None  # type: ignore[assignment]


ARG_INSTALL_PATH = "--install-path"
ARG_BRANCH = "--branch"
ARG_REPO_URL = "--repo-url"
ARG_OPTIONAL_MODE = "--optional-mode"
ARG_OPTIONAL_DEP = "--optional-dep"
ARG_OPTIONAL_GROUPS = "--optional-groups"
ARG_EDITABLE_CLONE = "--editable-clone"
ARG_CONFIG_REPO = "--config-repo"
ARG_CONFIG_BRANCH = "--config-branch"
ARG_CONFIG_PATH = "--config-path"
ARG_CONFIG_FILE = "--config-file"
ARG_GITHUB_TOKEN = "--github-token"

RAW_GITHUB_BASE = "https://raw.githubusercontent.com/acq4/acq4/main/"
ACQ4_REPO_URL = "https://github.com/acq4/acq4"
DEFAULT_BRANCH = "main"
DEFAULT_INSTALL_DIR_NAME = "acq4"
WINDOWS_SHORTCUT_NAME = "ACQ4.lnk"
CONDA_ENV_DIRNAME = "conda_env"
DEPENDENCIES_DIRNAME = "dependencies"
CONFIG_DIRNAME = "config"
ACQ4_SOURCE_DIRNAME = "acq4"
DEFAULT_PYTHON_VERSION = "python=3.12"
DEFAULT_CONDA_PACKAGES = ["pip"]
LINUX_BOOTSTRAP_URL = RAW_GITHUB_BASE + "tools/installer/install_linux.sh"
WINDOWS_BOOTSTRAP_URL = RAW_GITHUB_BASE + "tools/installer/install_windows.bat"

START_BAT_TEMPLATE = r"""@echo off
REM ACQ4 Launcher
REM This script activates the ACQ4 conda environment and starts ACQ4

call "{conda_activate_bat}" "{env_path}"
if errorlevel 1 (
    echo Failed to activate conda environment: {env_path}
    pause
    exit /b 1
)

cd "{acq4_path}"
python -m acq4 -x -c "{config_file_path}"
pause
"""

DEPENDENCY_METADATA: Dict[str, Dict[str, Dict[str, str]]] = {
    "groups": {
        "hardware": {
            "title": "Hardware Control / Data Acquisition",
            "description": "Drivers and APIs for supported microscopes and controllers.",
        },
        "lab": {
            "title": "Lab Utilities",
            "description": "Institution-specific analysis helpers and forks.",
        },
        "analysis": {
            "title": "Data Analysis",
            "description": "Packages for data analysis and visualization.",
        },
        "ml-models": {
            "title": "Machine Learning Framework and Models (warning: large downloads)",
            "description": "Packages for machine learning-based analysis.",
        },
        "docs": {
            "title": "Documentation",
            "description": "Packages required to build ACQ4 documentation.",
        },
        "testing": {
            "title": "Testing",
            "description": "Packages required for running ACQ4 test suite.",
        },
        "dev": {
            "title": "Development",
            "description": "Packages useful for ACQ4 development.",
        },
    },
    "packages": {
        "cupy": {
            "display_name": "CuPy",
            "pypi_package": "cupy",
            "description": "GPU acceleration for imaging workloads.",
            "post_install_doc": "Requires NVIDIA CUDA Toolkit. Download from <a href='https://developer.nvidia.com/cuda-downloads'>https://developer.nvidia.com/cuda-downloads</a>",
        },
        "pydaqmx": {
            "display_name": "PyDAQmx",
            "pypi_package": "PyDAQmx",
            "description": "National Instruments DAQ interface.",
            "post_install_doc": "Requires NI-DAQmx drivers. Download from <a href='https://www.ni.com/en-us/support/downloads/drivers/download.ni-daqmx.html'>National Instruments website</a>",
        },
        "pymmcore": {
            "display_name": "PyMMCore",
            "pypi_package": "pymmcore",
            "description": "Micro-Manager device bridge.",
            "post_install_doc": "Requires Micro-Manager installation. Download from <a href='https://micro-manager.org/Micro-Manager_Nightly_Builds'>Micro-Manager Nightly Builds</a>",
        },
        "sensapex-py": {
            "display_name": "sensapex-py",
            "pypi_package": "sensapex",
            "git_url": "https://github.com/acq4/sensapex-py.git",
            "description": "Sensapex manipulator control.",
        },
        "pytic": {
            "display_name": "pytic",
            "pypi_package": "pytic",
            "git_url": "https://github.com/AllenInstitute/pytic.git",
            "description": "TIC motor control",
        },
        "falconoptics": {
            "display_name": "falconoptics",
            "pypi_package": "falconoptics",
            "git_url": "https://github.com/AllenInstitute/falconoptics.git",
            "description": "Falcon optics motor turret.",
        },
        "cellpose": {
            "display_name": "cellpose (ACQ4 fork)",
            "pypi_package": "cellpose",
            "git_url": "https://github.com/outofculture/cellpose.git",
            "description": "Cell segmentation and analysis utilities.",
        },
        "coorx": {
            "display_name": "coorx",
            "pypi_package": "coorx",
            "git_url": "https://github.com/campagnola/coorx.git",
            "description": "Coordinate transformation helpers.",
        },
        "neuroanalysis": {
            "display_name": "neuroanalysis",
            "pypi_package": "neuroanalysis",
            "git_url": "https://github.com/AllenInstitute/neuroanalysis.git",
            "description": "Neurophysiology analysis tools.",
        },
        "pyqtgraph": {
            "display_name": "pyqtgraph (ACQ4)",
            "pypi_package": "pyqtgraph",
            "git_url": "https://github.com/acq4/pyqtgraph.git",
            "description": "ACQ4-maintained pyqtgraph fork.",
        },
        "teleprox": {
            "display_name": "teleprox",
            "pypi_package": "teleprox",
            "git_url": "https://github.com/campagnola/teleprox.git",
            "description": "Remote procedure call utilities.",
        },
        "numpydoc>=1.1.0": {
            "display_name": "numpydoc",
            "pypi_package": "numpydoc",
            "description": "Sphinx extension for NumPy-style docs.",
        },
        "Sphinx>=4.1.2": {
            "display_name": "Sphinx",
            "pypi_package": "Sphinx",
            "description": "Documentation builder.",
        },
        "sphinx-rtd-theme>=0.5.2": {
            "display_name": "sphinx-rtd-theme",
            "pypi_package": "sphinx-rtd-theme",
            "description": "Read the Docs theme for Sphinx.",
        },
        "acq4_automation": {
            "display_name": "acq4_automation",
            "git_url": "https://github.com/AllenInstitute/acq4-automation.git",
            "description": "Allen Institute automation helpers for patch clamp.",
        },
    },
}

def _group_meta(key: str) -> Dict[str, str]:
    return DEPENDENCY_METADATA.get("groups", {}).get(key, {})


def _package_meta(spec: str) -> Dict[str, str]:
    packages = DEPENDENCY_METADATA.get("packages", {})
    if spec in packages:
        return packages[spec]
    normalized = normalize_spec_name(spec)
    for candidate_pkg_name, meta in packages.items():
        if normalize_spec_name(candidate_pkg_name) == normalized:
            return meta
    return {}


def _format_with_description(title: str, description: str) -> str:
    return f"{title} — {description}" if description else title


def github_url_with_token(url: str, token: Optional[str]) -> str:
    """Return a GitHub HTTPS URL with the provided token injected as userinfo."""
    if not token:
        return url
    token = token.strip()
    if not token:
        return url
    try:
        parsed = urlsplit(url)
    except ValueError:
        return url
    hostname = parsed.hostname or ""
    if "github.com" not in hostname.lower():
        return url
    scheme = parsed.scheme or "https"
    if scheme.lower() not in {"http", "https"}:
        return url
    if parsed.username:
        # Assume caller already embedded credentials.
        return url
    host = hostname
    if parsed.port:
        host = f"{host}:{parsed.port}"
    netloc = f"{token}@{host}"
    return urlunsplit((scheme, netloc, parsed.path or "", parsed.query, parsed.fragment))


_PYPROJECT_DATA_CACHE: Optional[Dict[str, Any]] = None
_DEPENDENCY_GROUPS_CACHE: Optional[List["DependencyGroup"]] = None
_EDITABLE_DEPENDENCIES_CACHE: Optional[Dict[str, EditableDependency]] = None
_PROJECT_DEPENDENCIES_CACHE: Optional[List[str]] = None
TRISTATE_FLAG = (
    getattr(QtCore.Qt.ItemFlag, "ItemIsTristate", None)
    or getattr(QtCore.Qt.ItemFlag, "ItemIsTriState", None)
    or getattr(QtCore.Qt.ItemFlag, "ItemIsAutoTristate", None)
)


def qt_key(name: str) -> int:
    """Return a Qt key value compatible with both Qt5 and Qt6 enums."""
    key_enum = getattr(QtCore.Qt, "Key", None)
    if key_enum is not None and hasattr(key_enum, name):
        return getattr(key_enum, name)
    try:
        return getattr(QtCore.Qt, name)
    except AttributeError as exc:  # pragma: no cover - depends on Qt bindings
        raise AttributeError(f"Qt key {name} not available") from exc


class InstallerError(RuntimeError):
    """Raised when installation fails."""


class InstallerCancelled(InstallerError):
    """Raised when the user cancels installation."""


def repo_root() -> Path:
    """Return the repository root directory when running from a cloned repo.

    Returns
    -------
    Path
        Path to the repository root (two directories up from this script).
    """
    return Path(__file__).resolve().parents[2]


def fetch_pyproject_from_github(repo_url: str, branch: str) -> Tuple[str, bool]:
    """Download pyproject.toml content from a GitHub repository.

    Parameters
    ----------
    repo_url : str
        GitHub repository URL (e.g., "https://github.com/acq4/acq4").
    branch : str
        Branch or tag name to fetch from.

    Returns
    -------
    tuple of (str, bool)
        A tuple containing:
        - The pyproject.toml file content as a string
        - A boolean indicating whether fallback to acq4/acq4:main was used

    Raises
    ------
    InstallerError
        If the download fails or the file cannot be found, even after
        falling back to the main ACQ4 repository.
    """
    parts = urlsplit(repo_url)
    if parts.netloc not in {"github.com", "www.github.com"}:
        raise InstallerError(f"Only GitHub URLs are supported for fetching pyproject.toml: {repo_url}")

    path_components = parts.path.strip("/").split("/")
    if len(path_components) < 2:
        raise InstallerError(f"Invalid GitHub repository URL: {repo_url}")

    owner, repo_name = path_components[0], path_components[1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]

    raw_url = f"https://raw.githubusercontent.com/{owner}/{repo_name}/{branch}/pyproject.toml"

    try:
        with urlopen(raw_url, timeout=10) as response:
            content = response.read().decode("utf-8")
            return content, False
    except URLError as exc:
        # If the fetch fails and we're not already looking at the main ACQ4 repo,
        # fall back to fetching from github.com/acq4/acq4:main
        is_main_acq4 = (owner.lower() == "acq4" and repo_name.lower() == "acq4" and branch.lower() == "main")
        if not is_main_acq4:
            fallback_url = f"https://raw.githubusercontent.com/acq4/acq4/main/pyproject.toml"
            try:
                with urlopen(fallback_url, timeout=10) as response:
                    content = response.read().decode("utf-8")
                    return content, True
            except URLError:
                # Fallback also failed, raise the original error
                pass
        raise InstallerError(f"Failed to download pyproject.toml from {raw_url}: {exc}") from exc


def load_pyproject_data(content: Optional[str] = None, repo_path: Optional[Path] = None) -> Dict[str, Any]:
    """Parse pyproject.toml and return its contents.

    Parameters
    ----------
    content : str, optional
        The pyproject.toml content as a string. If provided, this is parsed directly.
    repo_path : Path, optional
        Path to the repository root directory. If provided, pyproject.toml is read from
        this location. Ignored if content is provided.

    Returns
    -------
    dict
        Parsed pyproject.toml data.

    Raises
    ------
    InstallerError
        If pyproject.toml cannot be found or parsed.
    """
    global _PYPROJECT_DATA_CACHE

    if tomllib is None:  # pragma: no cover - environment-specific
        raise InstallerError(
            "Parsing pyproject.toml requires Python 3.11+ or the 'tomli' package to be installed.")

    if content is not None:
        try:
            data = tomllib.loads(content)
            return data
        except Exception as exc:  # noqa: BLE001
            raise InstallerError(f"Failed to parse pyproject.toml: {exc}") from exc

    if repo_path is not None:
        path = repo_path / "pyproject.toml"
    else:
        if _PYPROJECT_DATA_CACHE is not None:
            return _PYPROJECT_DATA_CACHE
        path = repo_root() / "pyproject.toml"

    if not path.exists():
        raise InstallerError(f"pyproject.toml not found at {path}")

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise InstallerError(f"Failed to parse pyproject.toml: {exc}") from exc

    if repo_path is None and content is None:
        _PYPROJECT_DATA_CACHE = data

    return data


def _format_group_title(name: str) -> str:
    label = name.replace("_", " ").strip()
    if not label:
        return "Extras"
    return label[0].upper() + label[1:]


def dependency_groups_from_pyproject(content: Optional[str] = None,
                                     repo_path: Optional[Path] = None) -> List[DependencyGroup]:
    """Return dependency groups (extras) defined in pyproject.toml.

    Parameters
    ----------
    content : str, optional
        The pyproject.toml content as a string. If provided, parses this directly.
    repo_path : Path, optional
        Path to the repository root. If provided, reads pyproject.toml from this location.
        Ignored if content is provided.

    Returns
    -------
    list of DependencyGroup
        Dependency groups extracted from pyproject.toml.
    """
    global _DEPENDENCY_GROUPS_CACHE
    if content is None and repo_path is None and _DEPENDENCY_GROUPS_CACHE is not None:
        return _DEPENDENCY_GROUPS_CACHE

    data = load_pyproject_data(content=content, repo_path=repo_path)
    project = data.get("project") or {}
    optional = project.get("optional-dependencies") or {}
    groups: List[DependencyGroup] = []
    for key, packages in optional.items():
        pkg_list = list(packages or [])
        meta = _group_meta(key)
        title = meta.get("title") or _format_group_title(key)
        description = meta.get("description", "")
        groups.append(DependencyGroup(key=key, title=title, packages=pkg_list,
                                      optional=True, description=description))

    if content is None and repo_path is None:
        _DEPENDENCY_GROUPS_CACHE = groups

    return groups


def project_dependencies(repo_path: Optional[Path] = None) -> List[str]:
    """Return core dependencies defined in pyproject.toml.

    Parameters
    ----------
    repo_path : Path, optional
        Path to the repository root. If provided, reads pyproject.toml from this location.

    Returns
    -------
    list of str
        Core dependency specs from pyproject.toml.
    """
    global _PROJECT_DEPENDENCIES_CACHE
    if repo_path is None and _PROJECT_DEPENDENCIES_CACHE is not None:
        return _PROJECT_DEPENDENCIES_CACHE

    data = load_pyproject_data(repo_path=repo_path)
    project = data.get("project") or {}
    deps = project.get("dependencies") or []

    if repo_path is None:
        _PROJECT_DEPENDENCIES_CACHE = list(deps)

    return list(deps)


def editable_dependencies() -> Dict[str, EditableDependency]:
    global _EDITABLE_DEPENDENCIES_CACHE
    if _EDITABLE_DEPENDENCIES_CACHE is None:
        _EDITABLE_DEPENDENCIES_CACHE = _build_editable_dependency_map()
    return _EDITABLE_DEPENDENCIES_CACHE


def _build_editable_dependency_map() -> Dict[str, EditableDependency]:
    packages = DEPENDENCY_METADATA.get("packages", {})
    result: Dict[str, EditableDependency] = {}
    for pkg_name, meta in packages.items():
        git_url = meta.get("git_url")
        if not git_url:
            continue
        title = meta.get("display_name") or pkg_name
        description = meta.get("description", "")
        key_source = meta.get("pypi_package") or title or pkg_name
        key = normalize_spec_name(key_source)
        alias_values = {key_source, pkg_name, title}
        aliases = {normalize_spec_name(value) for value in alias_values if value}
        result[key] = EditableDependency(
            key=key,
            spec=pkg_name,
            git_url=git_url,
            display_name=title,
            description=description,
            aliases=aliases or {key},
        )
    return result


@dataclass
class DependencyOption:
    spec: str
    description: str
    source_label: str
    group: str = ""
    display_name: str = ""
    normalized_name: str = field(init=False)
    cli_name: str = ""
    aliases: set[str] = field(default_factory=set)
    post_install_doc: str = ""

    def __post_init__(self) -> None:
        self.normalized_name = normalize_spec_name(self.spec)
        cli_normalized = normalize_spec_name(self.cli_name or self.spec)
        normalized_aliases = {self.normalized_name, cli_normalized}
        for alias in self.aliases:
            normalized_aliases.add(normalize_spec_name(alias))
        self.cli_name = cli_normalized
        self.aliases = normalized_aliases


@dataclass
class DependencyGroup:
    key: str
    title: str
    packages: List[str]
    optional: bool = True
    description: str = ""


@dataclass
class EditableDependency:
    key: str
    spec: str
    git_url: str
    display_name: str
    description: str = ""
    aliases: set[str] = field(default_factory=set)


@dataclass
class InstallerState:
    install_path: Path
    branch: str
    repo_url: str
    github_token: Optional[str] = None
    optional_dependencies: List[DependencyOption] = field(default_factory=list)
    selected_optional: List[str] = field(default_factory=list)
    editable_selection: List[str] = field(default_factory=list)
    config_mode: str = "new"
    config_repo_url: Optional[str] = None
    config_repo_branch: Optional[str] = None
    config_copy_path: Optional[Path] = None
    config_file: Optional[str] = None
    create_desktop_shortcut: bool = True


@dataclass
class InstallerLogEvent:
    kind: str
    data: Dict[str, Any] = field(default_factory=dict)


class StructuredLogger:
    def __init__(self, text_fn: Optional[Callable[[str], None]] = None,
                 event_handler: Optional[Callable[[InstallerLogEvent], None]] = None) -> None:
        self.text_fn = text_fn
        self.event_handler = event_handler
        self._task_counter = 0
        self._command_counter = 0
        self._progress_total = 0
        self._progress_value = 0

    def _emit(self, kind: str, **data: Any) -> None:
        if self.event_handler is None:
            return
        self.event_handler(InstallerLogEvent(kind=kind, data=data))

    def set_task_total(self, total: int) -> None:
        self._progress_total = max(0, total)
        self._progress_value = 0
        self._emit("progress", total=self._progress_total, value=self._progress_value)

    def message(self, text: str, task_id: Optional[int] = None, *, broadcast: bool = True) -> None:
        if self.text_fn is not None:
            self.text_fn(text)
        if broadcast:
            self._emit("message", text=text, task_id=task_id)

    def start_task(self, title: str) -> int:
        self._task_counter += 1
        task_id = self._task_counter
        if self.text_fn is not None:
            self.text_fn(f"\n=== {title} ===")
        self._emit("task-start", task_id=task_id, title=title)
        return task_id

    def finish_task(self, task_id: int, success: bool = True) -> None:
        if self.text_fn is not None:
            status = "✓ Completed" if success else "✗ Failed"
            self.text_fn(f"{status}\n")
        self._emit("task-complete", task_id=task_id, success=success)
        self._progress_value = min(self._progress_value + 1, self._progress_total)
        self._emit("progress", total=self._progress_total, value=self._progress_value)

    def start_command(self, task_id: Optional[int], display_cmd: str) -> int:
        self._command_counter += 1
        command_id = self._command_counter
        if self.text_fn is not None:
            self.text_fn(f"$ {display_cmd}")
        self._emit("command-start", command_id=command_id, task_id=task_id, text=display_cmd)
        return command_id

    def command_output(self, command_id: Optional[int], text: str) -> None:
        if self.text_fn is not None:
            self.text_fn(text)
        if command_id is None:
            return
        self._emit("command-output", command_id=command_id, text=text)

    def finish_command(self, command_id: Optional[int], success: bool) -> None:
        if command_id is None:
            return
        if self.text_fn is not None and not success:
            self.text_fn("Command failed")
        self._emit("command-complete", command_id=command_id, success=success)

def normalize_spec_name(spec: str) -> str:
    """Normalize a dependency specifier to a simple, comparable name.

    Parameters
    ----------
    spec : str
        Original dependency specification, possibly including extras,
        version constraints, or VCS URLs.

    Returns
    -------
    str
        Lower-case identifier that can be used for deduping selections.
    """
    value = spec.strip()
    # Handle PEP 508 direct references (e.g., "package @ git+https://...")
    if " @ " in value:
        value = value.split(" @ ")[0]
    elif "#egg=" in value:
        value = value.split("#egg=")[-1]
    elif value.startswith("git+"):
        tail = value.split("/")[-1]
        tail = tail.split("@")[0]
        if tail.endswith(".git"):
            tail = tail[:-4]
        value = tail
    if any(sep in value for sep in ("==", ">=", "<=", "!=", "~~")):
        for sep in ("==", ">=", "<=", "!=", "~~"):
            if sep in value:
                value = value.split(sep)[0]
                break
    if "[" in value:
        value = value.split("[")[0]
    return value.strip().lower()


def parse_optional_dependencies(content: Optional[str] = None,
                                repo_path: Optional[Path] = None) -> List[DependencyOption]:
    """Return optional dependency entries defined via pyproject extras.

    Parameters
    ----------
    content : str, optional
        The pyproject.toml content as a string. If provided, parses this directly.
    repo_path : Path, optional
        Path to the repository root. If provided, reads pyproject.toml from this location.

    Returns
    -------
    list of DependencyOption
        Optional dependency descriptors extracted from pyproject.toml.
    """
    options: List[DependencyOption] = []
    for group in dependency_groups_from_pyproject(content=content, repo_path=repo_path):
        for spec in group.packages:
            spec_value = spec.strip()
            if not spec_value:
                continue
            pkg_meta = _package_meta(spec_value)
            display_name = pkg_meta.get("display_name") or spec_value
            description = pkg_meta.get("description", "")
            package_name = pkg_meta.get("pypi_package")
            cli_source = package_name or display_name or spec_value
            alias_values = {package_name, display_name}
            post_install_doc = pkg_meta.get("post_install_doc", "")
            options.append(
                DependencyOption(
                    spec=spec_value,
                    description=description,
                    source_label=group.key,
                    group=group.key,
                    display_name=display_name,
                    cli_name=cli_source,
                    aliases={value for value in alias_values if value},
                    post_install_doc=post_install_doc,
                )
            )
    return options


def _parse_cli_list(raw_value: Optional[str]) -> List[str]:
    if raw_value is None:
        return []
    parts = [part.strip() for part in raw_value.split(",")]
    return [part for part in parts if part]


def _optional_alias_lookup(options: Iterable[DependencyOption]) -> Dict[str, DependencyOption]:
    lookup: Dict[str, DependencyOption] = {}
    for dep in options:
        for alias in dep.aliases:
            lookup[alias] = dep
    return lookup


def _editable_alias_lookup(editable_map: Dict[str, EditableDependency]) -> Dict[str, EditableDependency]:
    lookup: Dict[str, EditableDependency] = {}
    for editable in editable_map.values():
        for alias in editable.aliases:
            lookup[alias] = editable
    return lookup


def _group_alias_lookup(groups: Iterable[DependencyGroup]) -> Dict[str, DependencyGroup]:
    lookup: Dict[str, DependencyGroup] = {}
    for group in groups:
        aliases = {group.key, group.title}
        for alias in aliases:
            if not alias:
                continue
            lookup[normalize_spec_name(alias)] = group
    return lookup


def resolve_optional_selection_from_args(args: argparse.Namespace,
                                         options: List[DependencyOption],
                                         groups: List[DependencyGroup]) -> List[str]:
    """Determine which optional dependencies should be installed.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments containing optional selection flags.
    options : list of DependencyOption
        Available optional dependency descriptors.
    groups : list of DependencyGroup
        Optional dependency groups used for --optional-groups resolution.

    Returns
    -------
    list of str
        The dependency specs to install.
    """
    mode = args.optional_mode
    raw_optional_arg = args.optional_dep
    raw_group_arg = args.optional_groups
    requested_names = _parse_cli_list(raw_optional_arg)
    requested_groups = _parse_cli_list(raw_group_arg)
    provided_optional_arg = (raw_optional_arg is not None) or (raw_group_arg is not None)
    if mode is None:
        mode = "list" if provided_optional_arg else "all"
    if mode not in {"all", "none", "list"}:
        raise InstallerError(f"Invalid optional selection mode: {mode}")
    if mode == "all":
        return [dep.spec for dep in options]
    if mode == "none":
        return []
    if not provided_optional_arg:
        raise InstallerError("Optional selection mode 'list' requires --optional-dep or --optional-groups.")
    if not requested_names and not requested_groups:
        return []
    alias_lookup = _optional_alias_lookup(options)
    group_lookup = _group_alias_lookup(groups)
    resolved: List[str] = []
    for name in requested_names:
        normalized = normalize_spec_name(name)
        dep = alias_lookup.get(normalized)
        if dep is None:
            raise InstallerError(f"Unknown optional dependency: {name}")
        if dep.spec not in resolved:
            resolved.append(dep.spec)
    for group_name in requested_groups:
        normalized = normalize_spec_name(group_name)
        group = group_lookup.get(normalized)
        if group is None:
            raise InstallerError(f"Unknown optional group: {group_name}")
        for spec in group.packages:
            spec_value = spec.strip()
            if spec_value and spec_value not in resolved:
                resolved.append(spec_value)
    return resolved


def resolve_editable_selection_from_args(args: argparse.Namespace,
                                         editable_map: Dict[str, EditableDependency]) -> List[str]:
    """Return editable dependency keys selected via CLI arguments."""
    raw_value = args.editable_clone
    names = _parse_cli_list(raw_value)
    if not names:
        return []
    alias_lookup = _editable_alias_lookup(editable_map)
    resolved: List[str] = []
    for name in names:
        normalized = normalize_spec_name(name)
        editable = alias_lookup.get(normalized)
        if editable is None:
            raise InstallerError(f"Unknown editable dependency: {name}")
        if editable.key not in resolved:
            resolved.append(editable.key)
    return resolved


def quote_windows_arguments(args: List[str]) -> str:
    """Quote a sequence of CLI arguments for Windows ``cmd.exe`` usage."""
    if not args:
        return ""
    return subprocess.list2cmdline(args)


def create_start_bat(base_dir: Path, conda_exe: str, env_path: Path, config_file_path: Path) -> Path:
    """Create a start_acq4.bat file in the base install directory.

    Parameters
    ----------
    base_dir : Path
        The base installation directory.
    conda_exe : str
        Path to the conda executable.
    env_path : Path
        Path to the conda environment.
    config_file_path : Path
        Path to the ACQ4 configuration file.

    Returns
    -------
    Path
        Path to the created bat file.
    """
    # Derive activate.bat path from conda.exe path
    # conda_exe is typically: C:\...\Scripts\conda.exe
    # activate.bat is at: C:\...\Scripts\activate.bat
    conda_path = Path(conda_exe)
    conda_activate_bat = conda_path.parent / "activate.bat"

    bat_content = START_BAT_TEMPLATE.format(
        conda_activate_bat=str(conda_activate_bat),
        env_path=str(env_path),
        config_file_path=str(config_file_path),
        acq4_path=str(base_dir / ACQ4_SOURCE_DIRNAME),
    )
    bat_path = base_dir / "start_acq4.bat"
    bat_path.write_text(bat_content, encoding="utf-8")
    return bat_path


def create_desktop_shortcut_windows(bat_path: Path, base_dir: Path) -> None:
    """Create a Windows desktop shortcut pointing to the start bat file.

    Parameters
    ----------
    bat_path : Path
        Path to the start_acq4.bat file.
    base_dir : Path
        The base installation directory (to find the icon).

    Notes
    -----
    This function creates a shortcut to the bat file and attempts to configure
    it to disable Quick Edit mode in the console window. Quick Edit mode can
    cause the console to pause when text is accidentally selected, which is
    undesirable for long-running applications.
    """
    desktop = Path(os.path.expanduser("~")) / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    shortcut_name = f"ACQ4 ({base_dir.name}).lnk"
    shortcut_path = desktop / shortcut_name

    # Try to find the ACQ4 icon
    icon_path = base_dir / ACQ4_SOURCE_DIRNAME / "acq4" / "icons" / "acq4.ico"
    icon_location = str(icon_path) if icon_path.exists() else ""

    # PowerShell script to create shortcut and modify its properties
    # Note: Disabling Quick Edit requires modifying the .lnk file binary directly
    # which is not easily done via WScript.Shell. We create the shortcut here,
    # and users can manually disable Quick Edit by right-clicking the shortcut,
    # selecting Properties > Options > and unchecking "Quick Edit Mode" if needed.
    ps_script = (
        "$ws = New-Object -ComObject WScript.Shell;"
        f"$s = $ws.CreateShortcut('{shortcut_path}');"
        f"$s.TargetPath = '{bat_path}';"
        "$s.Arguments = '';"
        f"$s.WorkingDirectory = '{base_dir}';"
    )

    if icon_location:
        ps_script += f"$s.IconLocation = '{icon_location}';"

    ps_script += "$s.Save();"

    subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], check=True)


def build_unattended_script_content(cli_args: List[str], *, is_windows: bool) -> str:
    """Create a self-contained script that replays the installer selections.

    Parameters
    ----------
    cli_args : list of str
        Arguments that reproduce the wizard selections.
    is_windows : bool
        Whether to emit a Windows ``.bat`` script instead of a POSIX shell script.

    Returns
    -------
    str
        Script contents ready to be written to disk.
    """
    if is_windows:
        bootstrap_call = quote_windows_arguments(["%BOOTSTRAP%", *cli_args])
        return (
            "@echo off\n"
            "setlocal enabledelayedexpansion\n"
            "set \"BOOTSTRAP=%TEMP%\\acq4-bootstrap-%RANDOM%.bat\"\n"
            "echo Downloading ACQ4 bootstrap script...\n"
            f"curl -L -o \"%BOOTSTRAP%\" \"{WINDOWS_BOOTSTRAP_URL}\" || "
            "goto :fail\n"
            f"{bootstrap_call}\n"
            "set \"RESULT=%ERRORLEVEL%\"\n"
            "del \"%BOOTSTRAP%\" >nul 2>&1\n"
            "exit /b %RESULT%\n"
            ":fail\n"
            "echo Failed to download ACQ4 bootstrap script.\n"
            "exit /b 1\n"
        )
    args_line = shlex.join(cli_args) if cli_args else ""
    command_line = '"${SCRIPT_PATH}"'
    if args_line:
        command_line = f'{command_line} {args_line}'
    return (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "SCRIPT_PATH=\"$(mktemp -t acq4-bootstrap-XXXXXX.sh)\"\n"
        "echo \"Downloading ACQ4 bootstrap script...\"\n"
        f"curl -fsSL \"{LINUX_BOOTSTRAP_URL}\" -o \"${{SCRIPT_PATH}}\"\n"
        "chmod +x \"${SCRIPT_PATH}\"\n"
        f"{command_line}\n"
        "RESULT=$?\n"
        "rm -f \"${SCRIPT_PATH}\"\n"
        "exit ${RESULT}\n"
    )


def register_location_cli_arguments(parser: argparse.ArgumentParser) -> None:
    """Add CLI options that control the installation location."""
    parser.add_argument(
        ARG_INSTALL_PATH,
        dest="install_path",
        help="Target directory for the ACQ4 installation.",
    )
    parser.add_argument(
        ARG_REPO_URL,
        dest="repo_url",
        help=f"Git repository URL that will be cloned (default: {ACQ4_REPO_URL}).",
        default=None,
    )
    parser.add_argument(
        ARG_BRANCH,
        dest="branch",
        help="Git tag or branch to install (default: %(default)s).",
        default=None,
    )
    parser.add_argument(
        ARG_GITHUB_TOKEN,
        dest="github_token",
        help="GitHub token to embed in HTTPS clone URLs (use with private repositories).",
        default=None,
    )


def register_dependency_cli_arguments(parser: argparse.ArgumentParser) -> None:
    """Add CLI options for optional dependency selection."""
    parser.add_argument(
        ARG_OPTIONAL_MODE,
        choices=["all", "none", "list"],
        help="Selection mode for optional dependencies (default: all, or list when --optional-dep is provided).",
        default=None,
    )
    parser.add_argument(
        ARG_OPTIONAL_DEP,
        dest="optional_dep",
        help=(
            "Comma-separated list of optional package names to include (matches display/pip names, not specs). "
            "Only used when --optional-mode list; pass an empty string to select none."
        ),
        default=None,
    )
    parser.add_argument(
        ARG_OPTIONAL_GROUPS,
        dest="optional_groups",
        help="Comma-separated list of optional dependency group names/keys to enable.",
        default=None,
    )
    parser.add_argument(
        ARG_EDITABLE_CLONE,
        dest="editable_clone",
        help="Comma-separated list of package names to clone for editable installation.",
        default=None,
    )


def register_config_cli_arguments(parser: argparse.ArgumentParser) -> None:
    """Add CLI options controlling configuration handling.

    Configuration mode is determined automatically:
    - Clone mode: if --config-repo and --config-branch are specified
    - Copy mode: if --config-path is specified
    - New mode: if neither are specified (creates default config)
    """
    parser.add_argument(
        ARG_CONFIG_REPO,
        dest="config_repo",
        help="URL of configuration repository to clone. Requires --config-branch.",
    )
    parser.add_argument(
        ARG_CONFIG_BRANCH,
        dest="config_branch",
        help="Branch to use when cloning configuration repository. Requires --config-repo.",
    )
    parser.add_argument(
        ARG_CONFIG_PATH,
        dest="config_path",
        help="Path to an existing configuration directory to copy. Cannot be used with --config-repo.",
    )
    parser.add_argument(
        ARG_CONFIG_FILE,
        dest="config_file",
        help="Configuration file to use from the cloned/copied config directory.",
    )


def is_git_available() -> bool:
    """Return True if git executable is available on PATH."""
    return shutil.which("git") is not None


class GitPage(QtWidgets.QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Git Is Required")
        layout = QtWidgets.QVBoxLayout(self)
        info = (
            "ACQ4 needs Git to download repositories and manage optional dependencies.\n"
            "You can:\n"
            "  1. Install Git inside the current conda environment (recommended; affects only this installer env).\n"
            "  2. Download and run the official Git installer from git-scm.com.\n"
            "  3. Install Git manually via your system package manager and restart this installer."
        )
        self.message_label = QtWidgets.QLabel(info)
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)
        self.status_label = QtWidgets.QLabel()
        layout.addWidget(self.status_label)
        btn_box = QtWidgets.QHBoxLayout()
        self.install_conda_btn = QtWidgets.QPushButton("Install git in conda env (recommended)")
        self.install_conda_btn.clicked.connect(self._install_git_conda)
        btn_box.addWidget(self.install_conda_btn)
        self.download_installer_btn = QtWidgets.QPushButton("Download installer from git-scm.org")
        self.download_installer_btn.clicked.connect(self._open_download_page)
        btn_box.addWidget(self.download_installer_btn)
        btn_box.addStretch(1)
        layout.addLayout(btn_box)
        self.refresh_button = QtWidgets.QPushButton("Re-check for git")
        self.refresh_button.clicked.connect(self._update_status)
        layout.addWidget(self.refresh_button)
        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setVisible(False)
        layout.addWidget(self.log_view)
        self._update_status()

    def _open_download_page(self) -> None:
        QtGui.QDesktopServices.openUrl(QtCore.QUrl("https://git-scm.com/downloads"))

    def _install_git_conda(self) -> None:
        conda_exe = os.environ.get("CONDA_EXE")
        conda_prefix = os.environ.get("CONDA_PREFIX")
        if not conda_exe or not Path(conda_exe).exists():
            QtWidgets.QMessageBox.warning(
                self, "Conda required",
                "Could not locate CONDA_EXE. Please ensure you launched the installer via the bootstrap script.")
            return
        self.install_conda_btn.setEnabled(False)
        self.log_view.setVisible(True)
        self.log_view.appendPlainText("Installing git via conda...\n")

        def install_git():
            process = subprocess.Popen(
                [conda_exe, "install", "-y", "git"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=os.environ,
                cwd=conda_prefix or None,
            )
            assert process.stdout is not None
            for line in process.stdout:
                QtCore.QMetaObject.invokeMethod(
                    self,
                    "_append_log_line",
                    QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, line.rstrip())
                )
            process.wait()
            QtCore.QMetaObject.invokeMethod(
                self,
                "_git_install_finished",
                QtCore.Qt.ConnectionType.QueuedConnection,
                QtCore.Q_ARG(int, process.returncode)
            )

        install_thread = threading.Thread(target=install_git, daemon=True)
        install_thread.start()

    @QtCore.pyqtSlot(str)
    def _append_log_line(self, line: str) -> None:
        self.log_view.appendPlainText(line)
        self.log_view.ensureCursorVisible()

    @QtCore.pyqtSlot(int)
    def _git_install_finished(self, returncode: int) -> None:
        if returncode == 0:
            self.log_view.appendPlainText("git installation finished.\n")
        else:
            self.log_view.appendPlainText(f"git installation failed (exit {returncode}).\n")
        self.install_conda_btn.setEnabled(True)
        self._update_status()

    def _update_status(self) -> None:
        available = is_git_available()
        if available:
            self.status_label.setText("Git detected on PATH.")
        else:
            self.status_label.setText("Git not found. Install using one of the options above, then re-check.")
        self.completeChanged.emit()

    def isComplete(self) -> bool:  # noqa: N802
        return is_git_available()


class GitRepoWidget(QtWidgets.QWidget):
    """Reusable widget combining a git repository URL input and branch/tag dropdown.

    Fetches branches only when the user presses Enter or focuses off the repo text field,
    avoiding excessive git ls-remote calls while typing.
    """

    repoChanged = QtCore.pyqtSignal(str)
    branchChanged = QtCore.pyqtSignal(str)

    def __init__(self, default_repo: str = "", default_branch: str = DEFAULT_BRANCH,
                 parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._github_token: Optional[str] = None
        self.branch_fetch_thread: Optional[threading.Thread] = None
        self.branch_fetch_cancel = threading.Event()

        layout = QtWidgets.QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.repo_edit = QtWidgets.QLineEdit(default_repo)
        layout.addRow("Repository URL", self.repo_edit)

        self.branch_combo = QtWidgets.QComboBox()
        self.branch_combo.setEditable(True)
        self.branch_combo.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
        self.branch_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.branch_combo.setMinimumContentsLength(20)
        self.branch_combo.setEditText(default_branch)
        layout.addRow("Tag or branch", self.branch_combo)

        self.status_label = QtWidgets.QLabel()
        self.status_label.setWordWrap(True)
        layout.addRow(self.status_label)

        # Clear branches immediately when user starts editing the URL
        self.repo_edit.textChanged.connect(self._clear_branch_choices)
        # Only fetch branches when user presses Enter or focuses off the field
        self.repo_edit.editingFinished.connect(self._load_branch_choices)
        self.branch_combo.currentTextChanged.connect(lambda text: self.branchChanged.emit(text))

        self._set_status("Ready to fetch branches")

        # If initialized with a repo URL, fetch branches immediately
        if default_repo:
            self._load_branch_choices()

    def set_github_token(self, token: Optional[str]) -> None:
        """Update the GitHub token and refresh branches if needed."""
        if self._github_token == token:
            return
        self._github_token = token
        # Only reload branches if we have a repo URL
        if self.repo_edit.text().strip():
            self._load_branch_choices()

    def repo_url(self) -> str:
        """Return the current repository URL."""
        return self.repo_edit.text().strip()

    def branch(self) -> str:
        """Return the current branch/tag."""
        return self.branch_combo.currentText().strip()

    def set_repo_url(self, url: str) -> None:
        """Set the repository URL and trigger branch loading."""
        self.repo_edit.setText(url)
        # Programmatically setting the URL should also load branches,
        # just like when a user enters a URL and presses Enter
        if url.strip():
            self._load_branch_choices()

    def set_branch(self, branch: str) -> None:
        """Set the branch/tag."""
        self.branch_combo.setEditText(branch)

    def _set_status(self, message: str, *, error: bool = False) -> None:
        if error:
            self.status_label.setStyleSheet("color: #a94442;")
        else:
            self.status_label.setStyleSheet("")
        self.status_label.setText(message)

    def _cancel_branch_process(self) -> None:
        if self.branch_fetch_thread and self.branch_fetch_thread.is_alive():
            self.branch_fetch_cancel.set()
            self.branch_fetch_thread.join(timeout=1.0)

    def _clear_branch_choices(self) -> None:
        """Clear branch choices when repository URL changes."""
        self._cancel_branch_process()
        self.branch_combo.clear()
        self._set_status("Ready to fetch branches")

    def _load_branch_choices(self) -> None:
        repo_value = self.repo_edit.text().strip()
        if not repo_value:
            self._set_status("Enter a repository URL", error=True)
            return

        remote_for_command = github_url_with_token(repo_value, self._github_token)
        if not is_git_available():
            self._set_status("Git is not available; enter a branch/tag manually.", error=True)
            return

        self._cancel_branch_process()
        self.branch_fetch_cancel.clear()
        self.branch_combo.setEnabled(False)
        self._set_status("Loading branch/tag list…")

        def fetch_branches():
            try:
                env = make_git_env()
                result = subprocess.run(
                    ["git", "ls-remote", "--heads", "--tags", remote_for_command],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    env=env
                )
                if not self.branch_fetch_cancel.is_set():
                    QtCore.QMetaObject.invokeMethod(
                        self,
                        "_handle_branch_fetch_finished",
                        QtCore.Qt.ConnectionType.QueuedConnection,
                        QtCore.Q_ARG(str, repo_value),
                        QtCore.Q_ARG(int, result.returncode),
                        QtCore.Q_ARG(str, result.stdout),
                        QtCore.Q_ARG(str, result.stderr)
                    )
            except Exception as exc:
                if not self.branch_fetch_cancel.is_set():
                    QtCore.QMetaObject.invokeMethod(
                        self,
                        "_handle_branch_fetch_error",
                        QtCore.Qt.ConnectionType.QueuedConnection,
                        QtCore.Q_ARG(str, repo_value),
                        QtCore.Q_ARG(str, str(exc))
                    )

        self.branch_fetch_thread = threading.Thread(target=fetch_branches, daemon=True)
        self.branch_fetch_thread.start()

    @QtCore.pyqtSlot(str, int, str, str)
    def _handle_branch_fetch_finished(
            self,
            repo_value: str,
            exit_code: int,
            stdout: str,
            stderr: str) -> None:
        self.branch_fetch_thread = None
        self.branch_combo.setEnabled(True)
        if exit_code != 0:
            detail = stderr.strip() or "git ls-remote failed."
            self._set_status(f"Unable to list branches for {repo_value}: {detail}", error=True)
            return
        names = self._parse_ref_names(stdout)
        if DEFAULT_BRANCH in names:
            names = [DEFAULT_BRANCH] + [name for name in names if name != DEFAULT_BRANCH]
        self._populate_branch_combo(names)
        if names:
            self._set_status(f"Loaded {len(names)} branches/tags.")
        else:
            self._set_status("No branches/tags reported; enter a reference manually.", error=True)
        self.repoChanged.emit(repo_value)

    @QtCore.pyqtSlot(str, str)
    def _handle_branch_fetch_error(
            self,
            repo_value: str,
            error: str) -> None:
        self.branch_fetch_thread = None
        self.branch_combo.setEnabled(True)
        self._set_status(f"Unable to run git ls-remote for {repo_value}: {error}", error=True)

    def _parse_ref_names(self, stdout: str) -> List[str]:
        seen: set[str] = set()
        names: List[str] = []
        for line in stdout.splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            ref = parts[1].strip()
            if ref.endswith("^{}"):
                ref = ref[:-3]
            if ref.startswith("refs/heads/"):
                name = ref.split("refs/heads/", 1)[1]
            elif ref.startswith("refs/tags/"):
                name = ref.split("refs/tags/", 1)[1]
            else:
                continue
            if name and name not in seen:
                seen.add(name)
                names.append(name)
        return names

    def _populate_branch_combo(self, names: List[str]) -> None:
        current_text = self.branch_combo.currentText().strip()
        self.branch_combo.blockSignals(True)
        self.branch_combo.clear()
        for name in names:
            self.branch_combo.addItem(name)
        if current_text:
            index = self.branch_combo.findText(current_text)
            if index >= 0:
                self.branch_combo.setCurrentIndex(index)
            else:
                self.branch_combo.setEditText(current_text)
        self.branch_combo.blockSignals(False)


class LocationPage(QtWidgets.QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Installation Target")
        outer_layout = QtWidgets.QVBoxLayout(self)

        # Target location section (top of vertical split)
        target_group = QtWidgets.QGroupBox("Target Location")
        target_form = QtWidgets.QFormLayout(target_group)
        target_help = QtWidgets.QLabel(
            "Pick an empty folder where ACQ4 and its conda environment will be created. "
            "This is required for every installation; the installer will create the directory for you."
        )
        target_help.setWordWrap(True)
        target_form.addRow(target_help)
        default_path = Path.home() / DEFAULT_INSTALL_DIR_NAME
        self.path_edit = QtWidgets.QLineEdit(str(default_path))
        self.registerField("install_path*", self.path_edit)
        browse_btn = QtWidgets.QPushButton("Browse…")
        browse_btn.clicked.connect(self._select_path)
        path_row = QtWidgets.QHBoxLayout()
        path_row.addWidget(self.path_edit)
        path_row.addWidget(browse_btn)
        target_form.addRow("Install location", path_row)
        self.path_status_label = QtWidgets.QLabel()
        self.path_status_label.setWordWrap(True)
        target_form.addRow(self.path_status_label)

        # Version section (bottom of vertical split)
        version_group = QtWidgets.QGroupBox("ACQ4 Version")
        version_layout = QtWidgets.QVBoxLayout(version_group)
        version_help = QtWidgets.QLabel(
            "These values determine which version of ACQ4 will be installed from the Git repository."
            " Use the default values unless you know you need a specific branch or tag."
        )
        version_help.setWordWrap(True)
        version_layout.addWidget(version_help)

        self.git_repo_widget = GitRepoWidget(default_repo=ACQ4_REPO_URL, default_branch=DEFAULT_BRANCH)
        self.registerField("repo_url*", self.git_repo_widget.repo_edit)
        self.registerField("branch", self.git_repo_widget.branch_combo, "currentText",
                          self.git_repo_widget.branch_combo.currentTextChanged)
        self.git_repo_widget.repoChanged.connect(lambda _: self.completeChanged.emit())
        version_layout.addWidget(self.git_repo_widget)

        token_form = QtWidgets.QFormLayout()
        self.github_token_edit = QtWidgets.QLineEdit()
        self.github_token_edit.setPlaceholderText("Optional")
        self.registerField("github_token", self.github_token_edit)
        token_form.addRow("GitHub token", self.github_token_edit)
        token_help = QtWidgets.QLabel(
            "Optional: provide a GitHub personal access token that will be used whenever code is cloned from GitHub. "
            " (This can be used to facilitate pushing code/config changes from your install back to GitHub). "
        )
        token_help.setWordWrap(True)
        token_form.addRow(token_help)
        version_layout.addLayout(token_form)

        outer_layout.addWidget(target_group)
        outer_layout.addWidget(version_group)
        outer_layout.addStretch(1)
        self.path_edit.textChanged.connect(self._validate_path)
        self.github_token_edit.editingFinished.connect(self._handle_token_change)
        self._validate_path()

    def _select_path(self) -> None:
        directory = QtWidgets.QFileDialog.getExistingDirectory(self, "Select install directory", str(Path.home()))
        if directory:
            self.path_edit.setText(directory)

    def _validate_path(self) -> None:
        text = self.path_edit.text().strip()
        try:
            path = Path(text).expanduser()
        except Exception:
            self._set_path_status("Invalid path. Please choose another location.", error=True)
            self.completeChanged.emit()
            return
        if not text:
            self._set_path_status("", error=False)
        elif path.exists() and not path.is_dir():
            self._set_path_status("Selected path exists but is not a directory. Choose a new location.", error=True)
        elif path.exists():
            self._set_path_status("Selected path already exists and cannot be used.", error=True)
        else:
            self._set_path_status("Directory will be created automatically.", error=False)
        self.completeChanged.emit()

    def isComplete(self) -> bool:  # noqa: N802
        text = self.path_edit.text().strip()
        if not text:
            return False
        if not self.git_repo_widget.repo_url():
            return False
        try:
            path = Path(text).expanduser()
        except Exception:
            return False
        return not path.exists()

    def apply_cli_args(self, args: argparse.Namespace) -> None:
        if args.install_path:
            raw_path = Path(str(args.install_path)).expanduser()
            try:
                resolved = raw_path.resolve()
            except Exception:
                resolved = raw_path
            self.path_edit.setText(str(resolved))
        if args.repo_url:
            self.git_repo_widget.set_repo_url(str(args.repo_url))
        if args.branch:
            self.git_repo_widget.set_branch(str(args.branch))
        if args.github_token:
            self.github_token_edit.setText(str(args.github_token))

    def cli_arguments(self) -> List[str]:
        path_value = self.path_edit.text().strip()
        repo_value = self.git_repo_widget.repo_url() or ACQ4_REPO_URL
        branch_value = self.git_repo_widget.branch() or DEFAULT_BRANCH
        token_value = self._current_token()
        args = [
            ARG_INSTALL_PATH,
            path_value,
            ARG_REPO_URL,
            repo_value,
            ARG_BRANCH,
            branch_value,
        ]
        if token_value:
            args.extend([ARG_GITHUB_TOKEN, token_value])
        return args

    def _set_path_status(self, message: str, *, error: bool) -> None:
        if error:
            self.path_status_label.setStyleSheet("color: #a94442;")
        else:
            self.path_status_label.setStyleSheet("")
        self.path_status_label.setText(message)

    def _handle_token_change(self) -> None:
        self.git_repo_widget.set_github_token(self._current_token())

    def _current_token(self) -> Optional[str]:
        token = self.github_token_edit.text().strip()
        return token or None


class DependenciesPage(QtWidgets.QWizardPage):
    def __init__(self, editable_map: Dict[str, EditableDependency]) -> None:
        super().__init__()
        self.setTitle("Dependencies")
        self.options: List[DependencyOption] = []
        self.groups: List[DependencyGroup] = []
        self.editable_map = editable_map
        self.option_lookup: Dict[str, DependencyOption] = {}
        self._initialized = False
        self._pending_cli_args: Optional[argparse.Namespace] = None
        layout = QtWidgets.QVBoxLayout(self)
        description = QtWidgets.QLabel(
            "Optional packages enable specific hardware drivers, lab workflows, documentation builds, and other extras. "
            "Everything required for ACQ4 to run is already included; uncheck anything you do not need to reduce download size."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        self.option_items: Dict[str, QtWidgets.QTreeWidgetItem] = {}
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        layout.addWidget(self.tree)
        self.status_label = QtWidgets.QLabel("")
        layout.addWidget(self.status_label)
        clone_label = QtWidgets.QLabel(
            "Editable clones fetch the full source for select packages so you can make changes and track them in-place. "
            "Only enable these if you plan to develop those libraries locally; each clone adds a separate git checkout."
        )
        clone_label.setWordWrap(True)
        layout.addWidget(clone_label)
        self.clone_tree = QtWidgets.QTreeWidget()
        self.clone_tree.setHeaderHidden(True)
        self.clone_tree.setRootIsDecorated(False)
        self.clone_tree.setUniformRowHeights(True)
        self.clone_tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        layout.addWidget(self.clone_tree)
        self.clone_items: Dict[str, QtWidgets.QTreeWidgetItem] = {}
        self._populate_clone_tree()

        # Desktop shortcut checkbox (Windows only)
        self.create_shortcut_checkbox = QtWidgets.QCheckBox("Create desktop shortcut to start ACQ4")
        self.create_shortcut_checkbox.setChecked(True)
        if sys.platform != "win32":
            self.create_shortcut_checkbox.setVisible(False)
        layout.addWidget(self.create_shortcut_checkbox)

    def initializePage(self) -> None:
        """Fetch pyproject.toml from GitHub and populate the dependency tree."""
        if self._initialized:
            return

        wizard = cast(InstallWizard, self.wizard())
        repo_url = wizard.repo_url()
        branch = wizard.branch()

        self.status_label.setText(f"Fetching dependencies from {repo_url} ({branch})...")
        QtWidgets.QApplication.processEvents()

        try:
            content, used_fallback = fetch_pyproject_from_github(repo_url, branch)
            self.groups = dependency_groups_from_pyproject(content=content)
            self.options = parse_optional_dependencies(content=content)
            self.option_lookup = {dep.spec: dep for dep in self.options}
            self._populate_tree()
            if used_fallback:
                self.status_label.setStyleSheet("color: #8a6d3b;")  # Warning color
                self.status_label.setText(
                    f"Note: pyproject.toml not found in {repo_url} ({branch}). "
                    "Using dependency list from github.com/acq4/acq4:main instead."
                )
            else:
                self.status_label.setText("")
            self._initialized = True

            # Apply CLI args if they were provided before initialization
            if self._pending_cli_args is not None:
                self._apply_cli_args_internal(self._pending_cli_args)
                self._pending_cli_args = None
        except InstallerError as exc:
            self.status_label.setStyleSheet("color: #a94442;")
            self.status_label.setText(f"Error loading dependencies: {exc}")

    def _populate_tree(self) -> None:
        assert self.tree is not None
        self.tree.clear()
        for group in self.groups:
            parent_label = _format_with_description(group.title, group.description)
            parent = QtWidgets.QTreeWidgetItem([parent_label])
            parent.setExpanded(True)
            flags = parent.flags()
            if group.optional:
                parent_flags = flags | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                if TRISTATE_FLAG is not None:
                    parent_flags |= TRISTATE_FLAG
                parent.setFlags(parent_flags)
                parent.setCheckState(0, QtCore.Qt.CheckState.Checked)
            else:
                parent.setFlags(flags & ~QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            for spec in group.packages:
                item = QtWidgets.QTreeWidgetItem(parent, [spec])
                dep = self.option_lookup.get(spec)
                label = self._option_label(dep, spec)
                item.setText(0, label)
                if group.optional:
                    child_flags = item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                    item.setFlags(child_flags)
                    item.setCheckState(0, QtCore.Qt.CheckState.Checked)
                else:
                    item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                item.setData(0, QtCore.Qt.ItemDataRole.UserRole, spec)
                self.option_items[spec] = item
            self.tree.addTopLevelItem(parent)
        self.tree.expandAll()

    def _populate_clone_tree(self) -> None:
        self.clone_tree.clear()
        for editable in self.editable_map.values():
            label = self._editable_label(editable)
            item = QtWidgets.QTreeWidgetItem([label])
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
            item.setData(0, QtCore.Qt.ItemDataRole.UserRole, editable.key)
            self.clone_tree.addTopLevelItem(item)
            self.clone_items[editable.key] = item

    def _option_label(self, dep: Optional[DependencyOption], fallback: str) -> str:
        if dep is None:
            return fallback
        title = dep.display_name or dep.spec
        return _format_with_description(title, dep.description)

    def _editable_label(self, editable: EditableDependency) -> str:
        return _format_with_description(editable.display_name or editable.key, editable.description)

    def selected_specs(self) -> List[str]:
        enabled: List[str] = []
        for dep in self.options:
            item = self.option_items.get(dep.spec)
            if item is not None and item.checkState(0) == QtCore.Qt.CheckState.Checked:
                enabled.append(dep.spec)
        return enabled

    def selected_clone_keys(self) -> List[str]:
        selected: List[str] = []
        for key, item in self.clone_items.items():
            if item.checkState(0) == QtCore.Qt.CheckState.Checked:
                selected.append(key)
        return selected

    def apply_cli_args(self, args: argparse.Namespace) -> None:
        """Apply CLI arguments to this page.

        If the page hasn't been initialized yet, store the args for later application.
        """
        if not self._initialized:
            self._pending_cli_args = args
        else:
            self._apply_cli_args_internal(args)

    def _apply_cli_args_internal(self, args: argparse.Namespace) -> None:
        """Apply CLI arguments to the dependency selections."""
        try:
            selected_specs = resolve_optional_selection_from_args(args, self.options, self.groups)
        except InstallerError:
            selected_specs = [dep.spec for dep in self.options]
        selected_set = set(selected_specs)
        for spec, item in self.option_items.items():
            state = QtCore.Qt.CheckState.Checked if spec in selected_set else QtCore.Qt.CheckState.Unchecked
            item.setCheckState(0, state)
        try:
            clone_keys = resolve_editable_selection_from_args(args, self.editable_map)
        except InstallerError:
            clone_keys = []
        clone_set = set(clone_keys)
        for key, item in self.clone_items.items():
            state = QtCore.Qt.CheckState.Checked if key in clone_set else QtCore.Qt.CheckState.Unchecked
            item.setCheckState(0, state)

    def cli_arguments(self) -> List[str]:
        specs = self.selected_specs()
        args: List[str] = []
        if len(specs) == len(self.options):
            args.extend([ARG_OPTIONAL_MODE, "all"])
        elif not specs:
            args.extend([ARG_OPTIONAL_MODE, "none"])
        else:
            args.extend([ARG_OPTIONAL_MODE, "list"])
            cli_names: List[str] = []
            for spec in specs:
                dep = self.option_lookup.get(spec)
                cli_names.append(dep.cli_name if dep else normalize_spec_name(spec))
            args.extend([ARG_OPTIONAL_DEP, ",".join(cli_names)])
        clones = self.selected_clone_keys()
        if clones:
            args.extend([ARG_EDITABLE_CLONE, ",".join(clones)])
        return args


class ConfigPage(QtWidgets.QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Configuration Source")
        layout = QtWidgets.QVBoxLayout(self)
        intro_label = QtWidgets.QLabel(
            "Every ACQ4 installation needs a configuration directory that captures hardware mappings and experiment defaults. "
            "Choose how you want to create or reuse that configuration before first launch."
        )
        intro_label.setWordWrap(True)
        layout.addWidget(intro_label)
        self.new_radio = QtWidgets.QRadioButton("Create a new configuration from acq4/config/example")
        self.clone_radio = QtWidgets.QRadioButton("Clone configuration from repository")
        self.copy_radio = QtWidgets.QRadioButton("Copy configuration from an existing directory")
        self.new_radio.setChecked(True)
        layout.addWidget(self.new_radio)
        new_help = QtWidgets.QLabel(
            "Recommended for first-time setups. The installer copies a clean template that you can customize later."
        )
        new_help.setWordWrap(True)
        new_help.setIndent(24)
        layout.addWidget(new_help)

        clone_block = QtWidgets.QVBoxLayout()
        clone_block.addWidget(self.clone_radio)
        clone_help = QtWidgets.QLabel(
            "Select this when your lab already maintains a shared config repository. "
            "Provide a git URL with read access (use a token if the repo is private)."
        )
        clone_help.setWordWrap(True)
        clone_help.setIndent(24)
        clone_block.addWidget(clone_help)
        self.clone_widget_container = QtWidgets.QWidget()
        self.clone_widget_container.setContentsMargins(32, 0, 0, 0)
        clone_widget_layout = QtWidgets.QVBoxLayout(self.clone_widget_container)
        clone_widget_layout.setContentsMargins(0, 0, 0, 0)
        self.git_repo_widget = GitRepoWidget(default_repo="", default_branch="main")
        self.git_repo_widget.repo_edit.setPlaceholderText("https://github.com/your/config-repo.git")
        clone_widget_layout.addWidget(self.git_repo_widget)

        # Config file selection for clone mode
        clone_config_file_layout = QtWidgets.QFormLayout()
        self.clone_config_file_combo = QtWidgets.QComboBox()
        self.clone_config_file_combo.setEditable(True)
        self.clone_config_file_combo.setPlaceholderText("default.cfg")
        clone_config_file_layout.addRow("Config file:", self.clone_config_file_combo)
        self.clone_config_file_status_label = QtWidgets.QLabel()
        self.clone_config_file_status_label.setWordWrap(True)
        clone_config_file_layout.addRow(self.clone_config_file_status_label)
        clone_widget_layout.addLayout(clone_config_file_layout)

        clone_block.addWidget(self.clone_widget_container)
        layout.addLayout(clone_block)

        copy_block = QtWidgets.QVBoxLayout()
        copy_block.addWidget(self.copy_radio)
        copy_help = QtWidgets.QLabel(
            "Use this if you already have a working ACQ4 config folder on disk (for example from another machine) "
            "and simply want to copy it into the new installation."
        )
        copy_help.setWordWrap(True)
        copy_help.setIndent(24)
        copy_block.addWidget(copy_help)

        self.copy_widget_container = QtWidgets.QWidget()
        self.copy_widget_container.setContentsMargins(32, 0, 0, 0)
        copy_widget_layout = QtWidgets.QVBoxLayout(self.copy_widget_container)
        copy_widget_layout.setContentsMargins(0, 0, 0, 0)

        self.copy_path_edit = QtWidgets.QLineEdit()
        self.copy_path_edit.setPlaceholderText("Path to existing ACQ4 config directory")
        self.copy_browse_button = QtWidgets.QPushButton("Browse…")
        self.copy_browse_button.clicked.connect(self._browse_copy_path)
        copy_row = QtWidgets.QHBoxLayout()
        copy_row.addWidget(self.copy_path_edit)
        copy_row.addWidget(self.copy_browse_button)
        copy_widget_layout.addLayout(copy_row)

        # Config file selection for copy mode
        copy_config_file_layout = QtWidgets.QFormLayout()
        self.copy_config_file_combo = QtWidgets.QComboBox()
        self.copy_config_file_combo.setEditable(True)
        self.copy_config_file_combo.setPlaceholderText("default.cfg")
        copy_config_file_layout.addRow("Config file:", self.copy_config_file_combo)
        self.copy_config_file_status_label = QtWidgets.QLabel()
        self.copy_config_file_status_label.setWordWrap(True)
        copy_config_file_layout.addRow(self.copy_config_file_status_label)
        copy_widget_layout.addLayout(copy_config_file_layout)

        copy_block.addWidget(self.copy_widget_container)
        layout.addLayout(copy_block)

        self.clone_radio.toggled.connect(self._update_mode_widgets)
        self.copy_radio.toggled.connect(self._update_mode_widgets)
        self.new_radio.toggled.connect(self._update_mode_widgets)
        self.git_repo_widget.repoChanged.connect(self._on_clone_repo_changed)
        self.git_repo_widget.branchChanged.connect(self._on_clone_branch_changed)
        self.copy_path_edit.textChanged.connect(self._on_copy_path_changed)
        self._update_mode_widgets()

    def isComplete(self) -> bool:  # noqa: N802
        if self.clone_radio.isChecked():
            return bool(self.git_repo_widget.repo_url())
        if self.copy_radio.isChecked():
            return bool(self.copy_path_edit.text().strip())
        return True

    def apply_cli_args(self, args: argparse.Namespace) -> None:
        # Infer mode from which arguments are present
        if args.config_repo:
            self.clone_radio.setChecked(True)
            self.git_repo_widget.set_repo_url(str(args.config_repo))
            if args.config_branch:
                self.git_repo_widget.set_branch(str(args.config_branch))
        elif args.config_path:
            self.copy_radio.setChecked(True)
            self.copy_path_edit.setText(str(args.config_path))
        else:
            self.new_radio.setChecked(True)

        if args.config_file:
            if self.clone_radio.isChecked():
                self.clone_config_file_combo.setEditText(args.config_file)
            elif self.copy_radio.isChecked():
                self.copy_config_file_combo.setEditText(args.config_file)
        self._update_mode_widgets()

    def cli_arguments(self) -> List[str]:
        args: List[str] = []

        if self.clone_radio.isChecked():
            repo = self.git_repo_widget.repo_url()
            if repo:
                args.extend([ARG_CONFIG_REPO, repo])
            branch = self.git_repo_widget.branch()
            if branch:
                args.extend([ARG_CONFIG_BRANCH, branch])
            config_file = self.clone_config_file_combo.currentText().strip()
            if config_file:
                args.extend([ARG_CONFIG_FILE, config_file])
        elif self.copy_radio.isChecked():
            path = self.copy_path_edit.text().strip()
            if path:
                args.extend([ARG_CONFIG_PATH, path])
            config_file = self.copy_config_file_combo.currentText().strip()
            if config_file:
                args.extend([ARG_CONFIG_FILE, config_file])
        # else: new mode - no args needed

        return args

    def _update_mode_widgets(self) -> None:
        clone_enabled = self.clone_radio.isChecked()
        copy_enabled = self.copy_radio.isChecked()
        self.clone_widget_container.setVisible(clone_enabled)
        self.copy_widget_container.setVisible(copy_enabled)
        self.completeChanged.emit()

    def _browse_copy_path(self) -> None:
        start_dir = self.copy_path_edit.text().strip() or str(Path.home())
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select existing ACQ4 config directory",
            start_dir
        )
        if directory:
            self.copy_path_edit.setText(directory)

    def _on_copy_path_changed(self, path_text: str) -> None:
        """Update config file list when copy path changes."""
        self.completeChanged.emit()
        if not self.copy_radio.isChecked():
            return
        path_text = path_text.strip()
        if not path_text:
            self.copy_config_file_combo.clear()
            self.copy_config_file_status_label.setText("")
            return
        config_path = Path(path_text).expanduser().resolve()
        if not config_path.exists() or not config_path.is_dir():
            self.copy_config_file_combo.clear()
            self.copy_config_file_status_label.setText("Invalid directory path")
            return
        # List files in the directory
        try:
            files = [f.name for f in config_path.iterdir() if f.is_file() and not f.name.startswith(".")]
            self._populate_config_file_combo(files, "copy")
        except (OSError, PermissionError) as e:
            self.copy_config_file_combo.clear()
            self.copy_config_file_status_label.setText(f"Error reading directory: {e}")

    def _on_clone_repo_changed(self, repo_url: str) -> None:
        """Update config file list when clone repo changes."""
        self.completeChanged.emit()
        if not self.clone_radio.isChecked():
            return
        self._refresh_clone_file_list()

    def _on_clone_branch_changed(self, branch: str) -> None:
        """Update config file list when clone branch changes."""
        if not self.clone_radio.isChecked():
            return
        self._refresh_clone_file_list()

    def _refresh_clone_file_list(self) -> None:
        """Refresh the config file list from the git repository."""
        repo_url = self.git_repo_widget.repo_url()
        if not repo_url:
            self.clone_config_file_combo.clear()
            self.clone_config_file_status_label.setText("")
            return
        # Fetch files from git repo in a background thread
        self.clone_config_file_status_label.setText("Loading file list from repository...")
        self.clone_config_file_combo.setEnabled(False)

        def fetch_files():
            try:
                wizard = self.wizard()
                token = wizard.github_token() if wizard else None
                branch = self.git_repo_widget.branch() or "main"
                repo_with_token = github_url_with_token(repo_url, token)
                files = list_git_repo_files(repo_with_token, branch)
                QtCore.QMetaObject.invokeMethod(
                    self,
                    "_handle_git_files_loaded",
                    QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(list, files)
                )
            except Exception as exc:
                QtCore.QMetaObject.invokeMethod(
                    self,
                    "_handle_git_files_error",
                    QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, str(exc))
                )

        thread = threading.Thread(target=fetch_files, daemon=True)
        thread.start()

    @QtCore.pyqtSlot(list)
    def _handle_git_files_loaded(self, files: List[str]) -> None:
        """Handle successful loading of files from git repo."""
        self.clone_config_file_combo.setEnabled(True)
        self._populate_config_file_combo(files, "clone")
        if files:
            self.clone_config_file_status_label.setText(f"Found {len(files)} files")
        else:
            self.clone_config_file_status_label.setText("No files found in repository root")

    @QtCore.pyqtSlot(str)
    def _handle_git_files_error(self, error: str) -> None:
        """Handle error loading files from git repo."""
        self.clone_config_file_combo.setEnabled(True)
        self.clone_config_file_combo.clear()
        self.clone_config_file_status_label.setText(f"Error loading files: {error}")

    def _populate_config_file_combo(self, files: List[str], mode: str) -> None:
        """Populate the config file combo box with the given files.

        Args:
            files: List of file names to populate
            mode: Either "clone" or "copy" to determine which combo box to use
        """
        if mode == "clone":
            combo = self.clone_config_file_combo
            status_label = self.clone_config_file_status_label
        elif mode == "copy":
            combo = self.copy_config_file_combo
            status_label = self.copy_config_file_status_label
        else:
            raise ValueError(f"Invalid mode: {mode}")

        current_text = combo.currentText().strip()
        combo.blockSignals(True)
        combo.clear()

        # Sort files, prioritizing default.cfg
        sorted_files = sorted(files)
        if "default.cfg" in sorted_files:
            sorted_files.remove("default.cfg")
            sorted_files.insert(0, "default.cfg")

        for filename in sorted_files:
            combo.addItem(filename)

        # Restore previous selection or default to default.cfg
        if current_text and current_text in files:
            index = combo.findText(current_text)
            if index >= 0:
                combo.setCurrentIndex(index)
        elif "default.cfg" in files:
            combo.setCurrentText("default.cfg")
        elif sorted_files:
            combo.setCurrentIndex(0)

        combo.blockSignals(False)
        status_label.setText("")


class SummaryPage(QtWidgets.QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Ready to Install")
        layout = QtWidgets.QVBoxLayout(self)
        self.summary_label = QtWidgets.QLabel()
        self.summary_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)
        layout.addSpacing(12)
        self.export_help = QtWidgets.QLabel(
            'Use the Export button to "bake" this configuration into a reusable unattended script. '
            "That script installs ACQ4 with the exact settings shown above on other machines."
        )
        self.export_help.setWordWrap(True)
        layout.addWidget(self.export_help)

        export_row = QtWidgets.QHBoxLayout()
        self.export_button = QtWidgets.QPushButton("Export installation script…")
        size_policy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum,
                                            QtWidgets.QSizePolicy.Policy.Fixed)
        self.export_button.setSizePolicy(size_policy)
        self.export_button.clicked.connect(self._export_script)
        export_row.addWidget(self.export_button)

        self.unattended_checkbox = QtWidgets.QCheckBox("Unattended install")
        self.unattended_checkbox.setChecked(False)
        self.unattended_checkbox.setToolTip(
            "When checked, the exported script will run without user interaction. "
            "Uncheck to create an interactive installer script."
        )
        export_row.addWidget(self.unattended_checkbox)
        export_row.addStretch(1)

        layout.addLayout(export_row)
        self._previous_next_text: Optional[str] = None

    def initializePage(self) -> None:  # noqa: N802
        wizard: InstallWizard = self.wizard()  # type: ignore[assignment]
        path = wizard.install_path()
        branch = wizard.branch()
        repo_url = wizard.repo_url()
        optional_count = len(wizard.selected_optional_specs())
        mode = wizard.config_mode()
        if mode == "clone":
            repo = wizard.config_repo()
            config_source = f"clone ({repo})" if repo else "clone"
        elif mode == "copy":
            copy_path = wizard.config_copy_path()
            config_source = f"copy ({copy_path})" if copy_path else "copy"
        else:
            config_source = "new"
        editable_display = ", ".join(wizard.selected_editable_keys()) or "None"
        summary_items = [
            ("Install directory", path),
            ("Repository", repo_url),
            ("Branch/tag", branch),
            ("Optional dependencies selected", optional_count),
            ("Editable clones", editable_display),
            ("Config source", config_source),
        ]
        if mode in ("clone", "copy"):
            config_file = wizard.config_file()
            if config_file:
                summary_items.append(("Config file", config_file))
        summary_html = "<ul>" + "".join(
            f"<li><b>{title}:</b> {value}</li>" for title, value in summary_items
        ) + "</ul>"
        self.summary_label.setText(summary_html)
        if wizard is not None:
            if self._previous_next_text is None:
                self._previous_next_text = wizard.buttonText(QtWidgets.QWizard.WizardButton.NextButton)
            wizard.setButtonText(QtWidgets.QWizard.WizardButton.NextButton, "Install")

    def cleanupPage(self) -> None:  # noqa: N802
        wizard = self.wizard()
        if wizard is not None and self._previous_next_text is not None:
            wizard.setButtonText(QtWidgets.QWizard.WizardButton.NextButton, self._previous_next_text)
        super().cleanupPage()

    def _export_script(self) -> None:
        wizard: Optional[InstallWizard] = self.wizard()  # type: ignore[assignment]
        if wizard is None:
            return
        unattended = self.unattended_checkbox.isChecked()
        cli_args = wizard.cli_arguments(unattended=unattended)
        is_windows = os.name == "nt"
        default_suffix = ".bat" if is_windows else ".sh"
        default_name = f"acq4_install{default_suffix}"
        dialog_fn = QtWidgets.QFileDialog.getSaveFileName
        filters = "Script files (*.sh *.bat);;Shell scripts (*.sh);;Batch scripts (*.bat)"
        default_path = Path.cwd() / default_name
        file_path, _ = dialog_fn(
            self,
            "Save unattended installer script",
            str(default_path),
            filters,
        )
        if not file_path:
            return
        target_path = Path(file_path)
        if target_path.suffix.lower() not in {".sh", ".bat"}:
            target_path = target_path.with_suffix(default_suffix)
        try:
            script_text = build_unattended_script_content(cli_args, is_windows=is_windows)
            target_path.write_text(script_text, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(self, "Export Failed", str(exc))
        else:
            QtWidgets.QMessageBox.information(self, "Export Complete",
                                              f"Script saved to {target_path}. Run it to repeat this installation.")


class InstallPage(QtWidgets.QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Install")
        self.setFinalPage(True)
        layout = QtWidgets.QVBoxLayout(self)
        description = QtWidgets.QLabel("ACQ4 will now be installed. You can review progress and logs below.")
        description.setWordWrap(True)
        layout.addWidget(description)
        self.log_tree = QtWidgets.QTreeWidget()
        self.log_tree.setHeaderHidden(True)
        self.log_tree.setUniformRowHeights(True)
        self.log_tree.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.log_tree.setTextElideMode(QtCore.Qt.TextElideMode.ElideNone)
        self.log_tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.log_tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.log_tree.customContextMenuRequested.connect(self._show_log_context_menu)
        self.log_tree.setToolTip("Right-click or use Ctrl+C to copy selected log lines")
        header = self.log_tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.log_tree)
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 0)
        layout.addWidget(self.progress_bar)
        self._worker: Optional[InstallerWorker] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._state: Optional[InstallerState] = None
        self._task_items: Dict[int, QtWidgets.QTreeWidgetItem] = {}
        self._command_items: Dict[int, QtWidgets.QTreeWidgetItem] = {}
        self._completed = False
        self._running = False
        self._success_icon = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogApplyButton)
        self._error_icon = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MessageBoxCritical)
        self._back_button: Optional[QtWidgets.QAbstractButton] = None
        self._cancel_button: Optional[QtWidgets.QAbstractButton] = None
        self._pending_navigation: Optional[str] = None
        self._cancel_requested = False

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if obj in {self._back_button, self._cancel_button} and event.type() in {
            QtCore.QEvent.Type.MouseButtonPress,
            QtCore.QEvent.Type.KeyPress,
        }:
            if event.type() == QtCore.QEvent.Type.KeyPress:
                key_event = cast(QtGui.QKeyEvent, event)
                allowed = {
                    qt_key("Key_Return"),
                    qt_key("Key_Enter"),
                    qt_key("Key_Space"),
                }
                if obj is self._cancel_button:
                    allowed.add(qt_key("Key_Escape"))
                if key_event.key() not in allowed:
                    return False
            if obj is self._back_button:
                return self._handle_back_event(event)
            if obj is self._cancel_button:
                return self._handle_cancel_event(event)
        return super().eventFilter(obj, event)

    def isComplete(self) -> bool:  # noqa: N802
        return self._completed

    def initializePage(self) -> None:  # noqa: N802
        super().initializePage()
        self._completed = False
        self._cancel_requested = False
        self._pending_navigation = None
        self._reset_ui()
        self._setup_navigation_hooks()
        self._start_installation()

    def cleanupPage(self) -> None:  # noqa: N802
        super().cleanupPage()
        self._remove_navigation_hooks()
        self._disconnect_worker()

    def _reset_ui(self) -> None:
        self.log_tree.clear()
        self._task_items.clear()
        self._command_items.clear()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setValue(0)

    def _start_installation(self) -> None:
        wizard: Optional[InstallWizard] = self.wizard()  # type: ignore[assignment]
        if wizard is None:
            return
        self._state = collect_state(wizard)
        self._running = True
        self._update_navigation(running=True, success=False)
        self._worker = InstallerWorker(self._state)
        self._worker.log_event.connect(self._handle_log_event)
        self._worker.finished.connect(self._handle_finished)
        self._worker_thread = threading.Thread(target=self._worker.run, daemon=True)
        self._worker_thread.start()

    def _disconnect_worker(self) -> None:
        if self._worker:
            try:
                self._worker.log_event.disconnect(self._handle_log_event)
            except TypeError:
                pass
            try:
                self._worker.finished.disconnect(self._handle_finished)
            except TypeError:
                pass
        self._worker = None
        self._worker_thread = None

    def _setup_navigation_hooks(self) -> None:
        wizard = self.wizard()
        if not wizard:
            return
        self._back_button = wizard.button(QtWidgets.QWizard.WizardButton.BackButton)
        self._cancel_button = wizard.button(QtWidgets.QWizard.WizardButton.CancelButton)
        for button in (self._back_button, self._cancel_button):
            if button is not None:
                button.installEventFilter(self)

    def _remove_navigation_hooks(self) -> None:
        for button in (self._back_button, self._cancel_button):
            if button is not None:
                button.removeEventFilter(self)
        self._back_button = None
        self._cancel_button = None

    def _handle_back_event(self, event: QtCore.QEvent) -> bool:
        if not self._running:
            return False
        if not self._confirm_back_navigation():
            return True
        self._request_cancel("back")
        return True

    def _handle_cancel_event(self, event: QtCore.QEvent) -> bool:
        if not self._running:
            return False
        self._request_cancel("cancel")
        return True

    def _confirm_back_navigation(self) -> bool:
        response = QtWidgets.QMessageBox.question(
            self,
            "Cancel installation?",
            "Going back will cancel the current installation. Continue?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        return response == QtWidgets.QMessageBox.StandardButton.Yes

    def _request_cancel(self, action: str) -> None:
        self._pending_navigation = action
        if self._cancel_requested:
            return
        self._cancel_requested = True
        if self._worker:
            self._worker.request_cancel()
        self._append_message("Cancellation requested...", None)

    def _perform_pending_navigation(self) -> None:
        if not self._pending_navigation:
            return
        wizard = self.wizard()
        action = self._pending_navigation
        self._pending_navigation = None
        if not wizard:
            return
        if action == "back":
            wizard.back()
        elif action == "cancel":
            wizard.reject()

    def _handle_log_event(self, event: InstallerLogEvent) -> None:
        kind = event.kind
        data = event.data
        if kind == "task-start":
            title = data.get("title", "Task")
            task_id = data.get("task_id")
            if task_id is None:
                return
            item = QtWidgets.QTreeWidgetItem([title])
            item.setExpanded(True)
            self.log_tree.addTopLevelItem(item)
            self._task_items[task_id] = item
            self._scroll_to_item(item)
        elif kind == "task-complete":
            task_id = data.get("task_id")
            success = data.get("success", False)
            item = self._task_items.get(task_id)
            if item is None:
                return
            item.setIcon(0, self._success_icon if success else self._error_icon)
            item.setExpanded(not success)
        elif kind == "command-start":
            command_id = data.get("command_id")
            task_id = data.get("task_id")
            text = data.get("text", "Command")
            if command_id is None:
                return
            parent = self._task_items.get(task_id)
            if parent is None:
                parent = QtWidgets.QTreeWidgetItem(["Task"])
                parent.setExpanded(True)
                self.log_tree.addTopLevelItem(parent)
            item = QtWidgets.QTreeWidgetItem([text])
            item.setExpanded(True)
            parent.addChild(item)
            self._command_items[command_id] = item
            self._scroll_to_item(item)
        elif kind == "command-output":
            command_id = data.get("command_id")
            text = data.get("text", "")
            parent = self._command_items.get(command_id)
            if parent is None:
                return
            output_item = QtWidgets.QTreeWidgetItem([text])
            font = output_item.font(0)
            font.setFamily("Monospace")
            output_item.setFont(0, font)
            parent.addChild(output_item)
            self._scroll_to_item(output_item)
        elif kind == "command-complete":
            command_id = data.get("command_id")
            success = data.get("success", False)
            item = self._command_items.get(command_id)
            if item is None:
                return
            item.setIcon(0, self._success_icon if success else self._error_icon)
            item.setExpanded(not success)
        elif kind == "message":
            text = data.get("text", "")
            task_id = data.get("task_id")
            self._append_message(text, task_id)
        elif kind == "progress":
            total = data.get("total", 0)
            value = data.get("value", 0)
            if total <= 0:
                self.progress_bar.setRange(0, 0)
            else:
                self.progress_bar.setRange(0, total)
                self.progress_bar.setValue(value)

    def _append_message(self, text: str, task_id: Optional[int]) -> None:
        if not text:
            return
        parent = self._task_items.get(task_id)
        if parent is None:
            item = QtWidgets.QTreeWidgetItem([text])
            font = item.font(0)
            font.setItalic(True)
            item.setFont(0, font)
            brush = QtGui.QBrush(QtGui.QColor("#555555"))
            item.setForeground(0, brush)
            self.log_tree.addTopLevelItem(item)
            self._scroll_to_item(item)
        else:
            child = QtWidgets.QTreeWidgetItem([text])
            font = child.font(0)
            font.setItalic(True)
            child.setFont(0, font)
            parent.addChild(child)
            self._scroll_to_item(child)

    def _scroll_to_item(self, item: QtWidgets.QTreeWidgetItem) -> None:
        index = self.log_tree.indexFromItem(item)
        self.log_tree.scrollTo(index, QtWidgets.QAbstractItemView.ScrollHint.PositionAtBottom)

    def _show_log_context_menu(self, position: QtCore.QPoint) -> None:
        """Show context menu for log tree with copy options."""
        menu = QtWidgets.QMenu(self.log_tree)

        # Copy action
        copy_action = menu.addAction("Copy Selected Lines")
        copy_action.setShortcut(QtGui.QKeySequence.StandardKey.Copy)
        copy_action.triggered.connect(self._copy_selected_log_lines)

        # Select All action
        select_all_action = menu.addAction("Select All")
        select_all_action.setShortcut(QtGui.QKeySequence.StandardKey.SelectAll)
        select_all_action.triggered.connect(self.log_tree.selectAll)

        # Only enable copy if there's a selection
        selected_items = self.log_tree.selectedItems()
        copy_action.setEnabled(len(selected_items) > 0)

        menu.exec(self.log_tree.viewport().mapToGlobal(position))

    def _copy_selected_log_lines(self) -> None:
        """Copy selected log lines to clipboard."""
        selected_items = self.log_tree.selectedItems()
        if not selected_items:
            return

        # Collect text from selected items, preserving tree hierarchy
        lines: List[str] = []
        for item in selected_items:
            # Get the indentation level
            level = 0
            parent = item.parent()
            while parent is not None:
                level += 1
                parent = parent.parent()

            # Add indentation
            indent = "  " * level
            text = item.text(0)
            lines.append(f"{indent}{text}")

        # Copy to clipboard
        clipboard = QtWidgets.QApplication.clipboard()
        if clipboard:
            clipboard.setText("\n".join(lines))

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # noqa: N802
        """Handle keyboard shortcuts."""
        # Ctrl+C to copy selected lines
        if event.matches(QtGui.QKeySequence.StandardKey.Copy):
            self._copy_selected_log_lines()
            event.accept()
            return
        # Ctrl+A to select all log lines
        if event.matches(QtGui.QKeySequence.StandardKey.SelectAll):
            self.log_tree.selectAll()
            event.accept()
            return
        super().keyPressEvent(event)

    def _handle_finished(self, success: bool, detail: str) -> None:
        self._running = False
        self._update_navigation(running=False, success=success)
        self._disconnect_worker()
        cancelled = detail == "Installation cancelled"
        if success:
            self._completed = True
            self.completeChanged.emit()

            # Add summary with post-install documentation to log
            post_install_message = self._build_post_install_message()
            if post_install_message:
                self._add_summary_to_log(post_install_message)
        else:
            if cancelled:
                QtWidgets.QMessageBox.information(self, "Installer", "Installation cancelled.")
            else:
                QtWidgets.QMessageBox.critical(self, "Installer", detail)
            self._prompt_cleanup()
        self._perform_pending_navigation()

    def _build_post_install_message(self) -> str:
        """Build HTML message with post-install documentation for selected packages."""
        if not self._state:
            return ""

        # Get selected optional dependencies with post-install docs
        packages_with_docs: List[Tuple[str, str]] = []
        selected_specs = set(self._state.selected_optional)

        for dep in self._state.optional_dependencies:
            if dep.spec in selected_specs and dep.post_install_doc:
                display_name = dep.display_name or dep.spec
                packages_with_docs.append((display_name, dep.post_install_doc))

        if not packages_with_docs:
            return ""

        # Build HTML list
        html_parts = ["<ul>"]
        for name, doc in packages_with_docs:
            html_parts.append(f"<li><b>{name}</b>: {doc}</li>")
        html_parts.append("</ul>")

        return "".join(html_parts)

    def _add_summary_to_log(self, post_install_message: str) -> None:
        """Add a Summary section to the log tree with post-install documentation."""
        # Create top-level Summary item
        summary_item = QtWidgets.QTreeWidgetItem(["Summary"])
        summary_item.setIcon(0, self._success_icon)
        self.log_tree.addTopLevelItem(summary_item)

        # Create a child item to hold the QTextEdit widget
        widget_item = QtWidgets.QTreeWidgetItem()
        summary_item.addChild(widget_item)
        summary_item.setExpanded(True)

        # Create QTextBrowser for displaying the message with clickable links
        text_edit = QtWidgets.QTextBrowser()
        text_edit.setHtml(
            "<p><b>Installation complete.</b></p>"
            "<p>The following packages require additional 3rd-party software to be installed:</p>"
            + post_install_message
        )

        # Make it look like embedded rich text: no border, transparent background, clickable links
        text_edit.setFrameStyle(QtWidgets.QFrame.Shape.NoFrame)
        text_edit.setStyleSheet("QTextBrowser { background-color: transparent; }")
        text_edit.setOpenExternalLinks(True)

        # Disable scrollbars - we'll size the widget to show all content
        text_edit.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        text_edit.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        text_edit.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed
        )

        # Attach the widget to the tree item first
        self.log_tree.setItemWidget(widget_item, 0, text_edit)

        # Calculate proper width and height after widget is attached
        # Get the actual column width (accounting for indentation and margins)
        column_width = self.log_tree.columnWidth(0)
        indent_width = self.log_tree.indentation() * 2  # Parent + child indentation
        margins = 20  # Internal margins
        available_width = column_width - indent_width - margins

        # Set document width and calculate required height
        doc = text_edit.document()
        doc.setTextWidth(available_width)
        required_height = int(doc.size().height()) + 10  # Add padding

        # Set the widget size
        text_edit.setFixedHeight(required_height)
        text_edit.setMinimumWidth(available_width)

        # Tell the tree item how tall it needs to be
        widget_item.setSizeHint(0, QtCore.QSize(available_width, required_height))

        # Scroll to the summary
        self._scroll_to_item(summary_item)

    def _update_navigation(self, running: bool, success: bool) -> None:
        wizard = self.wizard()
        if not wizard:
            return
        back_button = wizard.button(QtWidgets.QWizard.WizardButton.BackButton)
        if back_button is not None:
            back_button.setEnabled(True)
        cancel_button = wizard.button(QtWidgets.QWizard.WizardButton.CancelButton)
        if cancel_button is not None:
            cancel_button.setEnabled(True)
            cancel_button.setVisible(not success)
        finish_button = wizard.button(QtWidgets.QWizard.WizardButton.FinishButton)
        if finish_button is not None:
            finish_button.setEnabled(success)

    def _prompt_cleanup(self) -> None:
        if not self._state:
            return
        install_path = self._state.install_path
        if not install_path.exists():
            return
        response = QtWidgets.QMessageBox.question(
            self,
            "Delete Incomplete Installation?",
            f"Installation failed. Delete {install_path}?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if response != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        try:
            shutil.rmtree(install_path)
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.warning(self, "Unable to Delete", f"Could not remove {install_path}: {exc}")

def ensure_directory_empty(target: Path) -> None:
    """Ensure that the installation directory is newly created for this run.

    Parameters
    ----------
    target : Path
        Directory that will hold the new installation.
    """
    if target.exists():
        raise InstallerError(f"{target} already exists. Choose a new directory.")
    target.mkdir(parents=True, exist_ok=False)


def find_conda_executable() -> str:
    """Locate the conda executable, preferring the environment used by bootstrap scripts."""
    candidates = [os.environ.get("CONDA_EXE"), shutil.which("conda")]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise InstallerError("Conda executable not found. Please run the installer via the bootstrap script.")


def run_command(cmd: Iterable[str], logger: StructuredLogger, cwd: Optional[Path] = None,
                env: Optional[Dict[str, str]] = None, task_id: Optional[int] = None,
                cancel_event: Optional[threading.Event] = None,
                conda_env: Optional[Path] = None, conda_exe: Optional[str] = None,
                mask_values: Optional[Iterable[str]] = None) -> None:
    """Execute a subprocess while streaming stdout to the provided logger.

    Parameters
    ----------
    cmd : iterable of str
        Command and arguments to execute.
    logger : StructuredLogger
        Structured logger used for emitting task/command events and plain text output.
    cwd : Path, optional
        Directory to run the command from.
    env : dict, optional
        Environment overrides for the process.
    task_id : int, optional
        Currently active task identifier for associating events.
    cancel_event : threading.Event, optional
        When set, terminates the subprocess and raises ``InstallerCancelled``.
    conda_env : Path, optional
        When provided, run the command inside this conda environment via ``conda run -p``.
    conda_exe : str, optional
        Path to the conda executable; required if ``conda_env`` is set.
    mask_values : iterable of str, optional
        Secrets to redact from log output and raised error messages.
    """
    cmd_list = [str(part) for part in cmd]
    if conda_env is not None:
        if not conda_exe:
            raise InstallerError("conda_exe is required when conda_env is specified")
        cmd_list = [
            str(conda_exe),
            "run",
            "--no-capture-output",
            "-p",
            str(conda_env),
            *cmd_list,
        ]
    mask_list = [str(value) for value in (mask_values or []) if value]

    def _mask(text: str) -> str:
        result = text
        for secret in mask_list:
            result = result.replace(secret, "********")
        return result

    display_cmd = shlex.join(cmd_list)
    if cwd:
        display_cmd = f"(cd {cwd}) {display_cmd}"
    masked_display = _mask(display_cmd)
    command_id = logger.start_command(task_id, masked_display)
    process = subprocess.Popen(
        cmd_list,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    output_queue: "queue.Queue[Tuple[str, Optional[str]]]" = queue.Queue()
    pumps = [
        _StreamPump(process.stdout, "stdout", output_queue),
        _StreamPump(process.stderr, "stderr", output_queue),
    ]
    remaining = len(pumps)
    cancelled = False
    while remaining > 0:
        try:
            source, line = output_queue.get(timeout=0.1)
        except queue.Empty:
            if cancel_event and cancel_event.is_set() and process.poll() is None:
                cancelled = True
                process.kill()
            continue
        if line is None:
            remaining -= 1
            continue
        logger.command_output(command_id, line)
        if cancel_event and cancel_event.is_set() and process.poll() is None:
            cancelled = True
            process.kill()
    process.wait()
    for pump in pumps:
        pump.join()
    if process.stdout:
        process.stdout.close()
    if process.stderr:
        process.stderr.close()
    if cancel_event and cancel_event.is_set():
        cancelled = True
    if cancelled:
        if process.poll() is None:
            process.kill()
            process.wait()
        logger.finish_command(command_id, success=False)
        raise InstallerCancelled("Installation cancelled")
    if process.returncode != 0:
        logger.finish_command(command_id, success=False)
        masked_error_cmd = _mask(" ".join(cmd_list))
        raise InstallerError(f"Command failed: {masked_error_cmd}")
    logger.finish_command(command_id, success=True)


def make_git_env() -> Dict[str, str]:
    """Create an environment dict for running git commands without interactive prompts.

    Returns
    -------
    dict
        Environment variables with GIT_TERMINAL_PROMPT=0 to prevent credential prompts.
    """
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def run_git_command(cmd: Iterable[str], logger: StructuredLogger, cwd: Optional[Path] = None,
                    task_id: Optional[int] = None, cancel_event: Optional[threading.Event] = None,
                    mask_values: Optional[Iterable[str]] = None) -> None:
    """Execute a git command with GIT_TERMINAL_PROMPT disabled to prevent credential prompts.

    Parameters
    ----------
    cmd : iterable of str
        Git command and arguments to execute.
    log_fn : Callable[[str], None]
        Function used to record each line of combined stdout/stderr.
    cwd : Path, optional
        Directory to run the command from.
    """
    env = make_git_env()
    run_command(cmd, logger, cwd=cwd, env=env, task_id=task_id, cancel_event=cancel_event, mask_values=mask_values)


def list_git_repo_files(repo_url: str, branch: str) -> List[str]:
    """List files at the root of a git repository.

    Parameters
    ----------
    repo_url : str
        Git repository URL (should already have token embedded if needed)
    branch : str
        Branch or tag to list files from

    Returns
    -------
    list of str
        List of filenames at the root of the repository
    """
    import tempfile
    temp_dir = Path(tempfile.mkdtemp(prefix="acq4_config_"))
    try:
        env = make_git_env()

        # Bare clone with depth 1
        result = subprocess.run(
            ["git", "clone", "--bare", "--depth", "1", "--single-branch", "--branch", branch, repo_url, str(temp_dir)],
            capture_output=True,
            text=True,
            env=env,
            timeout=60
        )

        if result.returncode != 0:
            raise InstallerError(f"Failed to clone repository: {result.stderr}")

        # List files at the root using git ls-tree
        result = subprocess.run(
            ["git", "--git-dir", str(temp_dir), "ls-tree", "HEAD"],
            capture_output=True,
            text=True,
            env=env,
            timeout=10
        )

        if result.returncode != 0:
            raise InstallerError(f"Failed to list repository files: {result.stderr}")

        # Parse output - format is: <mode> <type> <object> <file>
        # Only return blobs (files), not trees (directories)
        files = []
        for line in result.stdout.splitlines():
            parts = line.split(None, 3)
            if len(parts) >= 4:
                obj_type = parts[1]
                filename = parts[3]
                if obj_type == "blob" and not filename.startswith("."):
                    files.append(filename)
        return sorted(files)
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


class InstallWizard(QtWidgets.QWizard):
    def __init__(self, editable_map: Dict[str, EditableDependency], cli_args: argparse.Namespace,
                 test_flags: Optional[set[str]] = None) -> None:
        super().__init__()
        self.setWindowTitle("ACQ4 Installer")
        self.editable_map = editable_map
        self.cli_args = cli_args
        self.test_flags = test_flags or set()
        self.setOption(QtWidgets.QWizard.WizardOption.NoBackButtonOnStartPage, True)
        git_missing = "no-git" in self.test_flags or not is_git_available()
        self.git_page = GitPage() if git_missing else None
        self.location_page = LocationPage()
        self.dependencies_page = DependenciesPage(self.editable_map)
        self.config_page = ConfigPage()
        self.summary_page = SummaryPage()
        self.install_page = InstallPage()
        if self.git_page is not None:
            self.addPage(self.git_page)
        self.addPage(self.location_page)
        self.addPage(self.dependencies_page)
        self.addPage(self.config_page)
        self.addPage(self.summary_page)
        self.addPage(self.install_page)

        # Connect github token from LocationPage to ConfigPage's git_repo_widget
        self.location_page.github_token_edit.editingFinished.connect(
            lambda: self.config_page.git_repo_widget.set_github_token(
                self.location_page.github_token_edit.text().strip() or None
            )
        )

        self.apply_cli_arguments(cli_args)
        self._apply_default_size()

    def install_path(self) -> Path:
        raw_value = self.field("install_path")
        return Path(str(raw_value)).expanduser().resolve()

    def branch(self) -> str:
        raw_value = self.field("branch")
        value = str(raw_value).strip()
        return value or DEFAULT_BRANCH

    def repo_url(self) -> str:
        raw_value = self.field("repo_url")
        value = str(raw_value).strip()
        return value or ACQ4_REPO_URL

    def github_token(self) -> Optional[str]:
        raw_value = self.field("github_token")
        value = str(raw_value).strip()
        return value or None

    def selected_optional_specs(self) -> List[str]:
        return self.dependencies_page.selected_specs()

    def selected_editable_keys(self) -> List[str]:
        return self.dependencies_page.selected_clone_keys()

    def config_mode(self) -> str:
        if self.config_page.copy_radio.isChecked():
            return "copy"
        if self.config_page.clone_radio.isChecked():
            return "clone"
        return "new"

    def config_repo(self) -> Optional[str]:
        text = self.config_page.git_repo_widget.repo_url()
        return text or None

    def config_repo_branch(self) -> Optional[str]:
        text = self.config_page.git_repo_widget.branch()
        return text or None

    def config_copy_path(self) -> Optional[Path]:
        text = self.config_page.copy_path_edit.text().strip()
        if not text:
            return None
        return Path(text).expanduser().resolve()

    def config_file(self) -> Optional[str]:
        if self.config_page.clone_radio.isChecked():
            text = self.config_page.clone_config_file_combo.currentText().strip()
        elif self.config_page.copy_radio.isChecked():
            text = self.config_page.copy_config_file_combo.currentText().strip()
        else:
            text = ""
        return text or None

    def apply_cli_arguments(self, args: argparse.Namespace) -> None:
        self.location_page.apply_cli_args(args)
        self.dependencies_page.apply_cli_args(args)
        self.config_page.apply_cli_args(args)

    def cli_arguments(self, unattended: bool = False) -> List[str]:
        args: List[str] = []
        args.extend(self.location_page.cli_arguments())
        args.extend(self.dependencies_page.cli_arguments())
        args.extend(self.config_page.cli_arguments())
        if unattended:
            args.insert(0, "--unattended")
        return args

    def _apply_default_size(self) -> None:
        hint = self.sizeHint()
        width = hint.width() if hint.width() > 0 else 800
        height = hint.height() if hint.height() > 0 else 600
        self.resize(int(width * 1.5), int(height * 1.5))


class InstallerExecutor:
    """Shared implementation that performs all installer side effects."""

    def __init__(self, state: InstallerState, logger: StructuredLogger,
                 cancel_event: Optional[threading.Event] = None) -> None:
        self.state = state
        self.logger = logger
        self.cancel_event = cancel_event
        self._active_task_id: Optional[int] = None
        self._git_secrets: List[str] = [self.state.github_token] if self.state.github_token else []

    def run(self) -> None:
        base_dir = self.state.install_path
        clone_skip = normalized_clone_names(self.state.editable_selection)
        selected_optional_specs = resolve_selected_optional_specs(
            self.state.optional_dependencies,
            self.state.selected_optional,
            clone_skip,
        )
        conda_exe = find_conda_executable()
        env_dir = base_dir / CONDA_ENV_DIRNAME
        python_pkg = DEFAULT_PYTHON_VERSION
        tasks: List[tuple[str, Callable[[], None]]] = [
            ("Prepare install directory", lambda: self._prepare_install_dir(base_dir)),
            ("Clone ACQ4 repository", lambda: self._clone_acq4_repo(base_dir, self.state.repo_url, self.state.branch)),
            ("Create conda environment", lambda: self._create_conda_env(conda_exe, env_dir, python_pkg)),
            ("Install base conda packages", lambda: self._install_conda_packages(conda_exe, env_dir, DEFAULT_CONDA_PACKAGES, python_pkg)),
        ]
        if self.state.editable_selection:
            tasks.append(("Clone editable dependencies", lambda: self._handle_editable_dependencies(conda_exe, env_dir, base_dir)))
        tasks.extend([
            ("Install ACQ4 runtime dependencies", lambda: self._install_project_dependencies(conda_exe, env_dir, clone_skip, base_dir / ACQ4_SOURCE_DIRNAME)),
            ("Install ACQ4 package", lambda: self._install_acq4_package(conda_exe, env_dir, base_dir / ACQ4_SOURCE_DIRNAME)),
        ])
        if selected_optional_specs:
            tasks.append(("Install optional dependencies", lambda: self._install_optional_dependencies(conda_exe, env_dir, selected_optional_specs)))
        tasks.append(("Prepare configuration", lambda: self._prepare_config(base_dir)))
        if os.name == "nt" and self.state.create_desktop_shortcut:
            tasks.append(("Create desktop shortcut", lambda: self._create_shortcut_if_needed(base_dir, env_dir, conda_exe)))
        self.logger.set_task_total(len(tasks))
        for title, fn in tasks:
            self._run_task(title, fn)

    def _run_task(self, title: str, func: Callable[[], None]) -> None:
        self._ensure_not_cancelled()
        task_id = self.logger.start_task(title)
        previous = self._active_task_id
        self._active_task_id = task_id
        try:
            func()
        except Exception:  # noqa: BLE001
            self.logger.finish_task(task_id, success=False)
            raise
        else:
            self.logger.finish_task(task_id, success=True)
        finally:
            self._active_task_id = previous

    def _ensure_not_cancelled(self) -> None:
        if self.cancel_event and self.cancel_event.is_set():
            raise InstallerCancelled("Installation cancelled")

    def _prepare_install_dir(self, base_dir: Path) -> None:
        self.logger.message(f"Preparing install directory at {base_dir}", task_id=self._active_task_id)
        ensure_directory_empty(base_dir)

    def _clone_acq4_repo(self, base_dir: Path, repo_url: str, branch: str) -> None:
        dest = base_dir / ACQ4_SOURCE_DIRNAME
        self.logger.message(f"Cloning {repo_url} ({branch}) to {dest}", task_id=self._active_task_id)
        remote = github_url_with_token(repo_url, self.state.github_token)
        cmd = ["git", "clone", "--branch", branch, "--single-branch", remote, str(dest)]
        run_git_command(
            cmd,
            self.logger,
            task_id=self._active_task_id,
            cancel_event=self.cancel_event,
            mask_values=self._git_mask_values(),
        )

    def _create_conda_env(self, conda_exe: str, env_dir: Path, python_pkg: str) -> None:
        if env_dir.exists():
            raise InstallerError(f"Conda environment already exists at {env_dir}")
        self.logger.message("Creating base conda environment (this can take a while)...", task_id=self._active_task_id)
        cmd = [
            conda_exe,
            "create",
            "-y",
            "-p",
            str(env_dir),
            python_pkg,
            "pip",
        ]
        env = os.environ.copy()
        env["PYTHONNOUSERSITE"] = "1"
        run_command(cmd, self.logger, env=env, task_id=self._active_task_id, cancel_event=self.cancel_event)

    def _install_conda_packages(self, conda_exe: str, env_dir: Path, packages: List[str], python_pkg: str) -> None:
        remaining = [pkg for pkg in packages if pkg not in ("pip", python_pkg)]
        if not remaining:
            self.logger.message("No additional conda packages requested", task_id=self._active_task_id)
            return
        self.logger.message("Installing required conda packages...", task_id=self._active_task_id)
        cmd = [
            conda_exe,
            "install",
            "-y",
            "-p",
            str(env_dir),
            *remaining,
        ]
        run_command(cmd, self.logger, task_id=self._active_task_id, cancel_event=self.cancel_event)

    def _install_project_dependencies(self, conda_exe: str, env_dir: Path,
                                      skip_names: Iterable[str], repo_path: Path) -> None:
        deps = project_dependencies(repo_path=repo_path)
        skip_set = {name.lower() for name in skip_names}
        install_specs: List[str] = []
        for spec in deps:
            norm = normalize_spec_name(spec)
            if norm in skip_set:
                self.logger.message(f"Skipping dependency {spec} (editable clone selected)", task_id=self._active_task_id)
                continue
            install_specs.append(spec)
        if not install_specs:
            self.logger.message("No runtime dependencies to install", task_id=self._active_task_id)
            return
        self.logger.message("Installing ACQ4 runtime dependencies...", task_id=self._active_task_id)
        env = self._pip_env()
        cmd = [
            "python",
            "-u",
            "-m",
            "pip",
            "install",
            "--index-url=https://pypi.org/simple/",
            *install_specs,
        ]
        run_command(
            cmd,
            self.logger,
            env=env,
            task_id=self._active_task_id,
            cancel_event=self.cancel_event,
            conda_env=env_dir,
            conda_exe=conda_exe,
        )

    def _install_acq4_package(self, conda_exe: str, env_dir: Path, source_dir: Path) -> None:
        self.logger.message("Installing ACQ4 package in editable mode...", task_id=self._active_task_id)
        cmd = [
            "python",
            "-u",
            "-m",
            "pip",
            "install",
            "--index-url=https://pypi.org/simple/",
            "--no-deps",
            "-e",
            str(source_dir),
        ]
        env = self._pip_env()
        run_command(
            cmd,
            self.logger,
            env=env,
            task_id=self._active_task_id,
            cancel_event=self.cancel_event,
            conda_env=env_dir,
            conda_exe=conda_exe,
        )

    def _install_optional_dependencies(self, conda_exe: str, env_dir: Path, specs: List[str]) -> None:
        if not specs:
            self.logger.message("No optional dependencies selected", task_id=self._active_task_id)
            return
        self.logger.message("Installing optional dependencies via pip...", task_id=self._active_task_id)
        cmd = [
            "python",
            "-u",
            "-m",
            "pip",
            "install",
            "--index-url=https://pypi.org/simple/",
            *specs,
        ]
        env = self._pip_env()
        run_command(
            cmd,
            self.logger,
            env=env,
            task_id=self._active_task_id,
            cancel_event=self.cancel_event,
            conda_env=env_dir,
            conda_exe=conda_exe,
        )

    def _handle_editable_dependencies(self, conda_exe: str, env_dir: Path, base_dir: Path) -> None:
        if not self.state.editable_selection:
            self.logger.message("No editable dependencies selected", task_id=self._active_task_id)
            return
        dep_dir = base_dir / DEPENDENCIES_DIRNAME
        dep_dir.mkdir(parents=True, exist_ok=True)
        editable_map = editable_dependencies()
        for key in self.state.editable_selection:
            meta = editable_map.get(key)
            if not meta:
                continue
            repo_url = meta.git_url
            if not repo_url:
                self.logger.message(f"Skipping clone for {key}: repo URL not configured.", task_id=self._active_task_id)
                continue
            target = dep_dir / key
            self.logger.message(f"Cloning {meta.display_name or key} to {target}", task_id=self._active_task_id)
            remote = github_url_with_token(repo_url, self.state.github_token)
            cmd = ["git", "clone", remote, str(target)]
            run_git_command(
                cmd,
                self.logger,
                task_id=self._active_task_id,
                cancel_event=self.cancel_event,
                mask_values=self._git_mask_values(),
            )
            self.logger.message(f"Installing {meta.display_name or key} in editable mode", task_id=self._active_task_id)
            cmd = [
                "python",
                "-u",
                "-m",
                "pip",
                "install",
                "--index-url=https://pypi.org/simple/",
                "-e",
                str(target),
            ]
            env = self._pip_env()
            run_command(
                cmd,
                self.logger,
                env=env,
                task_id=self._active_task_id,
                cancel_event=self.cancel_event,
                conda_env=env_dir,
                conda_exe=conda_exe,
            )

    def _prepare_config(self, base_dir: Path) -> None:
        config_dir = base_dir / CONFIG_DIRNAME
        if config_dir.exists():
            raise InstallerError(f"Config directory already exists at {config_dir}")
        if self.state.config_mode == "clone" and self.state.config_repo_url:
            if not self.state.config_repo_branch:
                raise InstallerError("Config repository branch must be specified when cloning.")
            self.logger.message(
                f"Cloning configuration from {self.state.config_repo_url} ({self.state.config_repo_branch})",
                task_id=self._active_task_id
            )
            repo_with_token = github_url_with_token(self.state.config_repo_url, self.state.github_token)
            run_git_command(
                ["git", "clone", "--branch", self.state.config_repo_branch, "--single-branch", repo_with_token, str(config_dir)],
                self.logger,
                task_id=self._active_task_id,
                cancel_event=self.cancel_event,
                mask_values=self._git_mask_values(),
            )
        elif self.state.config_mode == "copy" and self.state.config_copy_path:
            source = self.state.config_copy_path
            if not source.exists() or not source.is_dir():
                raise InstallerError(f"Config path {source} does not exist or is not a directory.")
            self.logger.message(f"Copying configuration from {source}", task_id=self._active_task_id)
            shutil.copytree(source, config_dir)
        else:
            self.logger.message("Copying default configuration", task_id=self._active_task_id)
            source = base_dir / ACQ4_SOURCE_DIRNAME / "config" / "example"
            shutil.copytree(source, config_dir)

    def _create_shortcut_if_needed(self, base_dir: Path, env_dir: Path, conda_exe: str) -> None:
        if os.name != "nt":
            self.logger.message("Skipping shortcut creation on non-Windows platforms", task_id=self._active_task_id)
            return
        python_exe = env_dir / "python.exe"
        if not python_exe.exists():
            self.logger.message("python.exe not found in the environment; skipping shortcut creation",
                                task_id=self._active_task_id)
            return

        config_file_path = base_dir / CONFIG_DIRNAME / self.state.config_file

        self.logger.message("Creating start_acq4.bat launcher script", task_id=self._active_task_id)
        try:
            bat_path = create_start_bat(base_dir, conda_exe, env_dir, config_file_path)
        except Exception as e:
            self.logger.message(f"Failed to create bat file: {e}", task_id=self._active_task_id)
            return

        self.logger.message("Creating Windows desktop shortcut", task_id=self._active_task_id)
        try:
            create_desktop_shortcut_windows(bat_path, base_dir)
        except Exception as e:
            self.logger.message(f"Failed to create desktop shortcut: {e}", task_id=self._active_task_id)

    def _pip_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        return env

    def _git_mask_values(self) -> List[str]:
        return self._git_secrets


class _StreamPump:
    def __init__(self, stream: Optional[IO[str]], name: str,
                 output_queue: "queue.Queue[Tuple[str, Optional[str]]]") -> None:
        self.stream = stream
        self.name = name
        self.queue = output_queue
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        if self.stream is None:
            self.queue.put((self.name, None))
            return
        try:
            for line in self.stream:
                self.queue.put((self.name, line.rstrip("\n")))
        finally:
            self.queue.put((self.name, None))

    def join(self) -> None:
        self.thread.join()


class InstallerWorker(QtCore.QObject):
    log_event = QtCore.pyqtSignal(object)
    finished = QtCore.pyqtSignal(bool, str)

    def __init__(self, state: InstallerState) -> None:
        super().__init__()
        self.state = state
        self._cancel_event = threading.Event()

    def _queue_event(self, event: InstallerLogEvent) -> None:
        QtCore.QMetaObject.invokeMethod(
            self,
            "_emit_event",
            QtCore.Qt.ConnectionType.QueuedConnection,
            QtCore.Q_ARG(object, event)
        )

    @QtCore.pyqtSlot(object)
    def _emit_event(self, event: InstallerLogEvent) -> None:
        self.log_event.emit(event)

    def run(self) -> None:  # pragma: no cover - run in thread
        try:
            self._run_internal()
        except InstallerCancelled:
            QtCore.QMetaObject.invokeMethod(
                self,
                "_emit_finished",
                QtCore.Qt.ConnectionType.QueuedConnection,
                QtCore.Q_ARG(bool, False),
                QtCore.Q_ARG(str, "Installation cancelled"),
            )
        except Exception as exc:  # noqa: BLE001
            QtCore.QMetaObject.invokeMethod(
                self,
                "_emit_finished",
                QtCore.Qt.ConnectionType.QueuedConnection,
                QtCore.Q_ARG(bool, False),
                QtCore.Q_ARG(str, str(exc))
            )
        else:
            QtCore.QMetaObject.invokeMethod(
                self,
                "_emit_finished",
                QtCore.Qt.ConnectionType.QueuedConnection,
                QtCore.Q_ARG(bool, True),
                QtCore.Q_ARG(str, "Installation complete")
            )

    @QtCore.pyqtSlot(bool, str)
    def _emit_finished(self, success: bool, detail: str) -> None:
        self.finished.emit(success, detail)

    def _run_internal(self) -> None:
        logger = StructuredLogger(text_fn=None, event_handler=self._queue_event)
        executor = InstallerExecutor(self.state, logger, cancel_event=self._cancel_event)
        executor.run()

    def request_cancel(self) -> None:
        self._cancel_event.set()


def build_cli_parser() -> argparse.ArgumentParser:
    """Construct the CLI parser shared between GUI and unattended modes.

    Returns
    -------
    argparse.ArgumentParser
        Configured parser with all supported command-line switches.
    """
    parser = argparse.ArgumentParser(
        description="ACQ4 interactive installer",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    register_location_cli_arguments(parser)
    register_dependency_cli_arguments(parser)
    register_config_cli_arguments(parser)
    parser.add_argument(
        "--unattended",
        action="store_true",
        help="Run installer without showing the GUI (requires all options via CLI).",
    )
    parser.add_argument(
        "--test",
        dest="test_flags",
        help="Internal testing flag: comma-separated list of behaviors to simulate (e.g., no-git).",
    )
    return parser


def state_from_cli_args(args: argparse.Namespace,
                        editable_map: Dict[str, EditableDependency]) -> InstallerState:
    """Build an InstallerState instance from parsed CLI arguments.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI namespace.
    editable_map : dict
        Editable dependency descriptors used for CLI selection resolution.

    Returns
    -------
    InstallerState
        Fully-populated installer state ready for execution.
    """
    install_path_value = args.install_path or str((Path.home() / DEFAULT_INSTALL_DIR_NAME))
    install_path = Path(str(install_path_value)).expanduser().resolve()
    branch_value = (args.branch or DEFAULT_BRANCH).strip() or DEFAULT_BRANCH
    repo_value = (args.repo_url or ACQ4_REPO_URL).strip() or ACQ4_REPO_URL
    github_token = (args.github_token or "").strip() or None

    # Fetch pyproject.toml to get dependency information
    content, used_fallback = fetch_pyproject_from_github(repo_value, branch_value)
    if used_fallback:
        print(f"Warning: pyproject.toml not found in {repo_value} ({branch_value}).")
        print("Using dependency list from github.com/acq4/acq4:main instead.")
    dependency_groups = dependency_groups_from_pyproject(content=content)
    optional_dependencies = parse_optional_dependencies(content=content)

    selected_optional = resolve_optional_selection_from_args(args, optional_dependencies, dependency_groups)
    editable_selection = resolve_editable_selection_from_args(args, editable_map)
    # Parse config arguments
    config_repo = args.config_repo
    config_repo_branch = args.config_branch
    config_path_value = args.config_path
    config_copy_path = Path(str(config_path_value)).expanduser().resolve() if config_path_value else None
    config_file = args.config_file

    # Sanity check: can't specify both clone and copy options
    if config_repo and config_copy_path:
        raise InstallerError("Cannot specify both --config-repo and --config-path. Choose one configuration source.")

    # Infer mode and validate
    if config_repo:
        config_mode = "clone"
        if not config_repo_branch:
            raise InstallerError("--config-branch is required when using --config-repo.")
    elif config_copy_path:
        config_mode = "copy"
        if not config_copy_path.exists() or not config_copy_path.is_dir():
            raise InstallerError(f"Config path {config_copy_path} does not exist or is not a directory.")
    else:
        config_mode = "new"

    # Sanity check: --config-branch only makes sense with --config-repo
    if config_repo_branch and not config_repo:
        raise InstallerError("--config-branch requires --config-repo.")
    return InstallerState(
        install_path=install_path,
        branch=branch_value,
        repo_url=repo_value,
        github_token=github_token,
        optional_dependencies=optional_dependencies,
        selected_optional=selected_optional,
        editable_selection=editable_selection,
        config_mode=config_mode,
        config_repo_url=config_repo,
        config_repo_branch=config_repo_branch,
        config_copy_path=config_copy_path,
        config_file=config_file,
    )


def run_unattended_install(state: InstallerState) -> None:
    """Run the installer in unattended mode using stdout logging.

    Parameters
    ----------
    state : InstallerState
        Fully-resolved configuration describing what to install.
    """
    def log_text(message: str) -> None:
        print(message, flush=True)

    logger = StructuredLogger(text_fn=log_text)
    executor = InstallerExecutor(state, logger)
    try:
        executor.run()
    except Exception as exc:  # noqa: BLE001
        print(f"Installation failed: {exc}", file=sys.stderr)
        sys.exit(1)
    else:
        print("Installation complete", flush=True)

        # Display post-install documentation
        packages_with_docs: List[Tuple[str, str]] = []
        selected_specs = set(state.selected_optional)
        for dep in state.optional_dependencies:
            if dep.spec in selected_specs and dep.post_install_doc:
                display_name = dep.display_name or dep.spec
                # Strip HTML tags for plain text output
                plain_doc = re.sub(r'<a href=[\'"]([^\'"]+)[\'"]>([^<]+)</a>', r'\2 (\1)', dep.post_install_doc)
                plain_doc = re.sub(r'<[^>]+>', '', plain_doc)
                packages_with_docs.append((display_name, plain_doc))

        if packages_with_docs:
            print("\nThe following packages require additional 3rd-party software to be installed:")
            for name, doc in packages_with_docs:
                print(f"  - {name}: {doc}")


def normalized_clone_names(selection: Iterable[str]) -> set[str]:
    """Return a lowercase set of dependency identifiers chosen for cloning."""
    return {item.strip().lower() for item in selection}


def resolve_selected_optional_specs(options: Iterable[DependencyOption], selected_specs: Iterable[str],
                                    skip_names: Iterable[str]) -> List[str]:
    """Filter selected optional specs to drop ones handled via editable clones."""
    spec_set = set(selected_specs)
    skip = {name.lower() for name in skip_names}
    result: List[str] = []
    for dep in options:
        if dep.spec in spec_set and dep.normalized_name not in skip:
            result.append(dep.spec)
    return result


def collect_state(wizard: InstallWizard) -> InstallerState:
    """Capture the installer wizard selections into a serializable state."""
    return InstallerState(
        install_path=wizard.install_path(),
        branch=wizard.branch(),
        repo_url=wizard.repo_url(),
        github_token=wizard.github_token(),
        optional_dependencies=wizard.dependencies_page.options,
        selected_optional=wizard.selected_optional_specs(),
        editable_selection=wizard.selected_editable_keys(),
        config_mode=wizard.config_mode(),
        config_repo_url=wizard.config_repo(),
        config_repo_branch=wizard.config_repo_branch(),
        config_copy_path=wizard.config_copy_path(),
        config_file=wizard.config_file(),
        create_desktop_shortcut=wizard.dependencies_page.create_shortcut_checkbox.isChecked(),
    )


def parse_test_flags(raw_flags: Optional[str]) -> set[str]:
    return {flag.strip().lower() for flag in (raw_flags or "").split(",") if flag.strip()}


def main() -> None:
    """Entry point for the ACQ4 installer."""
    editable_map = editable_dependencies()
    parser = build_cli_parser()
    args = parser.parse_args()
    test_flags = parse_test_flags(args.test_flags)
    if args.unattended:
        try:
            state = state_from_cli_args(args, editable_map)
        except InstallerError as exc:
            print(f"Invalid unattended configuration: {exc}", file=sys.stderr)
            sys.exit(1)
        run_unattended_install(state)
        return
    app = QtWidgets.QApplication(sys.argv)
    wizard = InstallWizard(editable_map, args, test_flags)
    wizard.exec()
    sys.exit(0)


if __name__ == "__main__":
    main()
