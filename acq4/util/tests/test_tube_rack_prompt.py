"""Tests for the tube-rack swap dialog: the grid mirrors the array, the start-n
spinbox and fill-order toggle refill it, operator edits survive both, and only
plain data crosses back to the calling thread."""
import threading

import pytest

from acq4.util import Qt
from acq4.util.task import asynch
from acq4.util import TubeRackPrompt as prompt_mod
from acq4.util.TubeRackPrompt import TubeRackDialog, prompt_tube_rack


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


def _numbered(start_n, column_major):
    """A make_ids standing in for generate_tube_ids: row-major numbers tubes
    0,1,2,3; column-major numbers them 0,2,1,3 on a 2x2."""
    order = [0, 1, 2, 3] if not column_major else [0, 2, 1, 3]
    return {index: f"T{start_n + ordinal}" for ordinal, index in enumerate(order)}


def _dialog(qapp, qtbot, make_ids=_numbered, start_n=0, rows=2, cols=2):
    dlg = TubeRackDialog("Swap tubes", "Load a fresh rack", rows, cols, make_ids, start_n)
    qtbot.addWidget(dlg)
    return dlg


# -- the grid ---------------------------------------------------------------


def test_the_grid_is_laid_out_physically_like_the_array(qapp, qtbot):
    dlg = _dialog(qapp, qtbot, rows=2, cols=3, make_ids=lambda n, cm: {})
    layout = dlg.gridLayout

    for index in range(6):
        row, col = divmod(index, 3)
        item = layout.itemAtPosition(row, col)
        assert item is not None, f"no field at {row},{col}"
        assert item.widget() is dlg.fields[index]


def test_the_grid_shows_each_physical_wells_label_in_its_cell(qapp, qtbot):
    from acq4.experiment.tube_ids import generate_tube_ids

    def make_ids(start_n, column_major):
        return generate_tube_ids("{well}-{tube_count}", 2, 3, start_n, column_major)

    dlg = _dialog(qapp, qtbot, rows=2, cols=3, make_ids=make_ids, start_n=0)
    dlg.columnMajorCheck.setChecked(True)

    def text_at(row, col):
        return dlg.gridLayout.itemAtPosition(row, col).widget().text()

    # Column-major numbers A01, B01, A02, B02, A03, B03 as 0..5; the cell's
    # well label never moves.
    assert text_at(0, 0) == "A01-0"
    assert text_at(1, 0) == "B01-1"
    assert text_at(0, 2) == "A03-4"
    assert text_at(1, 2) == "B03-5"


def test_the_fields_prefill_from_make_ids(qapp, qtbot):
    dlg = _dialog(qapp, qtbot, start_n=10)
    assert dlg.result_ids() == {0: "T10", 1: "T11", 2: "T12", 3: "T13"}


# -- start-n and the fill-order toggle --------------------------------------


def test_changing_start_n_renumbers_the_grid(qapp, qtbot):
    dlg = _dialog(qapp, qtbot, start_n=0)
    dlg.startSpin.setValue(700)
    assert dlg.result_ids() == {0: "T700", 1: "T701", 2: "T702", 3: "T703"}
    assert dlg.start_n() == 700


def test_the_fill_order_toggle_renumbers_the_grid(qapp, qtbot):
    dlg = _dialog(qapp, qtbot, start_n=0)
    dlg.columnMajorCheck.setChecked(True)
    # Column-major fills 0, 2, 1, 3 -- so the tube at index 2 takes number 1.
    assert dlg.result_ids() == {0: "T0", 2: "T1", 1: "T2", 3: "T3"}


def test_an_operator_edit_survives_a_renumber(qapp, qtbot):
    dlg = _dialog(qapp, qtbot, start_n=0)
    qtbot.keyClicks(dlg.fields[1], "-mine")

    dlg.startSpin.setValue(50)

    assert dlg.result_ids()[1] == "T1-mine"
    assert dlg.result_ids()[0] == "T50"
    assert dlg.result_ids()[2] == "T52"


def test_an_operator_edit_survives_the_fill_order_toggle(qapp, qtbot):
    dlg = _dialog(qapp, qtbot, start_n=0)
    qtbot.keyClicks(dlg.fields[3], "!")

    dlg.columnMajorCheck.setChecked(True)

    assert dlg.result_ids()[3] == "T3!"
    assert dlg.result_ids()[2] == "T1"


# -- a template the operator got wrong --------------------------------------


def test_a_failing_make_ids_reports_the_problem_and_leaves_the_fields_empty(qapp, qtbot):
    def boom(start_n, column_major):
        raise ValueError("could not format tube id from '{nope}': name 'nope' is not defined")

    dlg = _dialog(qapp, qtbot, make_ids=boom)

    assert dlg.result_ids() == {0: "", 1: "", 2: "", 3: ""}
    assert "nope" in dlg.errorLabel.text()


def test_the_operator_can_still_type_ids_when_the_template_fails(qapp, qtbot):
    """An id must never fail a run: a broken template degrades to typing them."""
    def boom(start_n, column_major):
        raise ValueError("bad template")

    dlg = _dialog(qapp, qtbot, make_ids=boom)
    qtbot.keyClicks(dlg.fields[2], "typed")

    assert dlg.result_ids()[2] == "typed"


def test_a_make_ids_that_raises_anything_leaves_the_dialog_usable(qapp, qtbot):
    def boom(start_n, column_major):
        raise ZeroDivisionError("cols is zero")

    dlg = _dialog(qapp, qtbot, make_ids=boom)
    qtbot.keyClicks(dlg.fields[0], "typed")

    assert "cols is zero" in dlg.errorLabel.text()
    assert dlg.result_ids()[0] == "typed"


# -- the headless path ------------------------------------------------------


def test_headless_returns_the_generated_defaults(monkeypatch):
    monkeypatch.setattr(prompt_mod, "_gui_available", lambda: False)

    ids, start_n = prompt_tube_rack("t", "m", 2, 2, _numbered, 10)

    assert ids == {0: "T10", 1: "T11", 2: "T12", 3: "T13"}
    assert start_n == 10


def test_headless_with_a_failing_template_still_returns(monkeypatch):
    monkeypatch.setattr(prompt_mod, "_gui_available", lambda: False)

    def boom(start_n, column_major):
        raise ValueError("bad template")

    ids, start_n = prompt_tube_rack("t", "m", 2, 2, boom, 10)

    assert ids == {}
    assert start_n == 10


# -- thread marshalling -----------------------------------------------------


def _find_dialog():
    Qt.QApplication.processEvents()
    dialogs = [
        w
        for w in Qt.QApplication.topLevelWidgets()
        if isinstance(w, TubeRackDialog) and w.isVisible()
    ]
    return dialogs[0] if dialogs else None


def _await_dialog(qtbot):
    for _ in range(500):
        dlg = _find_dialog()
        if dlg is not None:
            return dlg
        qtbot.wait(5)
    pytest.fail("prompt_tube_rack never showed a dialog")


def test_a_worker_thread_gets_back_plain_data_only(qapp, qtbot):
    task = asynch(lambda: prompt_tube_rack("t", "m", 2, 2, _numbered, 5))()

    dlg = _await_dialog(qtbot)
    dlg.accept()

    qtbot.waitUntil(lambda: task.is_done, timeout=2000)
    ids, start_n = task.wait()

    assert ids == {0: "T5", 1: "T6", 2: "T7", 3: "T8"}
    assert start_n == 5
    assert all(isinstance(v, str) for v in ids.values())


def test_cancel_comes_back_as_none(qapp, qtbot):
    task = asynch(lambda: prompt_tube_rack("t", "m", 2, 2, _numbered, 5))()

    dlg = _await_dialog(qtbot)
    dlg.reject()

    qtbot.waitUntil(lambda: task.is_done, timeout=2000)
    assert task.wait() is None


def test_the_dialog_is_built_on_the_gui_thread(qapp, qtbot):
    built_on = {}
    original = prompt_mod.TubeRackDialog

    class _Recording(original):
        def __init__(self, *args, **kwds):
            built_on["thread"] = threading.get_ident()
            super().__init__(*args, **kwds)

    prompt_mod.TubeRackDialog = _Recording
    try:
        task = asynch(lambda: prompt_tube_rack("t", "m", 1, 1, _numbered, 0))()
        dlg = _await_dialog(qtbot)
        dlg.accept()
        qtbot.waitUntil(lambda: task.is_done, timeout=2000)
        task.wait()
    finally:
        prompt_mod.TubeRackDialog = original

    assert built_on["thread"] == threading.get_ident()


def test_a_worker_is_released_when_make_ids_raises_a_non_value_error(qapp, qtbot):
    def boom(start_n, column_major):
        raise RuntimeError("operator callable failed")

    task = asynch(lambda: prompt_tube_rack("t", "m", 2, 2, boom, 5))()
    dlg = _await_dialog(qtbot)
    dlg.accept()

    qtbot.waitUntil(lambda: task.is_done, timeout=2000)
    ids, start_n = task.wait()
    assert ids == {0: "", 1: "", 2: "", 3: ""}


def test_a_worker_is_released_when_the_dialog_cannot_be_built(qapp, qtbot, monkeypatch):
    def broken(*args, **kwds):
        raise RuntimeError("cannot build")

    monkeypatch.setattr(prompt_mod, "TubeRackDialog", broken)
    task = asynch(lambda: prompt_tube_rack("t", "m", 2, 2, _numbered, 5))()

    qtbot.waitUntil(lambda: task.is_done, timeout=2000)
    with pytest.raises(RuntimeError, match="cannot build"):
        task.wait()
