"""Tests for acq4.util.reload: which loaded modules a Ctrl-R reload picks up.

Most tests run reloadChanged over a fake sys.modules with pg_reload.reload stubbed. Tests
after the "real reloader" marker use real imports and the real reloader.
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
    """A module with no recorded state and an mtime after process start reloads on the
    first call."""
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
    """A module with a recorded, matching digest is not reloaded, whatever its mtime."""
    _install(modules, tmp_path, "known", "known.py", mtime=1500.0)
    _record("known", tmp_path / "known.py", acq4_reload._signature(str(tmp_path / "known.py")))

    result = acq4_reload.reloadChanged(debug=False)

    assert reloaded == []
    assert result["known"] == (False, acq4_reload.UNCHANGED)


def test_an_edit_keeping_the_same_mtime_and_size_is_still_seen(modules, reloaded, tmp_path):
    """An edit that preserves both mtime and file size is detected by the digest."""
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
    """A directory outside every install root is in scope."""
    checkout = tmp_path / "some-sibling-checkout" / "pkg"
    checkout.mkdir(parents=True)

    roots = acq4_reload._installed_roots()

    assert not acq4_reload._normalize(str(checkout / "mod.py")).startswith(roots)


def test_installed_roots_really_cover_the_stdlib_and_site_packages():
    """The real _installed_roots() covers os, importlib._bootstrap_external, numpy and
    the user site-packages."""
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
    """The acq4 source tree is not under an install root."""
    roots = acq4_reload._installed_roots()

    assert not acq4_reload._normalize(acq4_reload.__file__).startswith(roots)


def test_installed_roots_follow_sysconfig_away_from_the_prefixes(monkeypatch, tmp_path):
    """A sysconfig install path outside every sys prefix is still an install root."""
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
    """reloadChanged skips a module under an install root as NOT_EDITABLE."""
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
    """A path reached through a symlink to the environment matches its install root."""
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
    """``__mp_main__``, multiprocessing's alias for ``__main__``, is skipped too."""
    entry = _install(modules, tmp_path, "__main__", "__main__.py", mtime=1500.0)
    modules["__mp_main__"] = entry

    result = acq4_reload.reloadChanged(debug=False)

    assert reloaded == []
    assert result["__main__"] == (False, acq4_reload.IGNORED_MAIN)
    assert result["__mp_main__"] == (False, acq4_reload.IGNORED_MAIN)


def test_a_packages_own_main_module_is_skipped(modules, reloaded, tmp_path):
    """``acq4.__main__`` is skipped when it is a separate object from ``__main__``, as
    when launched through tools/entry.py."""
    pkg = tmp_path / "acq4"
    pkg.mkdir()
    _install(modules, tmp_path, "__main__", "entry.py", mtime=1500.0)
    _install(modules, pkg, "acq4.__main__", "__main__.py", mtime=1500.0)

    result = acq4_reload.reloadChanged(debug=False)

    assert reloaded == []
    assert result["acq4.__main__"] == (False, acq4_reload.IGNORED_MAIN)


def test_an_extension_module_beside_its_source_is_not_reloaded(modules, reloaded, tmp_path):
    """A module loaded from foo.so is skipped as NOT_SOURCE even with foo.py beside it."""
    _source(tmp_path, "accel.py", 1500.0)
    compiled = types.ModuleType("accel")
    compiled.__file__ = str(tmp_path / "accel.so")
    modules["accel"] = compiled

    result = acq4_reload.reloadChanged(debug=False)

    assert reloaded == []
    assert result["accel"] == (False, acq4_reload.NOT_SOURCE)


def test_an_edit_that_moves_mtime_backwards_still_reloads(modules, reloaded, tmp_path):
    """A changed digest triggers a reload even when mtime moved backwards (tar, cp -p)."""
    _install(modules, tmp_path, "restored", "restored.py", mtime=900.0)
    _record("restored", tmp_path / "restored.py", "a-different-digest")

    result = acq4_reload.reloadChanged(debug=False)

    assert reloaded == ["restored"]
    assert result["restored"] == (True, None)


def test_a_module_that_failed_is_retried_however_its_timestamp_moved(modules, reloaded, tmp_path):
    """A module whose last reload failed is retried even with an mtime before process
    start."""
    path = tmp_path / "repaired.py"
    _install(modules, tmp_path, "repaired", "repaired.py", mtime=900.0)
    _record("repaired", path, acq4_reload._signature(str(path)), ok=False)

    result = acq4_reload.reloadChanged(debug=False)

    assert reloaded == ["repaired"]
    assert result["repaired"] == (True, None)


def test_main_is_never_reloaded(modules, reloaded, tmp_path):
    """``__main__`` (the startup script under ``python -m acq4``) is never reloaded."""
    _install(modules, tmp_path, "__main__", "__main__.py", mtime=1500.0)

    result = acq4_reload.reloadChanged(debug=False)

    assert reloaded == []
    assert result["__main__"] == (False, acq4_reload.IGNORED_MAIN)


def test_non_module_entries_in_sys_modules_are_skipped(modules, reloaded, tmp_path):
    """A non-module object in sys.modules, such as a lazy-import shim, is skipped."""
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
    """A module with no .py on disk (.pyc-only, or source deleted) is skipped."""
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
    """A second module object backed by the same file gets its own reload attempt.

    Its failure is reported without affecting the importable module. Uses the real
    reloader.
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
    """A file saved during a reload is reloaded again on the next pass."""
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
    """A source deleted before it is hashed fails that module only; others still reload."""
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
    """Of two modules backed by one file, only the failing one is retried each pass."""
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
    """The ``__main__`` object is skipped under any other name it appears as."""
    entry = _install(modules, tmp_path, "__main__", "__main__.py", mtime=1500.0)
    modules["launcher_internals"] = entry

    result = acq4_reload.reloadChanged(debug=False)

    assert reloaded == []
    assert result["launcher_internals"] == (False, acq4_reload.IGNORED_MAIN)


def test_a_first_look_records_nothing_so_touching_the_file_still_rescues_it(modules, reloaded, tmp_path):
    """A module skipped as unchanged on first look records no state, so touching its
    file later makes it reload."""
    path = tmp_path / "preloaded.py"
    _install(modules, tmp_path, "preloaded", "preloaded.py", mtime=500.0)

    first = acq4_reload.reloadChanged(debug=False)

    assert first["preloaded"] == (False, acq4_reload.UNCHANGED)
    assert "preloaded" not in acq4_reload._state, "a module never reloaded must record no state"

    os.utime(path, (1500.0, 1500.0))  # the operator touches it
    second = acq4_reload.reloadChanged(debug=False)

    assert reloaded == ["preloaded"], "a touch must still rescue a missed edit"
    assert second["preloaded"] == (True, None)


def test_a_name_rebound_to_a_different_file_does_not_inherit_the_old_digest(modules, reloaded, tmp_path):
    """A module name now backed by a different file ignores the digest recorded for the
    old file."""
    _install(modules, tmp_path, "plugin", "second.py", mtime=1500.0)
    _record("plugin", tmp_path / "first.py", acq4_reload._signature(str(tmp_path / "second.py")))

    result = acq4_reload.reloadChanged(debug=False)

    assert reloaded == ["plugin"], "a digest recorded for another file says nothing here"
    assert result["plugin"] == (True, None)


def test_a_source_that_vanishes_is_retried_after_it_comes_back_older(modules, reloaded, tmp_path, monkeypatch):
    """A module whose hash failed is retried after the file returns with an old mtime."""
    path = tmp_path / "flaky.py"
    _install(modules, tmp_path, "flaky", "flaky.py", mtime=1500.0)
    real_signature = acq4_reload._signature
    monkeypatch.setattr(
        acq4_reload, "_signature", lambda py: (_ for _ in ()).throw(OSError("gone"))
    )

    first = acq4_reload.reloadChanged(debug=False)
    assert first["flaky"][0] is False

    # The file returns with an mtime before process start; only the failed flag retries it.
    monkeypatch.setattr(acq4_reload, "_signature", real_signature)
    os.utime(path, (500.0, 500.0))
    second = acq4_reload.reloadChanged(debug=False)

    assert reloaded == ["flaky"]
    assert second["flaky"] == (True, None)


def test_the_debug_flag_reaches_the_reloader(modules, tmp_path, monkeypatch):
    """reloadChanged passes debug through to pg_reload.reload."""
    _install(modules, tmp_path, "noisy", "noisy.py", mtime=1500.0)
    seen = []
    monkeypatch.setattr(
        acq4_reload.pg_reload, "reload", lambda mod, debug=False: seen.append(debug)
    )

    acq4_reload.reloadChanged(debug=True)

    assert seen == [True], "debug must be passed through, or the log comes back empty"


def test_manager_splits_reloaded_from_failed(monkeypatch, caplog):
    """Manager.reloadAll lists as failed only reasons starting with FAILED, not skipped
    modules."""
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
    """Manager.reloadAll does not log "No changed sources" when every reload failed."""
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
    """A failed reload is reported in the result, logged at ERROR on every pass, and
    retried."""
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
    """reloadChanged returns every module's outcome when one module fails, rather than
    raising."""
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
    """_drop_stale_bytecode raises PermissionError when the .pyc cannot be removed."""
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
    """A module whose .pyc cannot be removed is reported failed and recorded with no
    digest."""
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
    assert digest is None, "no digest must be recorded, so the retry does not depend on mtime"


# --- against the real reloader, not a stub -----------------------------------------


def test_a_same_second_same_size_edit_is_really_reloaded(modules, tmp_path, monkeypatch, request):
    """An edit with unchanged mtime and size runs the new code, not the cached .pyc."""
    # pytest disables bytecode writing; without a .pyc this test would pass vacuously.
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
    """Re-executing reload.py in its existing namespace keeps _state and _PROCESS_START."""
    source = Path(acq4_reload.__file__).read_text()
    namespace = _existing_namespace()

    exec(compile(source, acq4_reload.__file__, "exec"), namespace)

    assert namespace["_PROCESS_START"] == 123.0
    assert namespace["_state"] == {"already.known": ("/already/known.py", "digest", True)}


def test_bookkeeping_survives_a_body_that_raises_partway():
    """_state and _PROCESS_START survive a re-execution of reload.py that raises partway."""
    source = Path(acq4_reload.__file__).read_text()
    marker = "NOT_SOURCE ="
    assert marker in source, "anchor for truncating the body has moved"
    truncated = source[: source.index(marker)] + "raise RuntimeError('partway')\n"
    namespace = _existing_namespace()

    with pytest.raises(RuntimeError, match="partway"):
        exec(compile(truncated, acq4_reload.__file__, "exec"), namespace)

    assert namespace["_PROCESS_START"] == 123.0
    assert namespace["_state"] == {"already.known": ("/already/known.py", "digest", True)}
