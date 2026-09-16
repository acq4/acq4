"""Tests for ProtocolDirectory, which scans an operator's protocol directory
-- and any read-only `extra_paths` alongside it -- for .py files and holds a
ProtocolFile per discovered file, including failed ones."""
import os
import textwrap

import pytest

from acq4.experiment.protocol_directory import ProtocolDirectory


def _write(dir_path, name, body):
    path = dir_path / name
    path.write_text(textwrap.dedent(body))
    return str(path)


def test_scan_discovers_py_files(tmp_path):
    _write(tmp_path, "one.py", """
        def run(ctx, **params):
            return "done"
    """)
    _write(tmp_path, "two.py", """
        def run(ctx, **params):
            return "done"
    """)
    pd = ProtocolDirectory(str(tmp_path))
    pd.scan()
    assert set(pd.protocols.keys()) == {"one", "two"}
    assert pd.protocols["one"].is_loaded is True
    assert pd.protocols["two"].is_loaded is True


def test_non_py_files_ignored(tmp_path):
    _write(tmp_path, "one.py", """
        def run(ctx, **params):
            return "done"
    """)
    (tmp_path / "notes.txt").write_text("not a protocol")
    (tmp_path / "data.json").write_text("{}")
    pd = ProtocolDirectory(str(tmp_path))
    pd.scan()
    assert set(pd.protocols.keys()) == {"one"}


def test_underscore_prefixed_files_ignored(tmp_path):
    _write(tmp_path, "one.py", """
        def run(ctx, **params):
            return "done"
    """)
    _write(tmp_path, "__init__.py", "")
    _write(tmp_path, "_helper.py", "def helper(): return 1\n")
    pd = ProtocolDirectory(str(tmp_path))
    pd.scan()
    assert set(pd.protocols.keys()) == {"one"}


def test_bad_file_recorded_not_raised_alongside_good(tmp_path):
    _write(tmp_path, "good.py", """
        def run(ctx, **params):
            return "done"
    """)
    _write(tmp_path, "bad.py", "this is not valid python !!!")
    pd = ProtocolDirectory(str(tmp_path))
    pd.scan()  # must not raise
    assert set(pd.protocols.keys()) == {"good", "bad"}
    assert pd.protocols["good"].is_loaded is True
    assert pd.protocols["bad"].is_loaded is False
    assert pd.protocols["bad"].load_error is not None


def test_rescan_picks_up_new_file(tmp_path):
    _write(tmp_path, "one.py", """
        def run(ctx, **params):
            return "done"
    """)
    pd = ProtocolDirectory(str(tmp_path))
    pd.scan()
    assert set(pd.protocols.keys()) == {"one"}

    _write(tmp_path, "two.py", """
        def run(ctx, **params):
            return "done"
    """)
    pd.scan()
    assert set(pd.protocols.keys()) == {"one", "two"}


def test_rescan_drops_deleted_file(tmp_path):
    _write(tmp_path, "one.py", """
        def run(ctx, **params):
            return "done"
    """)
    path_two = _write(tmp_path, "two.py", """
        def run(ctx, **params):
            return "done"
    """)
    pd = ProtocolDirectory(str(tmp_path))
    pd.scan()
    assert set(pd.protocols.keys()) == {"one", "two"}

    os.remove(path_two)
    pd.scan()
    assert set(pd.protocols.keys()) == {"one"}


def test_get_returns_protocol_file(tmp_path):
    _write(tmp_path, "one.py", """
        def run(ctx, **params):
            return "done"
    """)
    pd = ProtocolDirectory(str(tmp_path))
    pd.scan()
    pf = pd.get("one")
    assert pf.name == "one"
    assert pf.is_loaded is True


def test_get_missing_name_raises_key_error(tmp_path):
    pd = ProtocolDirectory(str(tmp_path))
    pd.scan()
    with pytest.raises(KeyError):
        pd.get("nope")


def test_reload_missing_name_raises_key_error(tmp_path):
    pd = ProtocolDirectory(str(tmp_path))
    pd.scan()
    with pytest.raises(KeyError):
        pd.reload("nope")


def test_reload_reloads_single_protocol(tmp_path):
    path = _write(tmp_path, "one.py", """
        PARAMS = [dict(name="count", type="int", default=3)]

        def run(ctx, **params):
            return "done"
    """)
    pd = ProtocolDirectory(str(tmp_path))
    pd.scan()
    assert pd.get("one").param_values() == {"count": 3}

    _write(tmp_path, "one.py", """
        PARAMS = [dict(name="count", type="int", default=9)]

        def run(ctx, **params):
            return "done"
    """)
    pd.reload("one")
    assert pd.get("one").param_values() == {"count": 9}


def test_reload_all_is_alias_for_scan(tmp_path):
    _write(tmp_path, "one.py", """
        def run(ctx, **params):
            return "done"
    """)
    pd = ProtocolDirectory(str(tmp_path))
    pd.reload_all()
    assert set(pd.protocols.keys()) == {"one"}

    _write(tmp_path, "two.py", """
        def run(ctx, **params):
            return "done"
    """)
    pd.reload_all()
    assert set(pd.protocols.keys()) == {"one", "two"}


def test_scan_on_nonexistent_directory_is_noop(tmp_path):
    missing = str(tmp_path / "does_not_exist")
    pd = ProtocolDirectory(missing)
    pd.scan()  # must not raise
    assert pd.protocols == {}


def test_scan_on_non_directory_path_is_noop(tmp_path):
    file_path = tmp_path / "not_a_dir.py"
    file_path.write_text("x = 1\n")
    pd = ProtocolDirectory(str(file_path))
    pd.scan()  # must not raise
    assert pd.protocols == {}


def test_scan_does_not_reload_an_already_loaded_protocol(tmp_path):
    """Reproduces the operator-facing bug: opening the protocol picker's
    dropdown (which calls scan() for discovery) must not silently replace an
    edited, already-loaded ProtocolFile's param_tree with fresh defaults."""
    _write(tmp_path, "one.py", """
        PARAMS = [dict(name="speed", type="str", default="fast")]

        def run(ctx, **params):
            return "done"
    """)
    pd = ProtocolDirectory(str(tmp_path))
    pd.scan()
    protocol = pd.get("one")
    assert protocol.param_values() == {"speed": "fast"}

    # Operator edits the live param tree (e.g. via the ParameterTree widget).
    protocol.param_tree.child("speed").setValue("slow")
    assert protocol.param_values() == {"speed": "slow"}

    # Discovery-only rescan (e.g. from opening the dropdown) must not touch it.
    pd.scan()
    assert pd.get("one") is protocol
    assert protocol.param_values() == {"speed": "slow"}


def test_scan_reimports_a_file_whose_contents_changed_on_disk(tmp_path):
    """Design 2.6: opening the protocol selector (scan()) must re-import a
    file whose contents changed on disk since it was last loaded -- an
    operator's edit -- even though an already-loaded protocol whose file is
    otherwise unchanged is left untouched (test_scan_does_not_reload_an_
    already_loaded_protocol, above)."""
    path = _write(tmp_path, "one.py", """
        PARAMS = [dict(name="speed", type="str", default="fast")]

        def run(ctx, **params):
            return "done"
    """)
    pd = ProtocolDirectory(str(tmp_path))
    pd.scan()
    assert pd.get("one").param_values() == {"speed": "fast"}

    _write(tmp_path, "one.py", """
        PARAMS = [dict(name="speed", type="str", default="slow")]

        def run(ctx, **params):
            return "done"
    """)
    # Force the mtime forward so this reproduces reliably regardless of the
    # filesystem's mtime resolution (which can be as coarse as one second).
    newer = os.stat(path).st_mtime + 2
    os.utime(path, (newer, newer))

    pd.scan()
    assert pd.get("one").param_values() == {"speed": "slow"}


def test_reload_all_does_reset_an_edited_param_tree(tmp_path):
    """reload_all() (the explicit Reload button) is the force-reload path, so
    it SHOULD reset an edited param tree back to the file's defaults."""
    _write(tmp_path, "one.py", """
        PARAMS = [dict(name="speed", type="str", default="fast")]

        def run(ctx, **params):
            return "done"
    """)
    pd = ProtocolDirectory(str(tmp_path))
    pd.scan()
    protocol = pd.get("one")
    protocol.param_tree.child("speed").setValue("slow")
    assert protocol.param_values() == {"speed": "slow"}

    pd.reload_all()
    assert pd.get("one").param_values() == {"speed": "fast"}


def test_scan_still_retries_a_previously_failed_load(tmp_path):
    """A protocol that failed to import must still be retried on the next
    discovery scan -- only successfully-loaded protocols are left alone."""
    path = _write(tmp_path, "bad.py", "this is not valid python !!!")
    pd = ProtocolDirectory(str(tmp_path))
    pd.scan()
    assert pd.get("bad").is_loaded is False

    with open(path, "w") as fh:
        fh.write("def run(ctx, **params):\n    return 'done'\n")
    pd.scan()
    assert pd.get("bad").is_loaded is True


# A minimal loadable protocol body, for the tests below whose subject is which
# directory a name resolves to rather than what is in the file.
RUN = """
        def run(ctx, **params):
            return "done"
    """


# --- extra_paths: read-only directories searched after the operator's own ----
#
# This is how the bundled example protocols reach the picker without being
# copied into a rig's config directory, where the copy would silently drift
# from the one in the repo. See acq4.modules.Autopatch.example_protocols.


def test_scan_discovers_protocols_in_an_extra_path(tmp_path):
    own = tmp_path / "own"
    own.mkdir()
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write(own, "mine.py", RUN)
    _write(bundled, "theirs.py", RUN)

    pd = ProtocolDirectory(str(own), extra_paths=[str(bundled)])
    pd.scan()

    assert set(pd.protocols.keys()) == {"mine", "theirs"}
    assert pd.get("theirs").path == str(bundled / "theirs.py")


def test_the_primary_path_shadows_an_extra_path_of_the_same_name(tmp_path):
    """Precedence is what lets an operator keep their own version of a bundled
    protocol: same name in their own directory, and theirs is the one that
    loads."""
    own = tmp_path / "own"
    own.mkdir()
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write(own, "shared.py", RUN)
    _write(bundled, "shared.py", RUN)

    pd = ProtocolDirectory(str(own), extra_paths=[str(bundled)])
    pd.scan()

    assert set(pd.protocols.keys()) == {"shared"}
    assert pd.get("shared").path == str(own / "shared.py")


def test_earlier_extra_paths_win_over_later_ones(tmp_path):
    first = tmp_path / "first"
    first.mkdir()
    second = tmp_path / "second"
    second.mkdir()
    _write(first, "shared.py", RUN)
    _write(second, "shared.py", RUN)

    pd = ProtocolDirectory(str(tmp_path / "own"), extra_paths=[str(first), str(second)])
    pd.scan()

    assert pd.get("shared").path == str(first / "shared.py")


def test_removing_a_shadowing_file_falls_back_to_the_extra_path(tmp_path):
    """The other half of shadowing, and the reason _discover() compares paths
    rather than only mtimes: deleting the operator's copy must hand the name
    back to the bundled file, not leave a ProtocolFile pointing at a file that
    is gone."""
    own = tmp_path / "own"
    own.mkdir()
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    own_path = _write(own, "shared.py", RUN)
    _write(bundled, "shared.py", RUN)

    pd = ProtocolDirectory(str(own), extra_paths=[str(bundled)])
    pd.scan()
    assert pd.get("shared").path == own_path

    os.remove(own_path)
    pd.scan()

    assert pd.get("shared").path == str(bundled / "shared.py")
    assert pd.get("shared").is_loaded is True


def test_a_new_shadowing_file_takes_over_the_name_on_the_next_scan(tmp_path):
    own = tmp_path / "own"
    own.mkdir()
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write(bundled, "shared.py", RUN)

    pd = ProtocolDirectory(str(own), extra_paths=[str(bundled)])
    pd.scan()
    assert pd.get("shared").path == str(bundled / "shared.py")

    own_path = _write(own, "shared.py", RUN)
    pd.scan()

    assert pd.get("shared").path == own_path
    assert pd.get("shared").is_loaded is True


def test_a_missing_primary_path_does_not_hide_the_extra_paths(tmp_path):
    """A rig whose protocol directory does not exist yet must still see the
    bundled protocols -- this is the first-run case."""
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write(bundled, "theirs.py", RUN)

    pd = ProtocolDirectory(str(tmp_path / "does_not_exist"), extra_paths=[str(bundled)])
    pd.scan()

    assert set(pd.protocols.keys()) == {"theirs"}


def test_a_missing_extra_path_is_skipped_rather_than_raising(tmp_path):
    own = tmp_path / "own"
    own.mkdir()
    _write(own, "mine.py", RUN)

    pd = ProtocolDirectory(str(own), extra_paths=[str(tmp_path / "nope")])
    pd.scan()  # must not raise

    assert set(pd.protocols.keys()) == {"mine"}


def test_scan_leaves_an_already_loaded_extra_path_protocol_alone(tmp_path):
    """The no-clobber rule of scan() applies to extra paths too: a live, edited
    param tree survives a rescan."""
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write(bundled, "one.py", """
        PARAMS = [dict(name="speed", type="str", default="fast")]

        def run(ctx, **params):
            return "done"
    """)
    pd = ProtocolDirectory(str(tmp_path / "own"), extra_paths=[str(bundled)])
    pd.scan()
    pd.get("one").param_tree.child("speed").setValue("slow")

    pd.scan()

    assert pd.get("one").param_values() == {"speed": "slow"}


def test_search_paths_reports_the_primary_path_first(tmp_path):
    pd = ProtocolDirectory("own", extra_paths=["a", "b"])
    assert pd.search_paths == ["own", "a", "b"]


def test_extra_paths_defaults_to_none_so_a_single_dir_still_works(tmp_path):
    _write(tmp_path, "one.py", RUN)
    pd = ProtocolDirectory(str(tmp_path))
    pd.scan()

    assert set(pd.protocols.keys()) == {"one"}
    assert pd.search_paths == [str(tmp_path)]
