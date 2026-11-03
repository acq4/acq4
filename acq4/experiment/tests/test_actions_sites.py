"""Tests for the site actions: the nucleus-rack exhaustion gate, the rack swap,
and the cell-to-tube report derived from cell .index metadata."""
import time

import pytest

import acq4.util.DataManager as dm
from acq4.experiment.actions import sites as sites_mod
from acq4.experiment.actions.sites import (
    build_tube_report,
    nucleus_sites_exhausted,
    swap_tubes,
    tube_report,
)
from acq4.experiment.context import ExecutionContext
from acq4.experiment.exceptions import OrchestrationError


# -- doubles ----------------------------------------------------------------


class FakeSite:
    def __init__(self, name):
        self._name = name
        self.used_up = False
        self.tube_id = None
        self.parent = None

    def name(self):
        return self._name

    def parentDevice(self):
        return self.parent


class FakeArray:
    """Stands in for InteractionSiteArray: the grid, the availability rule, the
    clear, and the Device config-file storage the counter rides on."""

    role = "nucleus"

    def __init__(self, rows=1, cols=4):
        self.rows = rows
        self.cols = cols
        self.sites = [FakeSite(f"Rack[{i}]") for i in range(rows * cols)]
        for site in self.sites:
            site.parent = self
        self.files = {}

    def getFirstAvailableSite(self):
        for site in self.sites:
            if not site.used_up:
                return site
        return None

    def clearUsedUp(self):
        for site in self.sites:
            site.used_up = False
            site.tube_id = None

    def readConfigFile(self, filename):
        return self.files.get(filename, {})

    def writeConfigFile(self, data, filename):
        self.files[filename] = dict(data)


class FakePipetteDevice:
    def __init__(self, device=None):
        self.device = device

    def getSiteDeviceFor(self, role):
        assert role == "nucleus"
        return self.device

    def getSiteFor(self, role):
        device = self.getSiteDeviceFor(role)
        if device is not None and hasattr(device, "getFirstAvailableSite"):
            return device.getFirstAvailableSite()
        return device


class FakePatchPipette:
    def __init__(self, device=None):
        self.pipetteDevice = FakePipetteDevice(device)


class FakeManager:
    def __init__(self, current_dir=None):
        self.current_dir = current_dir

    def getCurrentDir(self):
        return self.current_dir


def _ctx(array, current_dir=None):
    return ExecutionContext(
        pipette=FakePatchPipette(array), manager=FakeManager(current_dir)
    )


@pytest.fixture
def day_tree(tmp_path):
    """A real managed Day/Slice/Cell tree, the way the orchestrator builds one.
    Returns (dayDir, make_cell) where make_cell(slice_name, cell_name, **info)
    creates a cell directory and stamps `info` onto its .index."""
    day = dm.getDirHandle(str(tmp_path / "2026.11.02_000"), create=True)
    day.setInfo({"dirType": "Day"})

    def make_cell(slice_name, cell_name, **info):
        slice_dir = day.getDir(slice_name, create=True)
        slice_dir.setInfo({"dirType": "Slice"})
        cell_dir = slice_dir.getDir(cell_name, create=True)
        cell_dir.setInfo({"dirType": "Cell", **info})
        return cell_dir

    return day, make_cell


# -- the gate ---------------------------------------------------------------


def test_the_gate_is_false_while_a_site_is_available():
    array = FakeArray(cols=2)
    assert nucleus_sites_exhausted(_ctx(array)) is False


def test_the_gate_flips_exactly_when_the_last_site_is_consumed():
    array = FakeArray(cols=2)
    ctx = _ctx(array)

    array.sites[0].used_up = True
    assert nucleus_sites_exhausted(ctx) is False

    array.sites[1].used_up = True
    assert nucleus_sites_exhausted(ctx) is True


def test_the_gate_is_false_again_after_a_clear():
    array = FakeArray(cols=2)
    for site in array.sites:
        site.used_up = True
    ctx = _ctx(array)
    assert nucleus_sites_exhausted(ctx) is True

    array.clearUsedUp()

    assert nucleus_sites_exhausted(ctx) is False


def test_the_gate_reports_exhausted_when_no_nucleus_site_is_assigned():
    """Nothing to deposit into is the same answer as nothing left to deposit
    into, so a protocol's gate still calls the operator over."""
    assert nucleus_sites_exhausted(_ctx(None)) is True


# -- the report -------------------------------------------------------------


def test_the_report_names_the_cell_in_each_tube(day_tree):
    day, make_cell = day_tree
    array = FakeArray(cols=3)
    for i, site in enumerate(array.sites):
        site.tube_id = f"PFS4_251103_{701 + i}"
    cell = make_cell("Slice_000", "Cell_000", nucleus_tube_id="PFS4_251103_701")
    make_cell("Slice_000", "Cell_003", nucleus_tube_id="PFS4_251103_702")

    report = build_tube_report(array, cell)

    lines = report.split("\n")
    assert lines[0].split() == ["tube", "position", "cell", "tube", "id"]
    assert lines[1].split() == ["0", "A01", "Slice_000/Cell_000", "PFS4_251103_701"]
    assert lines[2].split() == ["1", "A02", "Slice_000/Cell_003", "PFS4_251103_702"]
    assert lines[3].split() == ["2", "A03", "--", "PFS4_251103_703"]


def test_the_report_includes_cells_from_an_earlier_slice(day_tree):
    """A rack outlives a slice, so the walk starts at the Day directory: a
    slice-scoped report would silently drop the earlier slice's cells."""
    day, make_cell = day_tree
    array = FakeArray(cols=2)
    array.sites[0].tube_id = "T0"
    array.sites[1].tube_id = "T1"
    make_cell("Slice_000", "Cell_000", nucleus_tube_id="T0")
    current = make_cell("Slice_001", "Cell_000", nucleus_tube_id="T1")

    report = build_tube_report(array, current)

    assert "Slice_000/Cell_000" in report
    assert "Slice_001/Cell_000" in report


def test_the_report_joins_on_the_tube_id_not_the_position(day_tree):
    """Positions are reused by every rack; joining on them would attribute the
    previous rack's cell to a fresh tube in the same slot."""
    day, make_cell = day_tree
    make_cell(
        "Slice_000", "Cell_000", nucleus_tube_id="OLD_RACK_T0", nucleus_tube_position="A01"
    )
    array = FakeArray(cols=2)
    array.sites[0].tube_id = "NEW_RACK_T0"
    current = make_cell("Slice_001", "Cell_000")

    report = build_tube_report(array, current)

    assert "Cell_000" not in report.split("\n")[1]
    assert "NEW_RACK_T0" in report


def test_an_unlabelled_rack_reports_positions_with_empty_id_and_cell_columns(day_tree):
    day, make_cell = day_tree
    array = FakeArray(cols=2)
    current = make_cell("Slice_000", "Cell_000", nucleus_tube_id="T0")

    report = build_tube_report(array, current)

    lines = report.split("\n")
    assert lines[1].split() == ["0", "A01", "--"]
    assert lines[2].split() == ["1", "A02", "--"]


def test_the_report_is_empty_of_cells_when_the_day_directory_cannot_be_found(tmp_path):
    """A storage directory moved mid-session degrades rather than lying."""
    stray = dm.getDirHandle(str(tmp_path / "unmanaged"), create=True)
    array = FakeArray(cols=2)
    array.sites[0].tube_id = "T0"

    report = build_tube_report(array, stray)

    assert "T0" in report
    assert "--" in report


def test_the_report_with_no_directory_at_all_still_lists_the_rack():
    array = FakeArray(cols=2)
    array.sites[0].tube_id = "T0"

    report = build_tube_report(array, None)

    assert "T0" in report


def test_tube_report_action_retains_the_table_for_area_5(day_tree):
    day, make_cell = day_tree
    array = FakeArray(cols=2)
    array.sites[0].tube_id = "T0"
    current = make_cell("Slice_000", "Cell_000", nucleus_tube_id="T0")
    ctx = _ctx(array, current)
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )

    report = tube_report(ctx)

    assert "T0" in report
    assert details[0][0] == "text"
    assert details[0][1]["lines"] == report.split("\n")


# -- the swap ---------------------------------------------------------------


def _answer(monkeypatch, value, seen=None):
    """Stand in for the operator at the dialog. `value` is what prompt_tube_rack
    returns; `seen` collects the arguments it was called with."""

    def fake_prompt(title, text, rows, cols, make_ids, start_n, extra_text=None):
        if seen is not None:
            seen.append(
                dict(
                    title=title,
                    text=text,
                    rows=rows,
                    cols=cols,
                    make_ids=make_ids,
                    start_n=start_n,
                    extra_text=extra_text,
                )
            )
        return value(make_ids, start_n) if callable(value) else value

    monkeypatch.setattr(sites_mod, "prompt_tube_rack", fake_prompt)


def test_swap_clears_the_rack_and_writes_every_tube_id(monkeypatch):
    array = FakeArray(cols=4)
    for site in array.sites:
        site.used_up = True
    _answer(monkeypatch, lambda make_ids, start_n: (make_ids(start_n, False), start_n))

    assert swap_tubes(_ctx(array), id_format="PFS4_{tube_count + 701}_{well}") is True

    assert [site.used_up for site in array.sites] == [False] * 4
    assert [site.tube_id for site in array.sites] == [
        "PFS4_701_A01",
        "PFS4_702_A02",
        "PFS4_703_A03",
        "PFS4_704_A04",
    ]


def test_swap_advances_the_day_counter_past_the_whole_rack(monkeypatch):
    array = FakeArray(cols=4)
    _answer(monkeypatch, lambda make_ids, start_n: (make_ids(start_n, False), start_n))

    swap_tubes(_ctx(array), id_format="{tube_count}")

    assert array.files["tube_count"] == {"date": time.strftime("%y%m%d"), "count": 4}


def test_a_second_rack_continues_the_days_numbering(monkeypatch):
    array = FakeArray(cols=4)
    _answer(monkeypatch, lambda make_ids, start_n: (make_ids(start_n, False), start_n))
    ctx = _ctx(array)

    swap_tubes(ctx, id_format="T{tube_count}")
    assert array.sites[0].tube_id == "T0"

    swap_tubes(ctx, id_format="T{tube_count}")
    assert [site.tube_id for site in array.sites] == ["T4", "T5", "T6", "T7"]


def test_the_dialog_is_offered_the_rack_shape_and_todays_count(monkeypatch):
    array = FakeArray(rows=2, cols=3)
    array.writeConfigFile({"date": time.strftime("%y%m%d"), "count": 12}, "tube_count")
    seen = []
    _answer(monkeypatch, None, seen)

    swap_tubes(_ctx(array), id_format="{tube_count}")

    assert (seen[0]["rows"], seen[0]["cols"]) == (2, 3)
    assert seen[0]["start_n"] == 12


def test_an_operator_override_of_start_n_is_what_the_counter_advances_from(monkeypatch):
    array = FakeArray(cols=2)
    _answer(monkeypatch, lambda make_ids, start_n: (make_ids(900, False), 900))

    swap_tubes(_ctx(array), id_format="T{tube_count}")

    assert [site.tube_id for site in array.sites] == ["T900", "T901"]
    assert array.files["tube_count"]["count"] == 902


def test_swap_on_cancel_changes_nothing_and_returns_false(monkeypatch):
    array = FakeArray(cols=2)
    for site in array.sites:
        site.used_up = True
        site.tube_id = "OLD"
    _answer(monkeypatch, None)

    assert swap_tubes(_ctx(array), id_format="T{tube_count}") is False

    assert [site.used_up for site in array.sites] == [True, True]
    assert [site.tube_id for site in array.sites] == ["OLD", "OLD"]
    assert "tube_count" not in array.files


def test_the_dialog_shows_the_report_of_the_rack_being_removed(monkeypatch, day_tree):
    """Built before the clear, because clearUsedUp drops the tube ids the report
    joins on -- and because the operator reads it with the old rack in hand."""
    day, make_cell = day_tree
    array = FakeArray(cols=2)
    array.sites[0].tube_id = "OLD_T0"
    current = make_cell("Slice_000", "Cell_000", nucleus_tube_id="OLD_T0")
    seen = []
    _answer(monkeypatch, None, seen)

    swap_tubes(_ctx(array, current), id_format="T{tube_count}")

    assert "OLD_T0" in seen[0]["extra_text"]
    assert "Slice_000/Cell_000" in seen[0]["extra_text"]


def test_swap_retains_that_report_for_area_5(monkeypatch, day_tree):
    day, make_cell = day_tree
    array = FakeArray(cols=2)
    array.sites[0].tube_id = "OLD_T0"
    current = make_cell("Slice_000", "Cell_000", nucleus_tube_id="OLD_T0")
    _answer(monkeypatch, lambda make_ids, start_n: (make_ids(start_n, False), start_n))
    ctx = _ctx(array, current)
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )

    swap_tubes(ctx, id_format="T{tube_count}")

    assert details[0][0] == "text"
    assert any("OLD_T0" in line for line in details[0][1]["lines"])


def test_a_callable_id_format_is_used_for_every_tube(monkeypatch):
    array = FakeArray(cols=2)
    _answer(monkeypatch, lambda make_ids, start_n: (make_ids(start_n, False), start_n))

    swap_tubes(_ctx(array), id_format=lambda **ns: f"custom-{ns['well']}")

    assert [site.tube_id for site in array.sites] == ["custom-A01", "custom-A02"]


def test_swap_without_an_assigned_array_raises_a_named_orchestration_error():
    with pytest.raises(OrchestrationError) as exc:
        swap_tubes(_ctx(None), id_format="T{tube_count}")
    assert "nucleus" in str(exc.value)


def test_swap_with_a_standalone_site_assigned_raises(monkeypatch):
    """One well is not a rack: there is nothing to lay out a grid from."""
    site = FakeSite("NucleusWell")
    with pytest.raises(OrchestrationError):
        swap_tubes(_ctx(site), id_format="T{tube_count}")
