"""Tests for the plain-function prompt and storage actions (prompt,
new_data_dir)."""
import importlib

import pytest

import acq4.util.DataManager as dm
from acq4.experiment.context import ExecutionContext
from acq4.experiment.actions.prompt import prompt
from acq4.experiment.actions.storage import new_data_dir

# The `actions` package re-exports `prompt` (the function) under the same
# name as the `prompt` submodule, so `acq4.experiment.actions.prompt` no
# longer resolves to the module via attribute access; go through sys.modules
# (via import_module) to reach the real submodule for monkeypatching.
prompt_mod = importlib.import_module("acq4.experiment.actions.prompt")


# -- prompt -----------------------------------------------------------------


def test_prompt_returns_clicked_label(monkeypatch):
    monkeypatch.setattr(prompt_mod, "_is_headless", lambda: False)
    calls = []

    def fake_prompt_user(title, message, choices):
        calls.append((title, message, choices))
        return "Skip"

    monkeypatch.setattr(prompt_mod, "prompt_user", fake_prompt_user)

    ctx = ExecutionContext()
    result = prompt(ctx, message="continue?", title="Prompt", choices="Retry,Skip")

    assert result == "Skip"
    assert calls == [("Prompt", "continue?", ["Retry", "Skip"])]


def test_prompt_choices_comma_string_splits(monkeypatch):
    monkeypatch.setattr(prompt_mod, "_is_headless", lambda: False)
    calls = []
    monkeypatch.setattr(
        prompt_mod, "prompt_user", lambda t, m, c: calls.append(c) or c[0]
    )

    ctx = ExecutionContext()
    prompt(ctx, choices="Retry, Skip , Abort")

    assert calls == [["Retry", "Skip", "Abort"]]


def test_prompt_empty_choices_default_to_ok(monkeypatch):
    monkeypatch.setattr(prompt_mod, "_is_headless", lambda: False)
    calls = []
    monkeypatch.setattr(
        prompt_mod, "prompt_user", lambda t, m, c: calls.append(c) or c[0]
    )

    ctx = ExecutionContext()
    prompt(ctx, choices="")

    assert calls == [["OK"]]


def test_prompt_choices_accepts_a_sequence(monkeypatch):
    monkeypatch.setattr(prompt_mod, "_is_headless", lambda: False)
    calls = []
    monkeypatch.setattr(
        prompt_mod, "prompt_user", lambda t, m, c: calls.append(c) or c[0]
    )

    ctx = ExecutionContext()
    prompt(ctx, choices=["Retry", "Skip"])

    assert calls == [["Retry", "Skip"]]


def test_prompt_choices_empty_sequence_defaults_to_ok(monkeypatch):
    monkeypatch.setattr(prompt_mod, "_is_headless", lambda: False)
    calls = []
    monkeypatch.setattr(
        prompt_mod, "prompt_user", lambda t, m, c: calls.append(c) or c[0]
    )

    ctx = ExecutionContext()
    prompt(ctx, choices=())

    assert calls == [["OK"]]


def test_prompt_headless_returns_first_choice_and_logs(monkeypatch):
    monkeypatch.setattr(prompt_mod, "_is_headless", lambda: True)

    def _fail(*a, **k):
        raise AssertionError("prompt_user should not be called when headless")

    monkeypatch.setattr(prompt_mod, "prompt_user", _fail)

    logged = []
    ctx = ExecutionContext(log=logged.append)
    result = prompt(ctx, message="continue?", choices="Retry,Skip")

    assert result == "Retry"
    assert logged == ["continue?"]


def test_prompt_creates_prompt_log_entry(monkeypatch):
    monkeypatch.setattr(prompt_mod, "_is_headless", lambda: True)

    ctx = ExecutionContext()
    seen = []
    ctx.on_log_action = seen.append
    prompt(ctx, message="hi")

    assert len(seen) == 1
    assert seen[0].name == "Operator Prompt"
    assert seen[0].status == "hi"


# `_is_headless` itself is never monkeypatched below: these drive its real
# body by faking the `Qt.QApplication` it consults, so a regression in the
# detection logic (which the `prompt` tests above all bypass) fails a test
# instead of leaving `PromptUser.prompt`'s unbounded `done.wait()` to hang
# with no operator present.
class _FakeQApplication:
    """Stand-in for Qt.QApplication exposing only the `instance()` query that
    `_is_headless` reads."""

    def __init__(self, instance):
        self._instance = instance

    def instance(self):
        return self._instance


def test_is_headless_true_when_no_application_instance(monkeypatch):
    monkeypatch.setattr(prompt_mod.Qt, "QApplication", _FakeQApplication(None))

    assert prompt_mod._is_headless() is True


def test_is_headless_false_when_application_instance_present(monkeypatch):
    monkeypatch.setattr(
        prompt_mod.Qt, "QApplication", _FakeQApplication(object())
    )

    assert prompt_mod._is_headless() is False


def test_prompt_reaches_operator_dialog_when_application_present(monkeypatch):
    monkeypatch.setattr(
        prompt_mod.Qt, "QApplication", _FakeQApplication(object())
    )
    calls = []

    def fake_prompt_user(title, message, choices):
        calls.append((title, message, choices))
        return "Skip"

    monkeypatch.setattr(prompt_mod, "prompt_user", fake_prompt_user)

    ctx = ExecutionContext()
    result = prompt(ctx, message="continue?", title="Prompt", choices="Retry,Skip")

    assert result == "Skip"
    assert calls == [("Prompt", "continue?", ["Retry", "Skip"])]


# -- storage ------------------------------------------------------------


FOLDER_TYPES = {
    "Cell": {"name": "Cell_%Y%m%d_%H%M%S", "experimentalUnit": True},
    "Slice": {"name": "Slice_%Y%m%d_%H%M%S", "experimentalUnit": False},
}


class FakeManager:
    """Minimal stand-in for the parts of Manager that new_data_dir uses,
    backed by real DirHandle objects on a temp directory."""

    def __init__(self, current_dir):
        self.current_dir = current_dir

    def getCurrentDir(self):
        return self.current_dir

    def setCurrentDir(self, d):
        self.current_dir = d

    def folderTypesConfig(self):
        return FOLDER_TYPES


@pytest.fixture
def root_dir(tmp_path):
    return dm.getDirHandle(str(tmp_path), create=True)


def test_new_data_dir_returns_directory_and_sets_current(root_dir):
    man = FakeManager(root_dir)
    ctx = ExecutionContext(manager=man)

    new_dir = new_data_dir(ctx, level="Cell")

    assert new_dir is not None
    assert new_dir.info().get("dirType") == "Cell"
    assert new_dir.info().get("expUnit") is True
    assert man.current_dir is new_dir


def test_new_data_dir_honors_set_current_false(root_dir):
    man = FakeManager(root_dir)
    ctx = ExecutionContext(manager=man)

    new_dir = new_data_dir(ctx, level="Cell", set_current=False)

    assert man.current_dir is root_dir
    assert new_dir is not root_dir


def test_new_data_dir_does_not_nest_same_type(root_dir):
    man = FakeManager(root_dir)
    ctx = ExecutionContext(manager=man)

    first = new_data_dir(ctx, level="Cell")
    assert first.parent().name() == root_dir.name()

    second = new_data_dir(ctx, level="Cell")
    assert second.name() != first.name()
    assert second.parent().name() == root_dir.name()


def test_new_data_dir_walks_up_through_a_different_type_to_find_same_type(root_dir):
    man = FakeManager(root_dir)
    ctx = ExecutionContext(manager=man)

    cell_dir = new_data_dir(ctx, level="Cell")
    slice_dir = new_data_dir(ctx, level="Slice")
    assert slice_dir.parent().name() == cell_dir.name()

    new_dir = new_data_dir(ctx, level="Cell")

    assert new_dir.parent().name() == root_dir.name()
    assert new_dir.parent().name() != cell_dir.name()
    assert new_dir.parent().name() != slice_dir.name()


def test_new_data_dir_no_experimental_unit_flag_when_not_configured(root_dir):
    man = FakeManager(root_dir)
    ctx = ExecutionContext(manager=man)

    new_dir = new_data_dir(ctx, level="Slice")

    assert "expUnit" not in new_dir.info()


def test_new_data_dir_folder_level_makes_untyped_new_folder(root_dir):
    man = FakeManager(root_dir)
    ctx = ExecutionContext(manager=man)

    new_dir = new_data_dir(ctx, level="Folder")

    assert new_dir.shortName().startswith("NewFolder")
    assert "dirType" not in new_dir.info()


def test_create_data_dir_needs_no_context(root_dir):
    # A UI button has no run and no ExecutionContext, and must not fabricate one
    # to reach engine logic.
    from acq4.experiment.actions.storage import create_data_dir

    man = FakeManager(root_dir)
    created = create_data_dir(man, level="Slice")

    assert created.info()["dirType"] == "Slice"
    assert man.getCurrentDir() is created


def test_create_data_dir_can_leave_the_current_dir_alone(root_dir):
    from acq4.experiment.actions.storage import create_data_dir

    man = FakeManager(root_dir)
    before = man.getCurrentDir()
    created = create_data_dir(man, level="Slice", set_current=False)

    assert created is not before
    assert man.getCurrentDir() is before


def test_new_data_dir_still_behaves_identically_through_the_wrapper(root_dir):
    # The action keeps its log_action wrapper and its behaviour; only the body
    # moved.
    entries = []
    man = FakeManager(root_dir)
    ctx = ExecutionContext(manager=man, on_log_action=entries.append)
    created = new_data_dir(ctx, level="Slice")

    assert created.info()["dirType"] == "Slice"
    assert [e.name for e in entries] == ["New Data Directory"]
