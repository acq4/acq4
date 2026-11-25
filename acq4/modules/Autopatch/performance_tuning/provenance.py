"""Code provenance for tuned cells: git state of acq4 and the rig config, protocol hash, per-slice patches."""

import hashlib
import os
import subprocess
import time

import acq4

from . import catalogue, record, tracking

MEMO_SECONDS = 60
_memo = {}


def _git(path, *args):
    return subprocess.run(
        ["git", "-C", path, *args], capture_output=True, text=True, check=False
    )


def repo_state(path, now=None, excluded=()):
    now = time.monotonic() if now is None else now
    key = (path, tuple(excluded))
    cached = _memo.get(key)
    if cached is not None and now - cached[0] <= MEMO_SECONDS:
        return cached[1]
    state = _read_state(path, excluded)
    _memo[key] = (now, state)
    return state


def _read_state(path, excluded):
    sha = _git(path, "rev-parse", "HEAD")
    if sha.returncode != 0:
        return None
    branch = _git(path, "rev-parse", "--abbrev-ref", "HEAD")
    status = _git(path, "status", "--porcelain", "-uno", "--", *excluded)
    return {
        "sha": sha.stdout.strip(),
        "branch": branch.stdout.strip(),
        "dirty": bool(status.stdout.strip()),
    }


def _acq4_root():
    path = os.path.dirname(os.path.abspath(acq4.__file__))
    while not os.path.exists(os.path.join(path, ".git")):
        parent = os.path.dirname(path)
        if parent == path:
            return os.path.dirname(os.path.abspath(acq4.__file__))
        path = parent
    return path


def bookkeeping_paths():
    """The tuning records that scaffold, accept, abandon and arm rewrite, relative to the acq4 root."""
    root = _acq4_root()
    return tuple(
        os.path.relpath(path, root)
        for path in (catalogue.DEFAULT_PATH, tracking.DEFAULT_OUT, record.TRIALS_DIR)
    )


def excluded_paths(name):
    """Git pathspecs that keep a repo's tuning bookkeeping out of its dirty check and patch."""
    if name != "acq4":
        return ()
    return tuple(f":(exclude){path}" for path in bookkeeping_paths())


def _roots(config_dir):
    return {"acq4": _acq4_root(), "config": config_dir}


def _capture_states(config_dir):
    roots = _roots(config_dir)
    states = {
        name: repo_state(root, excluded=excluded_paths(name))
        for name, root in roots.items()
    }
    return states, roots


def capture(protocol_path, config_dir):
    with open(protocol_path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    states, _ = _capture_states(config_dir)
    return {**states, "protocol_sha256": digest}


def dump_patches(slice_dir_path, states, roots):
    for name, state in states.items():
        if state is None or not state["dirty"]:
            continue
        target = os.path.join(slice_dir_path, f"performance_tuning_{name}.patch")
        if os.path.exists(target):
            continue
        diff = _git(roots[name], "diff", "HEAD", "--", *excluded_paths(name))
        if diff.returncode != 0 or not diff.stdout:
            continue
        with open(target, "w") as f:
            f.write(diff.stdout)


def _enclosing_slice_dir(cell_dir):
    d = cell_dir
    while True:
        if d.info().get("dirType") == "Slice":
            return d
        parent = d.parent()
        if parent.name() == d.name():
            return None
        d = parent


def make_cell_close_hook(protocol_path, config_dir):
    def hook(cell_dir):
        provenance = capture(protocol_path, config_dir)
        slice_dir = _enclosing_slice_dir(cell_dir)
        if slice_dir is not None:
            states = {k: provenance[k] for k in ("acq4", "config")}
            dump_patches(slice_dir.name(), states, _roots(config_dir))
        return provenance

    return hook
