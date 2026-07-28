"""Tests for ProtocolFile, the .py protocol file loader (imports a file fresh on
load(), extracting run(), PARAMS, and the module docstring)."""
import textwrap

import pytest

from acq4.experiment.protocol_file import ProtocolFile, ProtocolLoadError


def _write(tmp_path, name, body):
    path = tmp_path / name
    path.write_text(textwrap.dedent(body))
    return str(path)


def test_valid_file_loads(tmp_path):
    path = _write(tmp_path, "good.py", '''
        """Does a thing."""
        def run(ctx, **params):
            return "done"
    ''')
    pf = ProtocolFile(path)
    pf.load()
    assert pf.name == "good"
    assert pf.description == "Does a thing."
    assert pf.is_loaded is True
    assert pf.load_error is None
    assert callable(pf.run)


def test_name_is_filename_stem_not_module_name(tmp_path):
    path = _write(tmp_path, "my_protocol.py", """
        def run(ctx, **params):
            return "done"
    """)
    pf = ProtocolFile(path)
    assert pf.name == "my_protocol"
    pf.load()
    assert pf.name == "my_protocol"


def test_params_build_param_tree_with_defaults(tmp_path):
    path = _write(tmp_path, "params.py", """
        PARAMS = [
            dict(name="amplitude", type="float", default=5.0),
            dict(name="count", type="int", default=3),
        ]

        def run(ctx, **params):
            return "done"
    """)
    pf = ProtocolFile(path)
    pf.load()
    assert pf.param_tree is not None
    assert pf.param_values() == {"amplitude": 5.0, "count": 3}


def test_editing_param_tree_changes_param_values(tmp_path):
    path = _write(tmp_path, "params2.py", """
        PARAMS = [dict(name="count", type="int", default=3)]

        def run(ctx, **params):
            return "done"
    """)
    pf = ProtocolFile(path)
    pf.load()
    pf.param_tree.child("count").setValue(7)
    assert pf.param_values() == {"count": 7}


def test_no_params_defaults_to_empty(tmp_path):
    path = _write(tmp_path, "noparams.py", """
        def run(ctx, **params):
            return "done"
    """)
    pf = ProtocolFile(path)
    pf.load()
    assert pf.params == []
    assert pf.param_values() == {}


def test_missing_run_raises_and_records_error(tmp_path):
    path = _write(tmp_path, "norun.py", "x = 1\n")
    pf = ProtocolFile(path)
    with pytest.raises(ProtocolLoadError, match="run"):
        pf.load()
    assert pf.is_loaded is False
    assert pf.load_error is not None


def test_syntax_error_raises_and_records_error(tmp_path):
    path = _write(tmp_path, "bad.py", "this is not valid python !!!")
    pf = ProtocolFile(path)
    with pytest.raises(ProtocolLoadError):
        pf.load()
    assert pf.is_loaded is False
    assert pf.load_error is not None


def test_import_time_exception_wrapped(tmp_path):
    path = _write(tmp_path, "boom.py", """
        raise RuntimeError("boom")

        def run(ctx, **params):
            return "done"
    """)
    pf = ProtocolFile(path)
    with pytest.raises(ProtocolLoadError, match="boom"):
        pf.load()
    assert pf.is_loaded is False
    assert pf.load_error is not None


def test_reload_picks_up_new_params_default(tmp_path):
    path = _write(tmp_path, "mut.py", """
        PARAMS = [dict(name="count", type="int", default=3)]

        def run(ctx, **params):
            return "done"
    """)
    pf = ProtocolFile(path)
    pf.load()
    assert pf.param_values() == {"count": 3}
    _write(tmp_path, "mut.py", """
        PARAMS = [dict(name="count", type="int", default=9)]

        def run(ctx, **params):
            return "done"
    """)
    pf.load()
    assert pf.param_values() == {"count": 9}


def test_dataclass_at_module_level_loads(tmp_path):
    # Regression: sys.modules must be populated before exec_module, otherwise
    # dataclass's ClassVar/InitVar detection (which looks up the defining
    # module's globals via sys.modules) blows up on modules using
    # `from __future__ import annotations`.
    path = _write(tmp_path, "dc.py", """
        from __future__ import annotations
        from dataclasses import dataclass

        @dataclass
        class Foo:
            x: int = 1

        def run(ctx, **params):
            return Foo()
    """)
    pf = ProtocolFile(path)
    pf.load()
    assert pf.is_loaded is True
    assert pf.run(None).x == 1


def test_successful_reload_after_failed_load_clears_error(tmp_path):
    path = _write(tmp_path, "flaky.py", "this is not valid python !!!")
    pf = ProtocolFile(path)
    with pytest.raises(ProtocolLoadError):
        pf.load()
    assert pf.is_loaded is False
    assert pf.load_error is not None

    _write(tmp_path, "flaky.py", """
        def run(ctx, **params):
            return "done"
    """)
    pf.load()
    assert pf.is_loaded is True
    assert pf.load_error is None
