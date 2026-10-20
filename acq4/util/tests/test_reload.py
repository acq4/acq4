"""Tests for acq4.util.reload: which loaded modules a Ctrl-R reload picks up.

Most tests drive reloadChanged over a controlled sys.modules with the reload call itself
stubbed, so they pin selection and bookkeeping. The last two use a real imported module
and the real reloader, because what they cover -- stale bytecode, and bookkeeping
surviving a re-execution of this module -- cannot be seen through a stub.
"""
import importlib
import importlib.util
import logging
import os
import sys
import site
import types
import warnings
from pathlib import Path

import pytest

from acq4.util import reload as acq4_reload


@pytest.fixture
def modules(monkeypatch):
    """Drive reloadChanged over a sys.modules we control, from a clean state table."""
    fake = {}
    monkeypatch.setattr(acq4_reload, "sys", types.SimpleNamespace(modules=fake))
    monkeypatch.setattr(acq4_reload, "_state", {})
    monkeypatch.setattr(acq4_reload, "_PROCESS_START", 1000.0)
    return fake


def _record(name, path, signature="sig", ok=True):
    """Pretend module *name* was reloaded before, with the given digest and outcome."""
    acq4_reload._state[name] = (str(path), signature, ok)


@pytest.fixture
def reloaded(monkeypatch):
    """Record the modules pg_reload.reload was asked to reload."""
    seen = []
    monkeypatch.setattr(
        acq4_reload.pg_reload, "reload", lambda mod, debug=False: seen.append(mod.__name__)
    )
    return seen


def _source(directory, filename, mtime):
    path = directory / filename
    path.write_text("# stand-in for a real source file\n")
    os.utime(path, (mtime, mtime))
    return path


def _install(modules, directory, name, filename, mtime):
    """Put a module named *name*, backed by a file of age *mtime*, into sys.modules."""
    mod = types.ModuleType(name)
    mod.__file__ = str(_source(directory, filename, mtime))
    modules[name] = mod
    return mod


def test_module_edited_after_process_start_reloads_though_never_recorded(modules, reloaded, tmp_path):
    """The regression this module exists for.

    A module imported on demand -- so its mtime was never recorded at startup -- and then
    edited must reload on the very next call. Recording it as "first seen" instead would
    swallow the edit until the file was touched a second time.
    """
    _install(modules, tmp_path, "latecomer", "latecomer.py", mtime=1500.0)

    result = acq4_reload.reloadChanged(debug=False)

    assert reloaded == ["latecomer"]
    assert result["latecomer"] == (True, None)


def test_module_untouched_since_process_start_is_left_alone(modules, reloaded, tmp_path):
    _install(modules, tmp_path, "untouched", "untouched.py", mtime=500.0)

    result = acq4_reload.reloadChanged(debug=False)

    assert reloaded == []
    assert result["untouched"] == (False, acq4_reload.UNCHANGED)


def test_a_recorded_signature_wins_over_the_startup_floor(modules, reloaded, tmp_path):
    """Once recorded, content decides -- the timestamp stops mattering."""
    _install(modules, tmp_path, "known", "known.py", mtime=1500.0)
    _record("known", tmp_path / "known.py", acq4_reload._signature(str(tmp_path / "known.py")))

    result = acq4_reload.reloadChanged(debug=False)

    assert reloaded == []
    assert result["known"] == (False, acq4_reload.UNCHANGED)


def test_an_edit_keeping_the_same_mtime_and_size_is_still_seen(modules, reloaded, tmp_path):
    """The hole no stat-based signature can close: same mtime, same size, new bytes.

    This is the whole reason the signature is a digest rather than (mtime, size), so the
    edit here must preserve both or the test proves nothing about content.
    """
    path = tmp_path / "ticked.py"
    _install(modules, tmp_path, "ticked", "ticked.py", mtime=1500.0)
    before = path.stat()
    _record("ticked", path, acq4_reload._signature(str(path)))

    path.write_text("# stand-in for a real source FILE\n")
    os.utime(path, (before.st_atime, before.st_mtime))
    after = path.stat()
    assert after.st_size == before.st_size, "the edit must not change the length"
    assert after.st_mtime == before.st_mtime, "the edit must not change the timestamp"

    result = acq4_reload.reloadChanged(debug=False)

    assert reloaded == ["ticked"]
    assert result["ticked"] == (True, None)


def test_a_reloaded_module_is_not_reloaded_again(modules, reloaded, tmp_path):
    _install(modules, tmp_path, "once", "once.py", mtime=1500.0)

    acq4_reload.reloadChanged(debug=False)
    acq4_reload.reloadChanged(debug=False)

    assert reloaded == ["once"]


def test_a_checkout_outside_the_install_roots_is_in_scope(tmp_path):
    """The rule is "not under an install root", whoever the package happens to be.

    Asserting that the real pyqtgraph and teleprox are in scope would only be testing
    this machine's layout: CI pip-installs both into site-packages, where they are
    correctly out of scope.
    """
    checkout = tmp_path / "some-sibling-checkout" / "pkg"
    checkout.mkdir(parents=True)

    roots = acq4_reload._installed_roots()

    assert not acq4_reload._normalize(str(checkout / "mod.py")).startswith(roots)


def test_installed_roots_really_cover_the_stdlib_and_site_packages():
    """The real _installed_roots(), not a synthetic stand-in.

    This is what keeps Ctrl-R away from importlib._bootstrap_external, whose reload
    leaves its _bootstrap as None and breaks every later import. A test that supplies
    its own known-good root proves nothing about the function that builds the real one.
    """
    roots = acq4_reload._installed_roots()

    def excluded(module):
        return acq4_reload._normalize(module.__file__).startswith(roots)

    import importlib._bootstrap_external as bootstrap
    import numpy  # installed in site-packages, not an editable checkout

    assert excluded(os), "the stdlib must be out of scope"
    assert excluded(bootstrap), "the import machinery must be out of scope"
    assert excluded(numpy), "site-packages must be out of scope"
    user_module = os.path.join(site.getusersitepackages(), "somepkg", "mod.py")
    assert acq4_reload._normalize(user_module).startswith(
        roots
    ), "pip install --user lands outside every sysconfig path and prefix"


def test_acq4_itself_is_in_scope():
    """The counterpart: the exclusion must not swallow the tree we are here to reload."""
    roots = acq4_reload._installed_roots()

    assert not acq4_reload._normalize(acq4_reload.__file__).startswith(roots)


def test_installed_roots_follow_sysconfig_away_from_the_prefixes(monkeypatch, tmp_path):
    """Whatever sysconfig reports as an install path is excluded, prefix or not.

    In an ordinary layout these sit under sys.prefix and the entry is redundant. It is
    kept because an install scheme is free to put them elsewhere, and a library tree
    wrongly treated as editable is the expensive direction of this decision.
    """
    elsewhere = tmp_path / "somewhere-else" / "site-packages"
    elsewhere.mkdir(parents=True)
    monkeypatch.setattr(
        acq4_reload.sysconfig, "get_paths", lambda *a, **k: {"purelib": str(elsewhere)}
    )

    roots = acq4_reload._installed_roots()

    assert acq4_reload._normalize(str(elsewhere / "pkg" / "mod.py")).startswith(roots)


def test_installed_roots_do_not_match_a_sibling_by_prefix(monkeypatch, tmp_path):
    """'/env' must not exclude '/env-src/...'; the roots carry a trailing separator."""
    env = tmp_path / "env"
    sibling = tmp_path / "env-src"
    env.mkdir()
    sibling.mkdir()
    monkeypatch.setattr(sys, "prefix", str(env))
    monkeypatch.setattr(sys, "base_prefix", str(env))
    monkeypatch.setattr(sys, "exec_prefix", str(env))
    monkeypatch.setattr(sys, "base_exec_prefix", str(env))

    roots = acq4_reload._installed_roots()

    assert acq4_reload._normalize(str(env / "x.py")).startswith(roots)
    assert not acq4_reload._normalize(str(sibling / "x.py")).startswith(roots)


def test_installed_packages_are_out_of_scope(modules, reloaded, tmp_path, monkeypatch):
    """And the exclusion is actually applied by reloadChanged, not merely computable."""
    installed = tmp_path / "env" / "lib" / "python3.12"
    installed.mkdir(parents=True)
    monkeypatch.setattr(
        acq4_reload, "_INSTALLED_ROOTS", (acq4_reload._normalize(str(installed)) + os.sep,)
    )
    _install(modules, installed, "importlib._bootstrap_external", "_bootstrap_external.py", mtime=1500.0)

    result = acq4_reload.reloadChanged(debug=False)

    assert reloaded == []
    assert result["importlib._bootstrap_external"] == (False, acq4_reload.NOT_EDITABLE)


def test_a_symlinked_environment_is_still_recognised_as_installed(monkeypatch, tmp_path):
    """A dev checkout keeps sibling repos in a symlink farm; abspath would miss this."""
    real_env = tmp_path / "realenv"
    (real_env / "lib").mkdir(parents=True)
    link = tmp_path / "linkenv"
    link.symlink_to(real_env)
    monkeypatch.setattr(sys, "prefix", str(real_env))
    monkeypatch.setattr(sys, "base_prefix", str(real_env))
    monkeypatch.setattr(sys, "exec_prefix", str(real_env))
    monkeypatch.setattr(sys, "base_exec_prefix", str(real_env))

    roots = acq4_reload._installed_roots()

    assert acq4_reload._normalize(str(link / "lib" / "mod.py")).startswith(roots)


def test_the_entry_point_is_skipped_under_its_multiprocessing_alias(modules, reloaded, tmp_path):
    """multiprocessing aliases __main__ as __mp_main__, pointing at the same object.

    Skipping by name lets the alias through, and reloading it either re-execs the entry
    point in the running process or fails forever, depending on whether it happens to be
    importable from a sys.path root.
    """
    entry = _install(modules, tmp_path, "__main__", "__main__.py", mtime=1500.0)
    modules["__mp_main__"] = entry

    result = acq4_reload.reloadChanged(debug=False)

    assert reloaded == []
    assert result["__main__"] == (False, acq4_reload.IGNORED_MAIN)
    assert result["__mp_main__"] == (False, acq4_reload.IGNORED_MAIN)


def test_a_packages_own_main_module_is_skipped(modules, reloaded, tmp_path):
    """tools/entry.py in this repo is `from acq4 import __main__`.

    Launched that way, sys.modules["__main__"] is the launcher and acq4/__main__.py is a
    separate object under its own name, so an identity test against __main__ does not
    cover it. Reloading it re-runs the startup script inside the running process.
    """
    pkg = tmp_path / "acq4"
    pkg.mkdir()
    _install(modules, tmp_path, "__main__", "entry.py", mtime=1500.0)
    _install(modules, pkg, "acq4.__main__", "__main__.py", mtime=1500.0)

    result = acq4_reload.reloadChanged(debug=False)

    assert reloaded == []
    assert result["acq4.__main__"] == (False, acq4_reload.IGNORED_MAIN)


def test_an_extension_module_beside_its_source_is_not_reloaded(modules, reloaded, tmp_path):
    """A Cython pure-python build leaves foo.so next to the foo.py it came from.

    Treating the .so as source and reloading it re-runs a C extension's module init,
    which many extensions do not support.
    """
    _source(tmp_path, "accel.py", 1500.0)
    compiled = types.ModuleType("accel")
    compiled.__file__ = str(tmp_path / "accel.so")
    modules["accel"] = compiled

    result = acq4_reload.reloadChanged(debug=False)

    assert reloaded == []
    assert result["accel"] == (False, acq4_reload.NOT_SOURCE)


def test_an_edit_that_moves_mtime_backwards_still_reloads(modules, reloaded, tmp_path):
    """tar, rsync -a and cp -p all restore older timestamps; that is still an edit."""
    _install(modules, tmp_path, "restored", "restored.py", mtime=900.0)
    _record("restored", tmp_path / "restored.py", "a-different-digest")

    result = acq4_reload.reloadChanged(debug=False)

    assert reloaded == ["restored"]
    assert result["restored"] == (True, None)


def test_a_module_that_failed_is_retried_however_its_timestamp_moved(modules, reloaded, tmp_path):
    """A repaired file restored with an old timestamp must not look settled.

    Retry is driven by the recorded outcome, not by the timestamp, so a fix that moves
    mtime back below the startup floor is still picked up.
    """
    path = tmp_path / "repaired.py"
    _install(modules, tmp_path, "repaired", "repaired.py", mtime=900.0)
    _record("repaired", path, acq4_reload._signature(str(path)), ok=False)

    result = acq4_reload.reloadChanged(debug=False)

    assert reloaded == ["repaired"]
    assert result["repaired"] == (True, None)


def test_main_is_never_reloaded(modules, reloaded, tmp_path):
    """acq4 runs as `python -m acq4`, so __main__ is the startup script.

    importlib.reload on it re-execs that script in the running process: argparse runs
    again, a second Manager is built, app.exec_() is re-entered.
    """
    _install(modules, tmp_path, "__main__", "__main__.py", mtime=1500.0)

    result = acq4_reload.reloadChanged(debug=False)

    assert reloaded == []
    assert result["__main__"] == (False, acq4_reload.IGNORED_MAIN)


def test_non_module_entries_in_sys_modules_are_skipped(modules, reloaded, tmp_path):
    """sys.modules can hold lazy-import shims and module proxies, not just modules."""
    modules["shim"] = types.SimpleNamespace(__file__=str(_source(tmp_path, "shim.py", 1500.0)))

    result = acq4_reload.reloadChanged(debug=False)

    assert reloaded == []
    assert result["shim"] == (False, acq4_reload.NOT_SOURCE)


def test_module_without_a_file_is_skipped(modules, reloaded):
    modules["namespacey"] = types.ModuleType("namespacey")

    result = acq4_reload.reloadChanged(debug=False)

    assert reloaded == []
    assert result["namespacey"] == (False, acq4_reload.NOT_SOURCE)


def test_module_whose_source_is_gone_is_skipped(modules, reloaded, tmp_path):
    """A .pyc-only install, or a source file deleted since load."""
    mod = types.ModuleType("compiled")
    mod.__file__ = str(tmp_path / "compiled.pyc")
    modules["compiled"] = mod

    result = acq4_reload.reloadChanged(debug=False)

    assert reloaded == []
    assert result["compiled"] == (False, acq4_reload.NOT_SOURCE)


def test_two_names_for_one_module_object_share_a_single_reload(modules, reloaded, tmp_path):
    mod = _install(modules, tmp_path, "canonical", "shared.py", mtime=1500.0)
    modules["an.alias"] = mod

    result = acq4_reload.reloadChanged(debug=False)

    assert reloaded == ["canonical"]
    assert result["canonical"] == (True, None)
    assert result["an.alias"] == (True, None), "an alias must still get a result"


def test_a_second_object_for_one_file_is_attempted_and_reported(modules, tmp_path, monkeypatch, request):
    """One file can back two module objects; each needs its own reload attempt.

    importlib.reload refuses it -- here because the synthetic name is absent from the
    real sys.modules it consults -- so what matters is that it is attempted, reported,
    and does not take the canonical module down with it. Uses the real reloader, because a stub
    would happily report a success that cannot happen.
    """
    monkeypatch.setattr(sys, "dont_write_bytecode", False)
    monkeypatch.syspath_prepend(str(tmp_path))
    src = tmp_path / "shared_mod.py"
    src.write_text("VALUE = 'old'\n")
    canonical = importlib.import_module("shared_mod")
    request.addfinalizer(lambda: sys.modules.pop("shared_mod", None))

    spec = importlib.util.spec_from_file_location("synthetic_shared", str(src))
    synthetic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(synthetic)

    src.write_text("VALUE = 'new'\n")
    modules["shared_mod"] = canonical
    modules["synthetic_shared"] = synthetic
    monkeypatch.setattr(acq4_reload, "_PROCESS_START", os.stat(src).st_mtime - 1)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = acq4_reload.reloadChanged(debug=False)

    assert canonical.VALUE == "new", "the importable module must actually reload"
    assert result["shared_mod"] == (True, None)
    assert result["synthetic_shared"][0] is False, "importlib cannot reload a specless module"
    assert result["synthetic_shared"][1].startswith(acq4_reload.FAILED)


def test_every_name_in_sys_modules_gets_a_result(modules, reloaded, tmp_path):
    _install(modules, tmp_path, "changed", "changed.py", mtime=1500.0)
    _install(modules, tmp_path, "stable", "stable.py", mtime=500.0)
    modules["bodiless"] = types.ModuleType("bodiless")

    result = acq4_reload.reloadChanged(debug=False)

    assert set(result) == {"changed", "stable", "bodiless"}


def test_a_save_during_the_reload_is_not_recorded_as_loaded(modules, tmp_path, monkeypatch):
    """The digest must describe the bytes that ran, not whatever is on disk afterwards.

    Saving again while a reload is in flight is ordinary behaviour. Recording the newer
    digest would report that edit as already loaded and never pick it up.
    """
    path = tmp_path / "racy.py"
    _install(modules, tmp_path, "racy", "racy.py", mtime=1500.0)
    seen = []

    def save_midway(mod, debug=False):
        seen.append(mod.__name__)
        path.write_text("# a newer version, saved while the reload was running\n")

    monkeypatch.setattr(acq4_reload.pg_reload, "reload", save_midway)
    acq4_reload.reloadChanged(debug=False)

    # The next pass must still see the version saved during the reload as outstanding.
    monkeypatch.setattr(
        acq4_reload.pg_reload, "reload", lambda mod, debug=False: seen.append(mod.__name__)
    )
    result = acq4_reload.reloadChanged(debug=False)

    assert seen == ["racy", "racy"], "the version saved mid-reload must still reload"
    assert result["racy"] == (True, None)


def test_a_source_that_vanishes_mid_pass_does_not_sink_the_pass(modules, reloaded, tmp_path, monkeypatch):
    """A git checkout landing between classification and hashing must not abort Ctrl-R."""
    _install(modules, tmp_path, "vanishing", "vanishing.py", mtime=1500.0)
    _install(modules, tmp_path, "survivor", "survivor.py", mtime=1500.0)
    real_signature = acq4_reload._signature

    def vanish_first(py):
        if py.endswith("vanishing.py"):
            os.remove(py)
        return real_signature(py)

    monkeypatch.setattr(acq4_reload, "_signature", vanish_first)

    result = acq4_reload.reloadChanged(debug=False)

    assert result["vanishing"][0] is False
    assert result["vanishing"][1].startswith(acq4_reload.FAILED)
    assert result["survivor"] == (True, None), "the rest of the pass must still run"


def test_a_failing_object_does_not_drag_its_siblings_along(modules, tmp_path, monkeypatch, caplog):
    """Two objects, one file, one of them permanently unreloadable.

    State is keyed by module name rather than by path precisely so the healthy one
    settles after its first reload instead of re-running its import side effects on
    every Ctrl-R for the rest of the session.
    """
    good = _install(modules, tmp_path, "good", "shared.py", mtime=1500.0)
    bad = types.ModuleType("bad")
    bad.__file__ = str(tmp_path / "shared.py")
    modules["bad"] = bad
    attempts = []

    def selective(mod, debug=False):
        attempts.append(mod.__name__)
        if mod.__name__ == "bad":
            raise RuntimeError("never reloadable")

    monkeypatch.setattr(acq4_reload.pg_reload, "reload", selective)

    with caplog.at_level(logging.CRITICAL, logger="acq4"):
        for _ in range(3):
            result = acq4_reload.reloadChanged(debug=False)

    assert attempts == ["good", "bad", "bad", "bad"], "only the failing object retries"
    assert result["good"] == (False, acq4_reload.UNCHANGED)
    assert result["bad"][0] is False


def test_an_entry_point_aliased_under_a_library_name_is_still_skipped(modules, reloaded, tmp_path):
    """Skipping by name alone lets the same object through under an ordinary alias."""
    entry = _install(modules, tmp_path, "__main__", "__main__.py", mtime=1500.0)
    modules["launcher_internals"] = entry

    result = acq4_reload.reloadChanged(debug=False)

    assert reloaded == []
    assert result["launcher_internals"] == (False, acq4_reload.IGNORED_MAIN)


def test_a_first_look_records_nothing_so_touching_the_file_still_rescues_it(modules, reloaded, tmp_path):
    """Nothing is recorded for a module we never actually reloaded.

    Recording its digest as "loaded" would be asserting something we never checked: the
    file merely looks older than startup. Worse, it would survive the operator's usual
    recovery move -- touch the file -- because content would then agree with the claim
    forever. This is the one path by which a recorded digest could describe bytes that
    never ran, so it stays closed.
    """
    path = tmp_path / "preloaded.py"
    _install(modules, tmp_path, "preloaded", "preloaded.py", mtime=500.0)

    first = acq4_reload.reloadChanged(debug=False)

    assert first["preloaded"] == (False, acq4_reload.UNCHANGED)
    assert "preloaded" not in acq4_reload._state, "nothing was loaded, so claim nothing"

    os.utime(path, (1500.0, 1500.0))  # the operator touches it
    second = acq4_reload.reloadChanged(debug=False)

    assert reloaded == ["preloaded"], "a touch must still rescue a missed edit"
    assert second["preloaded"] == (True, None)


def test_a_name_rebound_to_a_different_file_does_not_inherit_the_old_digest(modules, reloaded, tmp_path):
    """State is keyed by name, so a name reused for other code must not look settled."""
    _install(modules, tmp_path, "plugin", "second.py", mtime=1500.0)
    _record("plugin", tmp_path / "first.py", acq4_reload._signature(str(tmp_path / "second.py")))

    result = acq4_reload.reloadChanged(debug=False)

    assert reloaded == ["plugin"], "a digest recorded for another file says nothing here"
    assert result["plugin"] == (True, None)


def test_a_source_that_vanishes_is_retried_after_it_comes_back_older(modules, reloaded, tmp_path, monkeypatch):
    """A failed hash must leave the module pending, not fall back to the timestamp.

    Otherwise a file restored below the startup floor reads as unchanged forever.
    """
    path = tmp_path / "flaky.py"
    _install(modules, tmp_path, "flaky", "flaky.py", mtime=1500.0)
    real_signature = acq4_reload._signature
    monkeypatch.setattr(
        acq4_reload, "_signature", lambda py: (_ for _ in ()).throw(OSError("gone"))
    )

    first = acq4_reload.reloadChanged(debug=False)
    assert first["flaky"][0] is False

    # The file comes back, older than the floor -- only the pending flag can save it.
    monkeypatch.setattr(acq4_reload, "_signature", real_signature)
    os.utime(path, (500.0, 500.0))
    second = acq4_reload.reloadChanged(debug=False)

    assert reloaded == ["flaky"]
    assert second["flaky"] == (True, None)


def test_the_debug_flag_reaches_the_reloader(modules, tmp_path, monkeypatch):
    """reload_libraries advertises the reloader's debug log in its `output`."""
    _install(modules, tmp_path, "noisy", "noisy.py", mtime=1500.0)
    seen = []
    monkeypatch.setattr(
        acq4_reload.pg_reload, "reload", lambda mod, debug=False: seen.append(debug)
    )

    acq4_reload.reloadChanged(debug=True)

    assert seen == [True], "debug must be passed through, or the log comes back empty"


def test_manager_splits_reloaded_from_failed(monkeypatch, caplog):
    """Manager.reloadAll's summary must count only real failures.

    Without the FAILED filter, every out-of-scope name lands in `failed` -- about 1400
    on a running rig -- and Ctrl-R reports the whole standard library as broken.
    """
    from acq4 import Manager as manager_module

    monkeypatch.setattr(
        manager_module.reload,
        "reloadChanged",
        lambda debug=True: {
            "acq4.good": (True, None),
            "acq4.stale": (False, acq4_reload.UNCHANGED),
            "os": (False, acq4_reload.NOT_SOURCE),
            "numpy": (False, acq4_reload.NOT_EDITABLE),
            "acq4.wedged": (False, f"{acq4_reload.FAILED}: RuntimeError: no"),
        },
    )

    with caplog.at_level(logging.INFO, logger="acq4"):
        manager_module.Manager.reloadAll(None)

    text = caplog.text
    assert "Reloaded 1 module(s): acq4.good" in text
    assert "1 module(s) failed to reload: acq4.wedged" in text
    assert "os" not in text.split("failed to reload:")[1], "only real failures count"
    assert "No changed sources" not in text


def test_manager_does_not_claim_nothing_changed_when_every_reload_failed(monkeypatch, caplog):
    """Sources did change; they just all failed. Saying otherwise contradicts the log."""
    from acq4 import Manager as manager_module

    monkeypatch.setattr(
        manager_module.reload,
        "reloadChanged",
        lambda debug=True: {"acq4.wedged": (False, f"{acq4_reload.FAILED}: RuntimeError: no")},
    )

    with caplog.at_level(logging.INFO, logger="acq4"):
        manager_module.Manager.reloadAll(None)

    assert "1 module(s) failed to reload: acq4.wedged" in caplog.text
    assert "No changed sources" not in caplog.text


def test_a_failed_reload_is_reported_and_stays_pending(modules, tmp_path, monkeypatch, caplog):
    """A failure is reported in the result, logged, retried, and does not sink the pass.

    The returned dict is the reliable channel; the log carries the traceback for the
    operator. It is logged rather than warned because Python's default warning filter
    shows a given location once per process, so later failures would be silent.
    """
    _install(modules, tmp_path, "broken", "broken.py", mtime=1500.0)
    attempts = []

    def boom(mod, debug=False):
        attempts.append(mod.__name__)
        raise RuntimeError("no")

    monkeypatch.setattr(acq4_reload.pg_reload, "reload", boom)

    with caplog.at_level(logging.ERROR, logger="acq4"):
        results = [acq4_reload.reloadChanged(debug=False) for _ in range(2)]

    assert len(caplog.records) == 2, "every failure must reach the log, not just the first"
    assert "RuntimeError" in caplog.text
    for result in results:
        ok, reason = result["broken"]
        assert ok is False
        assert reason.startswith(acq4_reload.FAILED)
        assert "RuntimeError: no" == reason.split(": ", 1)[1], "the reason must read cleanly"
    assert attempts == ["broken", "broken"], "a failed module must be retried"


def test_one_unreloadable_module_does_not_sink_the_whole_report(modules, tmp_path, monkeypatch, caplog):
    """Raising would discard every other module's outcome on every call, forever.

    Nothing clears a permanently-failing candidate short of a restart, so a raise would
    leave Manager logging nothing and reload_libraries returning None for the modules
    that did reload.
    """
    _install(modules, tmp_path, "breaks", "breaks.py", mtime=1500.0)
    _install(modules, tmp_path, "works", "works.py", mtime=1500.0)

    def selective(mod, debug=False):
        if mod.__name__ == "breaks":
            raise RuntimeError("no")

    monkeypatch.setattr(acq4_reload.pg_reload, "reload", selective)

    with caplog.at_level(logging.CRITICAL, logger="acq4"):
        result = acq4_reload.reloadChanged(debug=False)

    assert result["works"] == (True, None), "a working module must still be reported"
    assert result["breaks"][0] is False



def test_an_unremovable_bytecode_cache_is_not_swallowed(tmp_path):
    """Only a missing cache is resolvable here.

    Swallowing a PermissionError would let importlib run the stale bytecode and let us
    record that as a successful reload, which is the bug the cache drop exists to close.
    """
    src = tmp_path / "guarded.py"
    src.write_text("VALUE = 1\n")
    cache = Path(importlib.util.cache_from_source(str(src)))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(b"stale")
    cache.parent.chmod(0o500)
    try:
        if os.access(cache.parent, os.W_OK):
            pytest.skip("cannot make a directory read-only here")
        with pytest.raises(PermissionError):
            acq4_reload._drop_stale_bytecode(str(src))
    finally:
        cache.parent.chmod(0o700)


def test_a_module_whose_cache_cannot_be_cleared_is_reported_not_recorded(modules, tmp_path, monkeypatch):
    """Reporting the failure is right; recording a possibly-stale reload is not."""
    _install(modules, tmp_path, "guarded", "guarded.py", mtime=1500.0)
    real_remove = os.remove

    def refuse(path, *args, **kwargs):
        if str(path).endswith(".pyc"):
            raise PermissionError(13, "Permission denied", str(path))
        return real_remove(path, *args, **kwargs)

    monkeypatch.setattr(os, "remove", refuse)

    result = acq4_reload.reloadChanged(debug=False)

    ok, reason = result["guarded"]
    assert ok is False
    assert reason.startswith(acq4_reload.FAILED)
    _path, digest, reloaded_cleanly = acq4_reload._state["guarded"]
    assert reloaded_cleanly is False, (
        "a reload that may have run stale bytecode must not be recorded as done"
    )
    assert digest is None, "and no digest, so the retry cannot hinge on a timestamp"


# --- against the real reloader, not a stub -----------------------------------------


def test_a_same_second_same_size_edit_is_really_reloaded(modules, tmp_path, monkeypatch, request):
    """The .pyc, not the source, decides what importlib.reload executes.

    CPython validates cached bytecode against the source's recorded mtime and size, so an
    edit landing in the same second that leaves the length unchanged still looks valid.
    Without dropping the cache the reload silently re-runs the old code -- and we would
    then record the new mtime and never retry.
    """
    # pytest runs with bytecode writing off, so without this the cache never exists and
    # the test would pass without touching the behaviour it is here to pin.
    monkeypatch.setattr(sys, "dont_write_bytecode", False)
    monkeypatch.syspath_prepend(str(tmp_path))
    src = tmp_path / "victim_mod.py"
    src.write_text("VALUE = 'old'\n")
    victim = importlib.import_module("victim_mod")
    request.addfinalizer(lambda: sys.modules.pop("victim_mod", None))
    assert victim.VALUE == "old"
    cache = importlib.util.cache_from_source(str(src))
    assert os.path.isfile(cache), "precondition: the import must have written bytecode"
    before = os.stat(src)

    src.write_text("VALUE = 'new'\n")
    os.utime(src, (before.st_atime, before.st_mtime))
    assert os.stat(src).st_size == before.st_size, "the edit must not change the length"

    modules["victim_mod"] = victim
    monkeypatch.setattr(acq4_reload, "_PROCESS_START", before.st_mtime - 1)

    acq4_reload.reloadChanged(debug=False)

    assert victim.VALUE == "new"


def _existing_namespace():
    """A module namespace as importlib.reload presents it: the dict the module already has."""
    return {
        "__file__": acq4_reload.__file__,
        "__name__": "acq4.util.reload",
        "_PROCESS_START": 123.0,
        "_state": {"already.known": ("/already/known.py", "digest", True)},
    }


def test_bookkeeping_survives_re_execution_of_this_module():
    """importlib.reload re-runs the body in the module's existing namespace.

    The module must read its table and floor back out of that namespace rather than
    assigning fresh ones.
    """
    source = Path(acq4_reload.__file__).read_text()
    namespace = _existing_namespace()

    exec(compile(source, acq4_reload.__file__, "exec"), namespace)

    assert namespace["_PROCESS_START"] == 123.0
    assert namespace["_state"] == {"already.known": ("/already/known.py", "digest", True)}


def test_bookkeeping_survives_a_body_that_raises_partway():
    """The case a __reload__ hook cannot cover, and the reason this module avoids one.

    pyqtgraph invokes __reload__ only after a reload that returned, so a body raising
    partway would leave the table empty and the floor reset to now -- silently stranding
    every edit made before it, which is the failure this reloader exists to remove.
    """
    source = Path(acq4_reload.__file__).read_text()
    marker = "NOT_SOURCE ="
    assert marker in source, "anchor for truncating the body has moved"
    truncated = source[: source.index(marker)] + "raise RuntimeError('partway')\n"
    namespace = _existing_namespace()

    with pytest.raises(RuntimeError, match="partway"):
        exec(compile(truncated, acq4_reload.__file__, "exec"), namespace)

    assert namespace["_PROCESS_START"] == 123.0
    assert namespace["_state"] == {"already.known": ("/already/known.py", "digest", True)}
