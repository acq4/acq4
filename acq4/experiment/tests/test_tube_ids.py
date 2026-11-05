"""Tests for tube identity: formatting one id, laying out a rack's fill order,
and the day-scoped counter."""
import time

import pytest

from acq4.experiment.tube_ids import (
    fill_order,
    format_tube_id,
    generate_tube_ids,
    read_tube_count,
    tube_position,
    well_label,
    write_tube_count,
)


# -- format_tube_id ---------------------------------------------------------


def test_strftime_codes_expand():
    assert format_tube_id("PFS4_%y%m%d") == "PFS4_" + time.strftime("%y%m%d")


def test_arithmetic_in_the_template_evaluates():
    assert format_tube_id("{tube_count + 701}", tube_count=12) == "713"


def test_the_operators_real_format_renders():
    expected = f"PFS4_{time.strftime('%y%m%d')}_713_A01"
    assert (
        format_tube_id(
            "PFS4_%y%m%d_{tube_count + 701}_{well}", tube_count=12, well="A01"
        )
        == expected
    )


@pytest.mark.parametrize(
    "template,expected",
    [
        ("{index}", "4"),
        ("{row}", "1"),
        ("{col}", "1"),
        ("{well}", "B02"),
        ("{tube_count}", "7"),
    ],
)
def test_every_namespace_name_is_reachable(template, expected):
    assert (
        format_tube_id(template, index=4, row=1, col=1, well="B02", tube_count=7)
        == expected
    )


def test_an_unknown_name_raises_value_error_naming_the_problem():
    with pytest.raises(ValueError) as exc:
        format_tube_id("{slice_name}", well="A01")
    assert "slice_name" in str(exc.value)


def test_a_syntax_error_raises_value_error_naming_the_template():
    with pytest.raises(ValueError) as exc:
        format_tube_id("{tube_count +}", tube_count=1)
    assert "{tube_count +}" in str(exc.value)


def test_a_callable_template_is_called_with_the_namespace():
    seen = {}

    def make(**namespace):
        seen.update(namespace)
        return "custom"

    assert format_tube_id(make, well="A01", tube_count=3) == "custom"
    assert seen == {"well": "A01", "tube_count": 3}


# -- positions --------------------------------------------------------------


@pytest.mark.parametrize(
    "index,cols,expected",
    [(0, 3, "A01"), (2, 3, "A03"), (3, 3, "B01"), (4, 3, "B02"), (0, 1, "A01")],
)
def test_well_label(index, cols, expected):
    assert well_label(index, cols) == expected


class _FakeArray:
    def __init__(self, sites, cols):
        self.sites = sites
        self.cols = cols

    def getFirstAvailableSite(self):
        return None


class _FakeSite:
    def __init__(self, name="Site", parent=None):
        self._name = name
        self._parent = parent

    def name(self):
        return self._name

    def parentDevice(self):
        return self._parent


def test_tube_position_is_the_well_label_within_its_array():
    sites = [_FakeSite(f"Rack[{i}]") for i in range(6)]
    array = _FakeArray(sites, cols=3)
    for site in sites:
        site._parent = array

    assert tube_position(sites[4]) == "B02"


def test_tube_position_of_a_standalone_site_is_its_device_name():
    assert tube_position(_FakeSite("NucleusWell")) == "NucleusWell"


# -- fill order and prefill -------------------------------------------------


def test_row_major_fill_order_is_plain_index_order():
    assert fill_order(2, 3) == [0, 1, 2, 3, 4, 5]


def test_column_major_fill_order_walks_down_each_column():
    assert fill_order(2, 3, column_major=True) == [0, 3, 1, 4, 2, 5]


def test_generate_numbers_tubes_in_row_major_fill_order():
    ids = generate_tube_ids("{tube_count}@{well}", rows=2, cols=3, start_n=10)
    assert ids == {
        0: "10@A01",
        1: "11@A02",
        2: "12@A03",
        3: "13@B01",
        4: "14@B02",
        5: "15@B03",
    }


def test_the_toggle_changes_only_the_counter_not_the_position():
    """well/row/col/index are physical; tube_count is the one name the fill
    order moves."""
    ids = generate_tube_ids(
        "{tube_count}@{well}", rows=2, cols=3, start_n=10, column_major=True
    )
    assert ids == {
        0: "10@A01",
        3: "11@B01",
        1: "12@A02",
        4: "13@B02",
        2: "14@A03",
        5: "15@B03",
    }


def test_start_n_shifts_every_number():
    ids = generate_tube_ids("{tube_count}", rows=1, cols=3, start_n=701)
    assert ids == {0: "701", 1: "702", 2: "703"}


def test_overrides_survive_regeneration_and_do_not_consume_a_number():
    """An operator's typed id stays as typed; the tubes around it keep the
    numbering they would have had."""
    ids = generate_tube_ids(
        "{tube_count}", rows=1, cols=3, start_n=10, overrides={1: "mine"}
    )
    assert ids == {0: "10", 1: "mine", 2: "12"}


# -- the day counter --------------------------------------------------------


class _FakeConfigDevice:
    """Stands in for the array's Device config-file storage."""

    def __init__(self, files=None):
        self.files = dict(files or {})

    def readConfigFile(self, filename):
        return self.files.get(filename, {})

    def writeConfigFile(self, data, filename):
        self.files[filename] = dict(data)


def test_a_missing_record_reads_as_zero():
    assert read_tube_count(_FakeConfigDevice()) == 0


def test_the_count_round_trips_within_the_same_day():
    array = _FakeConfigDevice()
    write_tube_count(array, 12)
    assert read_tube_count(array) == 12


def test_a_record_from_another_date_reads_as_zero():
    array = _FakeConfigDevice({"tube_count": {"date": "010101", "count": 99}})
    assert read_tube_count(array) == 0


def test_the_written_record_carries_todays_date():
    array = _FakeConfigDevice()
    write_tube_count(array, 4)
    assert array.files["tube_count"] == {"date": time.strftime("%y%m%d"), "count": 4}


def test_a_callable_template_that_raises_becomes_a_value_error():
    def make(**ns):
        raise KeyError("nope")

    with pytest.raises(ValueError, match="make"):
        format_tube_id(make, well="A01")


def test_a_non_string_template_becomes_a_value_error():
    with pytest.raises(ValueError, match="42"):
        format_tube_id(42, well="A01")
