"""Tests for code provenance capture: git state, protocol hash, per-slice patch dumps."""

import hashlib
import random
import subprocess

import pytest

import acq4.util.DataManager as dm
from acq4.experiment.context import ExecutionContext
from acq4.experiment.orchestrator import Orchestrator
from acq4.experiment.protocol_file import ProtocolFile
from acq4.experiment.tests.test_actions_prompt_storage import FakeManager
from acq4.experiment.tests.test_orchestrator_producer import make_producer
from acq4.modules.Autopatch.performance_tuning import provenance
from acq4.util import tuning_points
from acq4.util.tests.memory_ledger import MemoryLedger
from acq4.util.tuning_points import Point, Runtime

CELL_POINT = "test_provenance_cell_value"


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture(autouse=True)
def fresh_memo():
    provenance._memo.clear()
    yield
    provenance._memo.clear()


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "repo"
    path.mkdir()
    _git(path, "init", "-q", "-b", "trunk")
    (path / "tracked.txt").write_text("one\n")
    _git(path, "add", "tracked.txt")
    _git(
        path,
        "-c",
        "user.name=T",
        "-c",
        "user.email=t@example.com",
        "commit",
        "-q",
        "-m",
        "first",
    )
    return path


def test_clean_state(repo):
    assert provenance.repo_state(str(repo)) == {
        "sha": _git(repo, "rev-parse", "HEAD"),
        "branch": "trunk",
        "dirty": False,
    }


def test_dirty_after_editing_tracked_file(repo):
    (repo / "tracked.txt").write_text("two\n")
    assert provenance.repo_state(str(repo))["dirty"] is True


def test_untracked_file_is_not_dirty(repo):
    (repo / "new.txt").write_text("x\n")
    assert provenance.repo_state(str(repo))["dirty"] is False


def test_non_git_dir_is_none(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert provenance.repo_state(str(plain)) is None


def test_memoized_within_sixty_seconds(repo):
    first = provenance.repo_state(str(repo), now=1000.0)
    (repo / "tracked.txt").write_text("two\n")
    _git(
        repo,
        "-c",
        "user.name=T",
        "-c",
        "user.email=t@example.com",
        "commit",
        "-q",
        "-am",
        "second",
    )
    assert provenance.repo_state(str(repo), now=1059.0) == first
    later = provenance.repo_state(str(repo), now=1061.0)
    assert later["sha"] == _git(repo, "rev-parse", "HEAD") != first["sha"]


def test_capture_hashes_protocol_bytes(repo, tmp_path):
    protocol = tmp_path / "protocol.py"
    protocol.write_bytes(b"def run(ctx):\n    pass\n")
    captured = provenance.capture(str(protocol), str(repo))
    assert (
        captured["protocol_sha256"] == hashlib.sha256(protocol.read_bytes()).hexdigest()
    )
    assert captured["config"] == provenance.repo_state(str(repo))
    assert set(captured["acq4"]) == {"sha", "branch", "dirty"}


def test_capture_raises_for_missing_protocol(repo, tmp_path):
    with pytest.raises(FileNotFoundError):
        provenance.capture(str(tmp_path / "absent.py"), str(repo))


def test_patch_dumped_once_and_not_overwritten(repo, tmp_path):
    (repo / "tracked.txt").write_text("two\n")
    slice_dir = tmp_path / "slice"
    slice_dir.mkdir()
    states = {"acq4": provenance.repo_state(str(repo)), "config": None}
    roots = {"acq4": str(repo), "config": None}

    provenance.dump_patches(str(slice_dir), states, roots)

    patch = slice_dir / "performance_tuning_acq4.patch"
    assert "+two" in patch.read_text()
    assert not (slice_dir / "performance_tuning_config.patch").exists()

    patch.write_text("sentinel")
    provenance.dump_patches(str(slice_dir), states, roots)
    assert patch.read_text() == "sentinel"


def test_clean_repo_gets_no_patch(repo, tmp_path):
    states = {"acq4": provenance.repo_state(str(repo))}
    provenance.dump_patches(str(tmp_path), states, {"acq4": str(repo)})
    assert not (tmp_path / "performance_tuning_acq4.patch").exists()


def _commit(repo, message):
    _git(
        repo,
        "-c",
        "user.name=T",
        "-c",
        "user.email=t@example.com",
        "commit",
        "-q",
        "-m",
        message,
    )


@pytest.fixture
def acq4_like_repo(repo):
    """A repo holding the tuning bookkeeping files at the same paths they have in the acq4 checkout."""
    files = [repo / p for p in provenance.bookkeeping_paths()]
    for path in files:
        if path.suffix:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("original\n")
        else:
            path.mkdir(parents=True)
            (path / "001-x").mkdir()
            path = path / "001-x" / "trial.yaml"
            path.write_text("original\n")
    _git(repo, "add", "-A")
    _commit(repo, "bookkeeping")
    return repo


def _edit_bookkeeping(repo):
    for p in provenance.bookkeeping_paths():
        path = repo / p
        if path.is_dir():
            path = path / "001-x" / "trial.yaml"
        path.write_text("edited by tuning\n")


def _acq4_states(repo):
    state = provenance.repo_state(str(repo), excluded=provenance.excluded_paths("acq4"))
    return {"acq4": state}, {"acq4": str(repo)}


def test_bookkeeping_paths_are_the_tuning_records_relative_to_the_acq4_root():
    assert provenance.bookkeeping_paths() == (
        "acq4/modules/Autopatch/performance_tuning/factors.yaml",
        "acq4/modules/Autopatch/performance_tuning/tracking.md",
        "acq4/modules/Autopatch/performance_tuning/trials",
    )


def test_editing_only_bookkeeping_is_not_dirty_and_gets_no_patch(
    acq4_like_repo, tmp_path
):
    _edit_bookkeeping(acq4_like_repo)
    states, roots = _acq4_states(acq4_like_repo)
    assert states["acq4"]["dirty"] is False
    slice_dir = tmp_path / "slice"
    slice_dir.mkdir()
    provenance.dump_patches(str(slice_dir), states, roots)
    assert list(slice_dir.iterdir()) == []


def test_other_edits_are_dirty_and_their_patch_leaves_out_bookkeeping(
    acq4_like_repo, tmp_path
):
    _edit_bookkeeping(acq4_like_repo)
    (acq4_like_repo / "tracked.txt").write_text("two\n")
    states, roots = _acq4_states(acq4_like_repo)
    assert states["acq4"]["dirty"] is True
    slice_dir = tmp_path / "slice"
    slice_dir.mkdir()
    provenance.dump_patches(str(slice_dir), states, roots)
    patch = (slice_dir / "performance_tuning_acq4.patch").read_text()
    assert "+two" in patch
    assert "edited by tuning" not in patch
    assert "performance_tuning/" not in patch


def test_capture_applies_the_bookkeeping_exclusion_to_acq4_only(repo, tmp_path):
    protocol = tmp_path / "protocol.py"
    protocol.write_text("")
    captured = provenance.capture(str(protocol), str(repo))
    assert captured["acq4"] == provenance.repo_state(
        provenance._acq4_root(), excluded=provenance.excluded_paths("acq4")
    )
    assert provenance.excluded_paths("config") == ()


def test_a_failing_diff_writes_no_patch_and_a_later_one_does(tmp_path):
    unborn = tmp_path / "unborn"
    unborn.mkdir()
    _git(unborn, "init", "-q", "-b", "trunk")
    (unborn / "tracked.txt").write_text("one\n")
    _git(unborn, "add", "tracked.txt")
    slice_dir = tmp_path / "slice"
    slice_dir.mkdir()
    states = {"config": {"sha": "none", "branch": "trunk", "dirty": True}}
    roots = {"config": str(unborn)}

    provenance.dump_patches(str(slice_dir), states, roots)
    assert not (slice_dir / "performance_tuning_config.patch").exists()

    _commit(unborn, "first")
    (unborn / "tracked.txt").write_text("two\n")
    provenance.dump_patches(str(slice_dir), states, roots)
    assert "+two" in (slice_dir / "performance_tuning_config.patch").read_text()


@pytest.fixture
def protocol_file(tmp_path):
    path = tmp_path / "protocol.py"
    path.write_text("PARAMS = []\n\n\ndef run(ctx, **kwargs):\n    return None\n")
    pf = ProtocolFile(str(path))
    pf.load()
    return pf


class CellMutator:
    name = "cell_mut"
    unit = "cell"
    answers = {CELL_POINT}
    conditions = ["x", "y"]

    def eligible(self, facts):
        return True

    def value(self, point, default, condition, facts):
        return condition


class Cell:
    def __repr__(self):
        return "<cell c0>"


def test_hook_output_lands_in_cell_metadata(repo, tmp_path, protocol_file, monkeypatch):
    monkeypatch.setitem(
        tuning_points.POINTS,
        CELL_POINT,
        Point("value", "cell", (), "Test-only cell point.", "test"),
    )
    (repo / "tracked.txt").write_text("dirty\n")
    root = dm.getDirHandle(str(tmp_path / "data"), create=True)
    slice_dir = root.mkdir("slice_000", info={"dirType": "Slice"})
    hook = provenance.make_cell_close_hook(protocol_file.path, str(repo))
    tuning_points.install(
        Runtime(
            "run-1",
            [CellMutator()],
            MemoryLedger(random.Random(0)),
            cell_close_hook=hook,
        )
    )
    sliceUnit = tuning_points.open_unit("slice", slice_dir=slice_dir)
    cellDirs = {}
    cell = Cell()

    def run(ctx, **kwargs):
        cellDirs[ctx.cell] = ctx.manager.getCurrentDir()
        tuning_points.value(CELL_POINT, None)

    protocol_file.run = run
    manager = FakeManager(slice_dir)
    try:
        Orchestrator(
            protocol_file,
            manager=manager,
            contextFactory=lambda c: ExecutionContext(cell=c, manager=manager),
            cellProducer=make_producer([[cell], None]),
        ).run_sync()
        tuning_points.close_unit(sliceUnit)
    finally:
        tuning_points.uninstall()

    block = cellDirs[cell].info()["performance_tuning"]["provenance"]
    assert set(block) == {"acq4", "config", "protocol_sha256"}
    assert block["config"]["dirty"] is True
    assert block["config"]["branch"] == "trunk"
    assert (
        "+dirty"
        in (
            tmp_path / "data" / "slice_000" / "performance_tuning_config.patch"
        ).read_text()
    )


def test_hook_without_a_slice_dir_still_records_provenance(repo, tmp_path):
    protocol = tmp_path / "protocol.py"
    protocol.write_text("x = 1\n")
    (repo / "tracked.txt").write_text("dirty\n")
    cell_dir = dm.getDirHandle(str(tmp_path / "loose"), create=True)

    block = provenance.make_cell_close_hook(str(protocol), str(repo))(cell_dir)

    assert block["config"]["dirty"] is True
    assert not list((tmp_path / "loose").glob("*.patch"))
