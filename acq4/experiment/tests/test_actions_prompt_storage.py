"""Tests for the plain-function prompt and storage actions (prompt,
new_data_dir, mark_important)."""
import importlib

import pytest

import acq4.util.DataManager as dm
from acq4.experiment.context import ExecutionContext
from acq4.experiment.actions.prompt import prompt
from acq4.experiment.actions.storage import mark_important, new_data_dir

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


def test_prompt_retains_the_message_and_the_clicked_label(monkeypatch):
    monkeypatch.setattr(prompt_mod, "_is_headless", lambda: False)
    monkeypatch.setattr(prompt_mod, "prompt_user", lambda title, message, labels: "Retry")
    ctx = ExecutionContext()
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )

    assert prompt(ctx, message="Replace the pipette", choices=("Retry", "Skip")) == "Retry"

    assert details == [
        ("text", {"lines": ["Replace the pipette", "operator chose: Retry"]})
    ]


def test_prompt_retains_the_default_choice_when_headless(monkeypatch):
    monkeypatch.setattr(prompt_mod, "_is_headless", lambda: True)
    ctx = ExecutionContext()
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )

    prompt(ctx, message="carry on", choices=("OK", "Cancel"))

    assert details[0][1]["lines"][1] == "operator chose: OK"


def test_new_data_dir_retains_the_directory_it_created():
    from acq4.experiment.actions.storage import new_data_dir
    from acq4.experiment.context import ExecutionContext

    class _Dir:
        def __init__(self, name):
            self._name = name

        def name(self):
            return self._name

        def isManaged(self):
            return True

        def info(self):
            return {"dirType": "Slice"}

        def mkdir(self, name, autoIncrement=False, info=None):
            return _Dir(f"/data/{name}")

        def parent(self):
            return self

        def setInfo(self, info):
            return None

    class _Manager:
        def __init__(self):
            self.current = _Dir("/data/slice_000")
            self.set_calls = []

        def getCurrentDir(self):
            return self.current

        def folderTypesConfig(self):
            return {"Cell": {"name": "cell_000"}}

        def setCurrentDir(self, d):
            self.set_calls.append(d)

    ctx = ExecutionContext(manager=_Manager())
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )

    created = new_data_dir(ctx, level="Cell")

    assert details == [("text", {"lines": [f"created {created.name()}"]})]


def test_mark_important_flags_the_current_directory(root_dir):
    man = FakeManager(root_dir)
    ctx = ExecutionContext(manager=man)
    cell_dir = new_data_dir(ctx, level="Cell")

    marked = mark_important(ctx)

    assert marked.name() == cell_dir.name()
    assert cell_dir.info()["important"] is True


def test_mark_important_leaves_the_rest_of_the_index_alone(root_dir):
    # setInfo updates the keys it is given; the directory type and the
    # experimental-unit flag the Data Manager reads must survive the marking.
    man = FakeManager(root_dir)
    ctx = ExecutionContext(manager=man)
    cell_dir = new_data_dir(ctx, level="Cell")

    mark_important(ctx)

    info = cell_dir.info()
    assert info["dirType"] == "Cell"
    assert info["expUnit"] is True


def test_mark_important_retains_the_directory_it_marked(root_dir):
    man = FakeManager(root_dir)
    ctx = ExecutionContext(manager=man)
    cell_dir = new_data_dir(ctx, level="Cell")
    details = []
    entries = []

    def watch(entry):
        entries.append(entry)
        entry.on_details = lambda e, kind, payload: details.append((kind, payload))

    ctx.on_log_action = watch

    mark_important(ctx)

    assert [e.name for e in entries] == ["Mark Important"]
    assert details == [("text", {"lines": [f"marked {cell_dir.name()} important"]})]


def test_mark_important_survives_a_storage_failure(root_dir):
    # A flag on the index is a record of the run, not the run: a storage
    # directory that cannot take it must not fail the protocol that has just
    # patched a cell and still has data to record. The reason goes to the
    # cell's log, exactly as _openRecorder's does.
    class _FailingManager(FakeManager):
        def getCurrentDir(self):
            raise RuntimeError("Storage directory has not been set.")

    lines = []
    ctx = ExecutionContext(manager=_FailingManager(root_dir), log=lines.append)

    assert mark_important(ctx) is None
    assert any("Storage directory has not been set." in line for line in lines)
