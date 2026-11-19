"""Code provenance for tuned cells: git state of acq4 and the rig config, protocol hash, per-slice patches."""

import hashlib
import os
import subprocess
import time

import acq4

MEMO_SECONDS = 60
_memo = {}


def _git(path, *args):
    return subprocess.run(
        ["git", "-C", path, *args], capture_output=True, text=True, check=False
    )


def repo_state(path, now=None):
    now = time.monotonic() if now is None else now
    cached = _memo.get(path)
    if cached is not None and now - cached[0] <= MEMO_SECONDS:
        return cached[1]
    state = _read_state(path)
    _memo[path] = (now, state)
    return state


def _read_state(path):
    sha = _git(path, "rev-parse", "HEAD")
    if sha.returncode != 0:
        return None
    branch = _git(path, "rev-parse", "--abbrev-ref", "HEAD")
    status = _git(path, "status", "--porcelain", "-uno")
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


def _roots(config_dir):
    return {"acq4": _acq4_root(), "config": config_dir}


def _capture_states(config_dir):
    roots = _roots(config_dir)
    return {name: repo_state(root) for name, root in roots.items()}, roots


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
        diff = _git(roots[name], "diff", "HEAD")
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
