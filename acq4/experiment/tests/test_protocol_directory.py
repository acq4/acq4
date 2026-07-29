"""Tests for ProtocolDirectory, which scans an operator's protocol directory
for .py files and holds a ProtocolFile per discovered file, including failed ones."""
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
