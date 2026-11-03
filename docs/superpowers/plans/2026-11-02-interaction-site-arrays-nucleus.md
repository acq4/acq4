# InteractionSiteArray Nucleus Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an Autopatch protocol deposit each cell's nucleus into its own tube in an `InteractionSiteArray`, notice when the rack is exhausted, have the operator label and swap the rack, and report which cell went into which tube.

**Architecture:** Three layers, each testable alone. The *device* layer gains a persisted `tube_id` on `InteractionSite` plus three accessors that expose state already present (`InteractionSiteArray.clearUsedUp/rows/cols`, `Pipette.getSiteDeviceFor`). The *id* layer (`acq4/experiment/tube_ids.py`) is pure functions over a template string and a day-scoped counter; nothing downstream ever sees a template, a counter or a date, only plain id strings. The *action* layer (`actions/fsm.py`, `actions/device.py`, a new `actions/sites.py`) drives the FSM, marks the tube used, writes the tube onto the cell directory's `.index`, and derives the report back out of those `.index` entries.

**Tech Stack:** Python 3, PyQt (via `acq4.util.Qt`), pytest + pytest-qt, acq4's `Device` config-file persistence, acq4's `DirHandle` managed directories.

**Spec:** `docs/superpowers/specs/2026-11-02-interaction-site-arrays-nucleus-design.md`

## Global Constraints

- **Python interpreter:** `/home/martin/.miniforge3/envs/acq4-gl/bin/python`. Every `pytest` command below runs as `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest ...` from the repo root (`/home/martin/src/acq4/acq4/.claude/worktrees/interaction-site-arrays-nucleus-053b36`).
- **Branch:** `claude/interaction-site-arrays-nucleus-053b36`, off `mini-rig`. Never commit to `_staging`.
- **Commits:** conventional format, imperative mood, `--author="Martin Chase (claude) <outofculture@gmail.com>"`, body ending with the two attribution lines this session uses. Never `--no-verify`.
- **TDD is mandatory.** Every task below writes the failing test first and runs it to watch it fail before any implementation line is written.
- **Comments:** default to none. Add one only where it carries something the code cannot (a distant interplay, a hazard, a rationale unrecoverable from reading the function). The comments quoted in the code blocks below are the ones that earn their place; do not add others.
- **Pre-existing test failures on this branch.** The baseline is **8 failures, 776 passed** across `acq4/experiment/tests` and `acq4/modules/Autopatch/tests/test_example_protocols.py`:
  - 6 in `test_example_protocols.py`, because `example_patch.py` on `mini-rig` dropped the `check_cell_present` param and gained `post_task_cellfie_preset` without its tests following.
  - 2 in `test_actions_fsm.py` (`test_the_live_plot_updates_from_a_test_pulse_emitted_on_another_thread`, `test_the_live_plot_disconnects_when_mounting_the_widget_fails`).

  **Do not fix them.** They are unrelated to this work. Task 6 edits `test_example_protocols.py`; leave the six failing assertions exactly as they are and change only the lists of bundled protocol filenames. After every task, the failure count must still be 8 — that is the regression check, not "all green".

- **Vocabulary.** A *site* is one `InteractionSite` (one tube). An *array* is the `InteractionSiteArray` holding them (the rack). `ctx.pipette` is a `PatchPipette`; the device that carries site-role assignments is `ctx.pipette.pipetteDevice` (a `Pipette`). Getting that wrong is the single easiest mistake in this plan.

---

## File Structure

**Created:**

| Path | Responsibility |
| --- | --- |
| `acq4/experiment/tube_ids.py` | Tube identity: format one id from a template, lay out a rack's fill order, read/write the day counter. Pure functions, no Qt, no context. |
| `acq4/experiment/tests/test_tube_ids.py` | Unit tests for the above. |
| `acq4/util/TubeRackPrompt.py` | The rack-swap dialog: a grid of line edits mirroring the array, a start-n spinbox, a fill-order toggle. Knows nothing of templates, counters or dates — it is handed a callable that makes ids. |
| `acq4/util/tests/test_tube_rack_prompt.py` | Widget and thread-marshalling tests for the dialog. |
| `acq4/experiment/actions/sites.py` | The three site-level actions (`nucleus_sites_exhausted`, `swap_tubes`, `tube_report`) and the report builder. |
| `acq4/experiment/tests/test_actions_sites.py` | Integration tests for the above. |
| `acq4/modules/Autopatch/example_protocols/example_patch_seq.py` | The bundled patch-seq example protocol. |

**Modified:**

| Path | Change |
| --- | --- |
| `acq4/devices/InteractionSite.py` | Add persisted `tube_id` + `sigTubeIdChanged`, mirroring `used_up`. |
| `acq4/devices/InteractionSiteArray.py` | Add `clearUsedUp()`, `rows`, `cols`; the GUI calls them instead of reaching inside. |
| `acq4/devices/Pipette/pipette.py` | Extract `getSiteDeviceFor(role)` out of `getSiteFor(role)`. |
| `acq4/experiment/actions/fsm.py` | Add `home_with_nucleus` and `collect`. |
| `acq4/experiment/actions/device.py` | Add `snap`. |
| `acq4/experiment/actions/__init__.py` | Export the new actions. |
| `acq4/devices/tests/test_interaction_site.py` | Tests for `tube_id`. |
| `acq4/devices/tests/test_interaction_site_array.py` | Tests for `clearUsedUp`, `rows`, `cols`. |
| `acq4/devices/Pipette/tests/test_pipette_site_assignment.py` | Tests for `getSiteDeviceFor`; attach it to the stub. |
| `acq4/experiment/tests/test_actions_fsm.py` | Tests for `collect` and `home_with_nucleus`. |
| `acq4/experiment/tests/test_actions_device.py` | Tests for `snap`. |
| `acq4/modules/Autopatch/tests/test_example_protocols.py` | List the third bundled example; e2e test for the protocol. |

---

## Deviations from the spec

Two, both deliberate, both narrowing what crosses a boundary:

1. **`prompt_tube_rack` takes `make_ids`, not `defaults`.** Spec §3 gives the signature
   `prompt_tube_rack(title, text, rows, cols, defaults, start_n, extra_text=None)`. A fixed
   `defaults` dict cannot answer the start-n spinbox or the fill-order toggle, both of which
   have to refill the grid. The dialog therefore takes `make_ids(start_n, column_major) -> dict[int, str]`
   and calls it whenever either control changes. This is what keeps `acq4/util/` free of the
   template/counter/date vocabulary the spec's Containment section draws a box around — and
   avoids `acq4/util/` importing from `acq4/experiment/`, which would invert the layering.
2. **The prefill function lives in `tube_ids.py`, not in the dialog module.** Spec §3 says the
   prefill logic "is a pure function, tested without a widget" but does not say where. It is
   `generate_tube_ids`, next to `format_tube_id`, for the same containment reason.

---

### Task 1: Expose what is already there (refactor)

Three behaviour-preserving extractions, all inside code the feature touches. They land in one
`refactor:` commit **before any feature commit**, so no later diff mixes "moved" with "new".

`clearUsedUp()` here clears `used_up` only. `tube_id` does not exist yet; Task 2 extends it.
That is deliberate — a refactor commit that cleared a field nobody had added would not be a
refactor.

**Files:**
- Modify: `acq4/devices/InteractionSiteArray.py`
- Modify: `acq4/devices/Pipette/pipette.py:1310-1332`
- Test: `acq4/devices/tests/test_interaction_site_array.py`
- Test: `acq4/devices/Pipette/tests/test_pipette_site_assignment.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `InteractionSiteArray.rows -> int`, `InteractionSiteArray.cols -> int` (read-only properties)
  - `InteractionSiteArray.clearUsedUp() -> None`
  - `Pipette.getSiteDeviceFor(role: str) -> InteractionSite | InteractionSiteArray | None`

- [ ] **Step 1: Write the failing tests**

Append to `acq4/devices/tests/test_interaction_site_array.py`:

```python
class TestGridAccessors:
    def test_rows_and_cols_report_the_configured_grid(self, make_array):
        arr = make_array(rows=2, cols=3)
        assert (arr.rows, arr.cols) == (2, 3)


class TestClearUsedUp:
    def test_clears_every_used_site(self, make_array):
        arr = make_array(rows=2, cols=2)
        for site in arr.sites:
            site.used_up = True

        arr.clearUsedUp()

        assert [site.used_up for site in arr.sites] == [False] * 4

    def test_is_a_no_op_on_sites_that_were_already_clear(self, make_array):
        arr = make_array(rows=1, cols=2)
        arr.sites[0].used_up = True

        arr.clearUsedUp()

        assert [site.used_up for site in arr.sites] == [False, False]

    def test_an_array_with_no_used_sites_is_available_again_afterwards(self, make_array):
        arr = make_array(rows=1, cols=2)
        for site in arr.sites:
            site.used_up = True
        assert arr.getFirstAvailableSite() is None

        arr.clearUsedUp()

        assert arr.getFirstAvailableSite() is arr.sites[0]
```

Append to `acq4/devices/Pipette/tests/test_pipette_site_assignment.py` — and first add the new
method to the stub in `_make_pipette`, next to the other attached methods:

```python
    _StubPipette.getSiteDeviceFor = Pipette.getSiteDeviceFor
```

```python
class TestGetSiteDeviceFor:
    def test_returns_none_when_no_device_is_assigned(self, qt_app):
        pip, _, _ = _make_pipette()
        assert pip.getSiteDeviceFor('nucleus') is None

    def test_returns_a_plain_site_unchanged(self, qt_app):
        site = MagicMock(spec=['name'])
        site.name.return_value = 'Well1'
        pip, _, _ = _make_pipette(saved_sites={'nucleus': 'Well1'}, devices={'Well1': site})

        assert pip.getSiteDeviceFor('nucleus') is site

    def test_returns_the_array_itself_not_one_of_its_sites(self, qt_app):
        """This is the whole point of the method: getSiteFor narrows an array to
        its first available site, which is None once the rack is exhausted --
        exactly when a caller most needs to reach the array."""
        array = MagicMock()
        array.role = 'nucleus'
        array.getFirstAvailableSite.return_value = None
        pip, _, _ = _make_pipette(saved_sites={'nucleus': 'Rack'}, devices={'Rack': array})

        assert pip.getSiteFor('nucleus') is None
        assert pip.getSiteDeviceFor('nucleus') is array

    def test_returns_none_for_an_array_whose_role_does_not_match(self, qt_app):
        array = MagicMock()
        array.role = 'clean'
        pip, _, _ = _make_pipette(saved_sites={'nucleus': 'Rack'}, devices={'Rack': array})

        assert pip.getSiteDeviceFor('nucleus') is None

    def test_returns_none_when_the_assigned_device_is_gone(self, qt_app):
        pip, _, _ = _make_pipette(saved_sites={'nucleus': 'Vanished'}, devices={})

        assert pip.getSiteDeviceFor('nucleus') is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/devices/tests/test_interaction_site_array.py -k "GridAccessors or ClearUsedUp" acq4/devices/Pipette/tests/test_pipette_site_assignment.py -k "GetSiteDeviceFor" -v
```
Expected: `AttributeError: 'InteractionSiteArray' object has no attribute 'rows'` and
`AttributeError: type object 'Pipette' has no attribute 'getSiteDeviceFor'`.

- [ ] **Step 3: Add the array accessors**

In `acq4/devices/InteractionSiteArray.py`, in the "Site access" section just below the existing
`role` property:

```python
    @property
    def rows(self) -> int:
        return self._rows

    @property
    def cols(self) -> int:
        return self._cols
```

And below `getFirstAvailableSite`:

```python
    def clearUsedUp(self):
        """Mark every site in this array as available again."""
        for site in self._sites:
            site.used_up = False
```

Then point the GUI at them. In `InteractionSiteArrayDeviceGui.__init__`:

```python
        cols = dev.cols
```

in `_styleSiteButton`:

```python
        row, col = divmod(index, self.dev.cols)
```

in `_markAllUnused`:

```python
    def _markAllUnused(self):
        self.dev.clearUsedUp()
```

and in the calibration group's label:

```python
        calib_layout.addWidget(Qt.QLabel(f"Grid: {dev.rows} × {dev.cols}"), 1, 0)
```

- [ ] **Step 4: Extract `getSiteDeviceFor`**

Replace `getSiteFor` in `acq4/devices/Pipette/pipette.py` with the pair:

```python
    def getSiteDeviceFor(self, role: str):
        """Return the device assigned to this pipette for *role* -- an
        InteractionSite or an InteractionSiteArray -- or None.

        Unlike getSiteFor, an array is returned as itself rather than narrowed
        to its first available site, so a caller can still reach the array once
        every site in it is used up.
        """
        name = self._site_assignments.get(role)
        if name is None:
            return None
        try:
            device = self.dm.getDevice(name)
        except Exception:
            return None
        if device is None:
            return None
        if hasattr(device, 'getFirstAvailableSite') and getattr(device, 'role', None) != role:
            return None
        return device

    def getSiteFor(self, role: str) -> "InteractionSite | None":
        """Return the interaction site assigned to this pipette for *role*.

        If the assigned device is an InteractionSiteArray (has getFirstAvailableSite),
        its role must match *role* and the first available site is returned.
        Returns None if no site is assigned or if the assigned device no longer exists.
        """
        device = self.getSiteDeviceFor(role)
        if device is not None and hasattr(device, 'getFirstAvailableSite'):
            return device.getFirstAvailableSite()
        return device
```

- [ ] **Step 5: Run the tests to verify they pass**

Run:
```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/devices/tests/test_interaction_site_array.py acq4/devices/tests/test_interaction_site.py acq4/devices/Pipette/tests/test_pipette_site_assignment.py -q
```
Expected: all pass, no failures.

- [ ] **Step 6: Commit**

```bash
git add acq4/devices/InteractionSiteArray.py acq4/devices/Pipette/pipette.py acq4/devices/tests/test_interaction_site_array.py acq4/devices/Pipette/tests/test_pipette_site_assignment.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "refactor: expose array grid, clearUsedUp, and the assigned site device"
```

---

### Task 2: Tube identity

`tube_ids.py` plus the persisted `tube_id` on a site. This is the whole date/template/counter
mechanism, and it all lives here.

**Files:**
- Create: `acq4/experiment/tube_ids.py`
- Create: `acq4/experiment/tests/test_tube_ids.py`
- Modify: `acq4/devices/InteractionSite.py`
- Modify: `acq4/devices/InteractionSiteArray.py` (extend `clearUsedUp`)
- Test: `acq4/devices/tests/test_interaction_site.py`
- Test: `acq4/devices/tests/test_interaction_site_array.py`

**Interfaces:**
- Consumes: `InteractionSiteArray.rows`, `.cols`, `.clearUsedUp()` (Task 1).
- Produces:
  - `format_tube_id(template, **namespace) -> str` — `template` is a str or a callable taking the namespace as keywords.
  - `well_label(index: int, cols: int) -> str` — `"A01"`-style label from a 0-based site index.
  - `tube_position(site) -> str` — the site's well label within its array, or its device name when it has no array parent.
  - `fill_order(rows: int, cols: int, column_major: bool = False) -> list[int]` — site indices in fill order.
  - `generate_tube_ids(template, rows, cols, start_n, column_major=False, overrides=None) -> dict[int, str]`
  - `read_tube_count(array) -> int`, `write_tube_count(array, count: int) -> None`
  - `InteractionSite.tube_id: str | None` (settable, persisted) and `InteractionSite.sigTubeIdChanged`.

- [ ] **Step 1: Write the failing tests for `tube_ids`**

Create `acq4/experiment/tests/test_tube_ids.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_tube_ids.py -q
```
Expected: collection error — `ModuleNotFoundError: No module named 'acq4.experiment.tube_ids'`.

- [ ] **Step 3: Write `tube_ids.py`**

Create `acq4/experiment/tube_ids.py`:

```python
"""Tube identity for an InteractionSiteArray: format one tube's id from an
operator's template, lay out a rack's fill order, and keep the day's running
tube count."""
from __future__ import annotations

import time

_COUNT_FILE = "tube_count"
_DATE_FORMAT = "%y%m%d"


def format_tube_id(template, **namespace) -> str:
    """Render one tube's id.

    `template` is either a callable taking the namespace as keywords, or a
    string run first through time.strftime (so %y%m%d and friends expand) and
    then evaluated as an f-string against the namespace (so {tube_count + 701}
    does). Both halves have precedent in this tree: storage.create_data_dir
    runs folder-type names through strftime, and NucleusCollectState evaluates
    its pressureSequence config string.

    Raises ValueError naming the problem for a template the operator got wrong,
    so the dialog can show it in place rather than failing a run.
    """
    if callable(template):
        return str(template(**namespace))
    dated = time.strftime(template)
    try:
        return eval(f"f{dated!r}", {}, dict(namespace))
    except Exception as exc:
        raise ValueError(f"could not format tube id from {template!r}: {exc}") from exc


def well_label(index: int, cols: int) -> str:
    """The "A01"-style label for a 0-based site index in a grid `cols` wide."""
    row, col = divmod(index, cols)
    return f"{chr(ord('A') + row)}{col + 1:02d}"


def tube_position(site) -> str:
    """The site's well label within its array, or its device name when it has no
    array parent (a standalone site assigned directly to a role)."""
    array = site.parentDevice()
    if array is None or not hasattr(array, "getFirstAvailableSite"):
        return site.name()
    return well_label(array.sites.index(site), array.cols)


def fill_order(rows: int, cols: int, column_major: bool = False) -> list[int]:
    """Site indices in the order the operator fills them."""
    if not column_major:
        return list(range(rows * cols))
    return [r * cols + c for c in range(cols) for r in range(rows)]


def tube_namespace(index: int, cols: int, tube_count: int) -> dict:
    """The names a template may use for one tube.

    index/row/col/well are the site's physical position and do not move with
    the fill order; tube_count is the day's running number for this tube, and
    is the one name the fill order changes.
    """
    row, col = divmod(index, cols)
    return {
        "index": index,
        "row": row,
        "col": col,
        "well": well_label(index, cols),
        "tube_count": tube_count,
    }


def generate_tube_ids(
    template,
    rows: int,
    cols: int,
    start_n: int,
    column_major: bool = False,
    overrides: "dict[int, str] | None" = None,
) -> dict:
    """{site index: id} for a whole rack, numbered from `start_n` along the
    chosen fill order. An overridden index keeps the operator's text and still
    consumes its place in the numbering, so the tubes around it do not shift
    when one is retyped.
    """
    overrides = overrides or {}
    ids = {}
    for ordinal, index in enumerate(fill_order(rows, cols, column_major)):
        if index in overrides:
            ids[index] = overrides[index]
            continue
        ids[index] = format_tube_id(
            template, **tube_namespace(index, cols, start_n + ordinal)
        )
    return ids


def read_tube_count(array) -> int:
    """The number of tubes filled today, or 0 when the stored record is from
    another date.

    Stored through the array's own config file, which is why it survives both a
    restart and a move to the next slice: there is no code for either, only the
    file's placement.
    """
    record = array.readConfigFile(_COUNT_FILE) or {}
    if record.get("date") != time.strftime(_DATE_FORMAT):
        return 0
    return int(record.get("count", 0))


def write_tube_count(array, count: int) -> None:
    """Record today's running tube count for this array."""
    array.writeConfigFile(
        {"date": time.strftime(_DATE_FORMAT), "count": int(count)}, _COUNT_FILE
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_tube_ids.py -q
```
Expected: all pass.

- [ ] **Step 5: Write the failing tests for `tube_id`**

Append to `acq4/devices/tests/test_interaction_site.py`:

```python
class TestTubeId:
    def test_tube_id_defaults_to_none(self, make_site):
        site = make_site()
        assert site.tube_id is None

    def test_tube_id_loaded_from_saved_positions(self, make_site):
        site = make_site(
            saved_positions={'TestSite': {'tube_id': 'PFS4_251103_701_A01', 'offset': [0, 0, 0]}}
        )
        assert site.tube_id == 'PFS4_251103_701_A01'

    def test_tube_id_setter_writes_to_config(self, make_site):
        site = make_site()
        site.tube_id = 'PFS4_251103_701_A01'
        args = site.dm.writeConfigFile.call_args[0]
        assert args[0].get('TestSite', {}).get('tube_id') == 'PFS4_251103_701_A01'

    def test_tube_id_signal_emitted(self, make_site, qt_app):
        site = make_site()
        emitted = []
        site.sigTubeIdChanged.connect(emitted.append)
        site.tube_id = 'T1'
        from acq4.util import Qt
        Qt.QApplication.processEvents()
        assert emitted == ['T1']

    def test_tube_id_signal_not_emitted_if_unchanged(self, make_site, qt_app):
        site = make_site()
        site.tube_id = 'T1'
        emitted = []
        site.sigTubeIdChanged.connect(emitted.append)
        site.tube_id = 'T1'
        from acq4.util import Qt
        Qt.QApplication.processEvents()
        assert emitted == []
```

And append to `acq4/devices/tests/test_interaction_site_array.py`, inside `TestClearUsedUp`:

```python
    def test_clears_tube_ids_too(self, make_array):
        """A new rack gets new labels, so the old rack's ids must not survive the
        clear -- which is why swap_tubes builds its report BEFORE clearing."""
        arr = make_array(rows=1, cols=2)
        for i, site in enumerate(arr.sites):
            site.used_up = True
            site.tube_id = f"T{i}"

        arr.clearUsedUp()

        assert [site.tube_id for site in arr.sites] == [None, None]
```

- [ ] **Step 6: Run the tests to verify they fail**

Run:
```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/devices/tests/test_interaction_site.py -k TubeId acq4/devices/tests/test_interaction_site_array.py -k tube_ids -v
```
Expected: `AttributeError: 'InteractionSite' object has no attribute 'tube_id'`.

- [ ] **Step 7: Add `tube_id`**

In `acq4/devices/InteractionSite.py`, next to the other signals:

```python
    sigTubeIdChanged = Qt.Signal(object)
```

in `__init__`, next to `self._used_up`:

```python
        self._tube_id = site_data.get('tube_id', None)
```

and below the `used_up` property:

```python
    @property
    def tube_id(self) -> "str | None":
        """The operator's label for whatever is currently in this site."""
        return self._tube_id

    @tube_id.setter
    def tube_id(self, value: "str | None"):
        if value == self._tube_id:
            return
        self._tube_id = value
        self.positions.setdefault(self.name(), {})['tube_id'] = value
        self.writeConfigFile(self.positions, "saved_positions")
        self.sigTubeIdChanged.emit(value)
```

In `acq4/devices/InteractionSiteArray.py`, extend `clearUsedUp`:

```python
    def clearUsedUp(self):
        """Mark every site in this array as available again and drop its tube id."""
        for site in self._sites:
            site.used_up = False
            site.tube_id = None
```

- [ ] **Step 8: Run the tests to verify they pass**

Run:
```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/devices/tests/ acq4/experiment/tests/test_tube_ids.py -q
```
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add acq4/experiment/tube_ids.py acq4/experiment/tests/test_tube_ids.py acq4/devices/InteractionSite.py acq4/devices/InteractionSiteArray.py acq4/devices/tests/test_interaction_site.py acq4/devices/tests/test_interaction_site_array.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "feat: tube ids and a day-scoped tube counter for interaction site arrays"
```

---

### Task 3: The rack-swap dialog

A sibling to `PromptUser.py`, under the same discipline: built, shown and destroyed entirely on
the GUI thread, with only plain data crossing back to the calling worker thread.

The module is split into a `TubeRackDialog` widget and a `prompt_tube_rack` marshalling
function, so the grid behaviour can be tested with `qtbot` directly instead of through the
blocking call.

**Files:**
- Create: `acq4/util/TubeRackPrompt.py`
- Create: `acq4/util/tests/test_tube_rack_prompt.py`

**Interfaces:**
- Consumes: nothing from earlier tasks. `make_ids` is supplied by the caller (Task 5 builds it out of `generate_tube_ids`).
- Produces:
  - `TubeRackDialog(title, text, rows, cols, make_ids, start_n, extra_text=None, parent=None)` with `result_ids() -> dict[int, str]` and `start_n() -> int`.
  - `prompt_tube_rack(title, text, rows, cols, make_ids, start_n, extra_text=None, parent=None) -> tuple[dict[int, str], int] | None`
  - `_gui_available() -> bool` — the seam tests monkeypatch to force the headless path.

- [ ] **Step 1: Write the failing tests**

Create `acq4/util/tests/test_tube_rack_prompt.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/util/tests/test_tube_rack_prompt.py -q
```
Expected: collection error — `ModuleNotFoundError: No module named 'acq4.util.TubeRackPrompt'`.

- [ ] **Step 3: Write `TubeRackPrompt.py`**

Create `acq4/util/TubeRackPrompt.py`:

```python
"""Tube-rack swap dialog: a grid of id fields laid out like the rack, with a
start-number spinbox and a fill-order toggle that refill it.

The dialog is built, shown, and destroyed entirely on the GUI thread. A worker
thread calling prompt_tube_rack() only ever receives plain data -- a dict of
strings and an int, or None; no QWidget/QObject reference crosses the thread
boundary.

This module knows nothing about id templates, dates or tube counters. It is
handed a `make_ids(start_n, column_major) -> {site index: id}` callable and
calls it whenever either control changes.
"""
from __future__ import annotations

from acq4.util import Qt
from acq4.util.task import Event, run_in_gui_thread

# Dialogs currently on screen, keyed by id(dialog), for the same reason
# PromptUser keeps _live_boxes: it holds each one alive between show() and the
# operator's click without handing a widget reference to the calling thread.
_live_dialogs = {}


def _gui_available() -> bool:
    return Qt.QApplication.instance() is not None


class TubeRackDialog(Qt.QDialog):
    """The grid itself. Built and driven only on the GUI thread."""

    def __init__(self, title, text, rows, cols, make_ids, start_n, extra_text=None, parent=None):
        Qt.QDialog.__init__(self, parent)
        self.setWindowTitle(title)
        self.setWindowModality(Qt.Qt.NonModal)
        self._make_ids = make_ids
        # Indices the operator has typed into; these keep their text through
        # every refill.
        self._overrides = {}
        self.fields = {}

        layout = Qt.QVBoxLayout(self)
        layout.addWidget(Qt.QLabel(text))

        controls = Qt.QHBoxLayout()
        controls.addWidget(Qt.QLabel("First tube number:"))
        self.startSpin = Qt.QSpinBox()
        self.startSpin.setRange(0, 999999)
        self.startSpin.setValue(start_n)
        controls.addWidget(self.startSpin)
        self.columnMajorCheck = Qt.QCheckBox("Fill down columns")
        controls.addWidget(self.columnMajorCheck)
        controls.addStretch()
        layout.addLayout(controls)

        gridWidget = Qt.QWidget()
        self.gridLayout = Qt.QGridLayout(gridWidget)
        for index in range(rows * cols):
            row, col = divmod(index, cols)
            field = Qt.QLineEdit()
            # textEdited, not textChanged: it fires only for the operator's own
            # typing, so a refill below never records itself as an override.
            field.textEdited.connect(lambda _text, i=index: self._onFieldEdited(i))
            self.gridLayout.addWidget(field, row, col)
            self.fields[index] = field
        layout.addWidget(gridWidget)

        self.errorLabel = Qt.QLabel("")
        layout.addWidget(self.errorLabel)

        if extra_text:
            report = Qt.QPlainTextEdit(extra_text)
            report.setReadOnly(True)
            layout.addWidget(report)

        buttons = Qt.QDialogButtonBox(
            Qt.QDialogButtonBox.StandardButton.Ok | Qt.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.startSpin.valueChanged.connect(self._refill)
        self.columnMajorCheck.toggled.connect(self._refill)
        self._refill()

    def _onFieldEdited(self, index):
        self._overrides[index] = self.fields[index].text()

    def _refill(self):
        try:
            ids = self._make_ids(self.startSpin.value(), self.columnMajorCheck.isChecked())
        except ValueError as exc:
            self.errorLabel.setText(str(exc))
            ids = {}
        else:
            self.errorLabel.setText("")
        for index, field in self.fields.items():
            if index in self._overrides:
                continue
            field.setText(ids.get(index, ""))

    def result_ids(self) -> dict:
        return {index: field.text() for index, field in self.fields.items()}

    def start_n(self) -> int:
        return self.startSpin.value()


def prompt_tube_rack(title, text, rows, cols, make_ids, start_n, extra_text=None, parent=None):
    """Ask the operator to label a freshly loaded rack.

    Returns ({site index: id string}, confirmed start number), or None if they
    cancelled.

    Headless (no QApplication) returns the generated ids unedited, the way
    actions.prompt.prompt returns its first choice when there is no UI. A
    make_ids that raises there comes back as empty ids rather than as a failed
    run: an id is a label, and losing one must not stop an experiment.
    """
    if not _gui_available():
        try:
            return make_ids(start_n, False), start_n
        except ValueError:
            return {}, start_n
    done = Event()
    result = {}
    run_in_gui_thread(
        _make_dialog, title, text, rows, cols, make_ids, start_n, extra_text, parent, done, result
    )
    done.wait()
    return result["value"]


def _make_dialog(title, text, rows, cols, make_ids, start_n, extra_text, parent, done, result):
    """Build and show the dialog, and arrange for its own teardown -- all on the
    GUI thread, for the reason PromptUser._make_message_box is."""
    dialog = TubeRackDialog(title, text, rows, cols, make_ids, start_n, extra_text, parent)

    def _finished(code):
        if code == Qt.QDialog.DialogCode.Accepted:
            result["value"] = (dialog.result_ids(), dialog.start_n())
        else:
            result["value"] = None
        _live_dialogs.pop(id(dialog), None)
        dialog.deleteLater()
        done.set()

    dialog.finished.connect(_finished)
    _live_dialogs[id(dialog)] = dialog
    dialog.show()
    dialog.raise_()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/util/tests/test_tube_rack_prompt.py -q
```
Expected: all pass.

If `Qt.QDialogButtonBox` / `Qt.QSpinBox` / `Qt.QLineEdit` are not re-exported by `acq4.util.Qt`,
check how a neighbouring module imports them (`acq4/util/Qt/__init__.py` re-exports the binding's
widgets wholesale) and follow that; do not add a direct PyQt import.

- [ ] **Step 5: Commit**

```bash
git add acq4/util/TubeRackPrompt.py acq4/util/tests/test_tube_rack_prompt.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "feat: tube rack swap dialog"
```

---

### Task 4: The nucleus-extraction actions

`home_with_nucleus` and `collect` in `fsm.py`, `snap` in `device.py`. `collect` is the only one
with behaviour beyond driving the FSM: it marks the tube used and records it on the cell.

**Files:**
- Modify: `acq4/experiment/actions/fsm.py`
- Modify: `acq4/experiment/actions/device.py`
- Modify: `acq4/experiment/actions/__init__.py`
- Test: `acq4/experiment/tests/test_actions_fsm.py`
- Test: `acq4/experiment/tests/test_actions_device.py`

**Interfaces:**
- Consumes: `tube_ids.tube_position(site)` (Task 2); `InteractionSite.tube_id` (Task 2).
- Produces:
  - `home_with_nucleus(ctx, **entry_config) -> str`
  - `collect(ctx, mark_used: bool = True, **entry_config) -> str`
  - `snap(ctx, name: str = "image") -> None`
  - `.index` keys written by `collect`: `nucleus_tube_id` (str) and `nucleus_tube_position` (str).

- [ ] **Step 1: Write the failing tests for the FSM actions**

Append to `acq4/experiment/tests/test_actions_fsm.py`. Add the imports at the top of the file:

```python
from acq4.experiment.actions.fsm import patch, reseal, clean, collect, home_with_nucleus
```

and append:

```python
# -- collect / home_with_nucleus ---------------------------------------------


class _FakeSite:
    def __init__(self, name="Rack[1]", tube_id="PFS4_251103_702_A02"):
        self._name = name
        self.tube_id = tube_id
        self.used_up = False
        self.parent = None

    def name(self):
        return self._name

    def parentDevice(self):
        return self.parent


class _FakeArray:
    def __init__(self, sites, cols):
        self.sites = sites
        self.cols = cols
        for site in sites:
            site.parent = self

    def getFirstAvailableSite(self):
        for site in self.sites:
            if not site.used_up:
                return site
        return None


class _FakePipetteDevice:
    def __init__(self, site=None):
        self.site = site

    def getSiteFor(self, role):
        assert role == "nucleus"
        return self.site


class _FakeCellDir:
    def __init__(self):
        self.info_written = {}

    def setInfo(self, info):
        self.info_written.update(info)


class _FakeManager:
    def __init__(self, cell_dir=None):
        self.cell_dir = cell_dir if cell_dir is not None else _FakeCellDir()

    def getCurrentDir(self):
        return self.cell_dir


def _collect_ctx(pip, site, cell_dir=None):
    pip.pipetteDevice = _FakePipetteDevice(site)
    return ExecutionContext(pipette=pip, manager=_FakeManager(cell_dir))


def _rack(cols=2, count=2):
    sites = [_FakeSite(f"Rack[{i}]", f"T{i}") for i in range(count)]
    return _FakeArray(sites, cols=cols), sites


def test_home_with_nucleus_enters_at_its_own_state(fake_pip_factory):
    pip = fake_pip_factory(["out"])
    assert home_with_nucleus(_ctx(pip)) == "out"
    assert pip.setState_calls[0][0] == "home with nucleus"


def test_home_with_nucleus_opens_one_area_5_row(fake_pip_factory):
    pip = fake_pip_factory(["out"])
    ctx = _ctx(pip)
    names = _entry_names(ctx)
    home_with_nucleus(ctx)
    assert names == ["Home With Nucleus"]


def test_collect_enters_at_collect(fake_pip_factory):
    _, sites = _rack()
    pip = fake_pip_factory(["out"])
    assert collect(_collect_ctx(pip, sites[0])) == "out"
    assert pip.setState_calls[0][0] == "collect"


def test_collect_marks_the_site_the_state_used(fake_pip_factory):
    _, sites = _rack()
    pip = fake_pip_factory(["out"])

    collect(_collect_ctx(pip, sites[0]))

    assert sites[0].used_up is True
    assert sites[1].used_up is False


def test_collect_writes_both_index_keys(fake_pip_factory):
    array, sites = _rack(cols=2, count=4)
    sites[1].tube_id = "PFS4_251103_702_A02"
    pip = fake_pip_factory(["out"])
    cell_dir = _FakeCellDir()

    collect(_collect_ctx(pip, sites[1], cell_dir))

    assert cell_dir.info_written == {
        "nucleus_tube_id": "PFS4_251103_702_A02",
        "nucleus_tube_position": "A02",
    }


def test_collect_records_an_unlabelled_tube_as_an_empty_id(fake_pip_factory):
    """A rack the operator never labelled still gets its position recorded; the
    report then shows the position with an empty id column."""
    _, sites = _rack()
    sites[0].tube_id = None
    pip = fake_pip_factory(["out"])
    cell_dir = _FakeCellDir()

    collect(_collect_ctx(pip, sites[0], cell_dir))

    assert cell_dir.info_written["nucleus_tube_id"] == ""
    assert cell_dir.info_written["nucleus_tube_position"] == "A01"


def test_collect_with_mark_used_false_marks_and_records_nothing(fake_pip_factory):
    _, sites = _rack()
    pip = fake_pip_factory(["out"])
    cell_dir = _FakeCellDir()

    assert collect(_collect_ctx(pip, sites[0], cell_dir), mark_used=False) == "out"

    assert sites[0].used_up is False
    assert cell_dir.info_written == {}


def test_collect_marks_nothing_when_the_drive_does_not_reach_out(fake_pip_factory):
    """'out' is collect's only declared terminal, so any other abnormal state
    raises out of _drive_fsm before the marking can run -- which is the property
    being pinned here, not a branch in collect."""
    _, sites = _rack()
    pip = fake_pip_factory(["broken"])
    cell_dir = _FakeCellDir()

    with pytest.raises(BrokenPipette):
        collect(_collect_ctx(pip, sites[0], cell_dir))

    assert sites[0].used_up is False
    assert cell_dir.info_written == {}


def test_collect_survives_a_cell_directory_it_cannot_write(fake_pip_factory):
    """The nucleus is already in the tube by the time this runs; an unwritable
    index must not turn a successful deposit into a failed run. Same posture as
    storage.mark_important."""
    _, sites = _rack()

    class _Unwritable:
        def setInfo(self, info):
            raise OSError("read-only")

    pip = fake_pip_factory(["out"])
    ctx = _collect_ctx(pip, sites[0], _Unwritable())

    assert collect(ctx) == "out"
    # The flag still lands: the tube is consumed whether or not it got recorded.
    assert sites[0].used_up is True


def test_collect_resolves_the_site_before_driving(fake_pip_factory):
    """NucleusCollectState resolves the site again when it runs; resolving after
    the drive would read the state's own effects back."""
    _, sites = _rack()
    pip = fake_pip_factory(["out"])
    ctx = _collect_ctx(pip, sites[0])
    order = []
    original = ctx.pipette.pipetteDevice.getSiteFor

    def tracked(role):
        order.append("resolve")
        return original(role)

    ctx.pipette.pipetteDevice.getSiteFor = tracked
    ctx.on_log_action = lambda entry: order.append("drive")

    collect(ctx)

    assert order == ["resolve", "drive"]


def test_collect_with_no_assigned_site_still_drives(fake_pip_factory):
    """A rig with no array assigned falls back to the FSM's own named 'collect'
    position; there is simply nothing to mark."""
    pip = fake_pip_factory(["out"])
    cell_dir = _FakeCellDir()

    assert collect(_collect_ctx(pip, None, cell_dir)) == "out"
    assert cell_dir.info_written == {}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_actions_fsm.py -k "collect or home_with_nucleus" -q
```
Expected: collection error — `ImportError: cannot import name 'collect' from 'acq4.experiment.actions.fsm'`.

- [ ] **Step 3: Add the two FSM actions**

Append to `acq4/experiment/actions/fsm.py` (and add `from ..tube_ids import tube_position` to its
imports, next to `from ..exceptions import ...`):

```python
def home_with_nucleus(ctx, **entry_config) -> str:
    """Carry an outside-out nucleus back to the home position under negative
    pressure, and return once the pipette settles at ``out``.

    Records nothing, for the reason `clean` does not: there is nothing an
    operator reads off the trip home.
    """
    return _drive_fsm(
        ctx,
        "Home With Nucleus",
        "home with nucleus",
        {"out"},
        entry_config,
        record=False,
    )


def collect(ctx, mark_used: bool = True, **entry_config) -> str:
    """Deposit the nucleus into this pipette's nucleus site and return once the
    pipette settles at ``out``.

    With `mark_used` (this action's own option, consumed here and never
    forwarded to pip.setState), the deposited-into site is marked used up and
    the cell's data directory records which tube it went into. Unset, the drive
    runs and nothing else happens.

    ``out`` is this action's only declared terminal, so a drive that ends any
    other way raises out of _drive_fsm and never reaches the marking: a tube
    that did not receive a nucleus is never consumed.

    The site is resolved here as well as inside NucleusCollectState, which
    resolves it again when it runs. The two agree because getFirstAvailableSite
    is deterministic and nothing mutates used_up between the calls; a second
    pipette depositing into the same rack concurrently would break that.
    """
    site = ctx.pipette.pipetteDevice.getSiteFor("nucleus") if mark_used else None
    reached = _drive_fsm(ctx, "Collect Nucleus", "collect", {"out"}, entry_config)
    if site is not None:
        site.used_up = True
        _recordNucleusTube(ctx, site)
    return reached


def _recordNucleusTube(ctx, site) -> None:
    """Record on the cell's data directory which tube its nucleus went into.

    Never raises, for the reason storage.mark_important does not: the nucleus is
    already in the tube by the time this runs, and an unset storage directory or
    an unwritable index must not turn a successful deposit into a failed run.
    """
    try:
        ctx.manager.getCurrentDir().setInfo(
            {
                "nucleus_tube_id": site.tube_id or "",
                "nucleus_tube_position": tube_position(site),
            }
        )
    except Exception as exc:
        ctx.log(f"could not record the nucleus tube: {exc}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_actions_fsm.py -q
```
Expected: the new tests pass; the two pre-existing live-plot failures remain and nothing else fails.

- [ ] **Step 5: Write the failing test for `snap`**

Append to `acq4/experiment/tests/test_actions_device.py` (adding `snap` to the imports from
`acq4.experiment.actions.device`):

```python
# -- snap -------------------------------------------------------------------


def test_snap_saves_one_image_into_the_current_directory(ctx, pip, monkeypatch):
    names = _entry_names(ctx)
    calls = []

    def fake_run_image_sequence(imager, z_stack=None, storage_dir=None, name=None):
        calls.append(dict(imager=imager, z_stack=z_stack, storage_dir=storage_dir, name=name))
        return _Waitable()

    monkeypatch.setattr(device_mod, "run_image_sequence", fake_run_image_sequence)

    snap(ctx, name="nucleus")

    assert len(calls) == 1
    call = calls[0]
    assert call["imager"] is pip.imager
    # No z_stack: one frame, saved as a single image.tif.
    assert call["z_stack"] is None
    assert call["storage_dir"] is ctx.manager.current_dir
    assert call["name"] == "nucleus"
    assert names == ["Snapshot"]


def test_snap_moves_no_focus(ctx, pip, monkeypatch):
    """reseal ends with goAboveTarget then focusTip, so the tip is already above
    the sample and in focus; a focus move here would pull off it. This is why
    cellfie is not reusable -- it focuses on the target."""
    monkeypatch.setattr(device_mod, "run_image_sequence", lambda *a, **k: _Waitable())

    snap(ctx)

    assert pip.focus_calls == []
    assert pip.pipetteDevice.move_calls == []


def test_snap_defaults_to_a_plain_image_name(ctx, pip, monkeypatch):
    calls = []
    monkeypatch.setattr(
        device_mod,
        "run_image_sequence",
        lambda imager, z_stack=None, storage_dir=None, name=None: (
            calls.append(name) or _Waitable()
        ),
    )

    snap(ctx)

    assert calls == ["image"]
```

- [ ] **Step 6: Run it to verify it fails**

Run:
```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_actions_device.py -k snap -q
```
Expected: `ImportError: cannot import name 'snap'`.

- [ ] **Step 7: Add `snap`**

In `acq4/experiment/actions/device.py`, directly below `cellfie`:

```python
def snap(ctx, name: str = "image") -> None:
    """Save a single image from the pipette's imager into the current storage
    directory.

    Moves no focus: this images whatever the previous action left under the
    objective. `cellfie` is not reusable for this -- it focuses on the target,
    and the subject here is the tip held above the sample.
    """
    with ctx.log_action("Snapshot") as action_entry:
        imager = ctx.pipette.imagingDevice()
        action_entry.set_status(f"saving {name!r}")
        run_image_sequence(
            imager,
            z_stack=None,
            storage_dir=ctx.manager.getCurrentDir(),
            name=name,
        ).wait()
```

- [ ] **Step 8: Export the three actions**

In `acq4/experiment/actions/__init__.py`:

```python
from .fsm import patch, reseal, clean, collect, home_with_nucleus  # noqa: F401
```

and add `snap` to the `from .device import (...)` list.

- [ ] **Step 9: Run the full action suites**

Run:
```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests -q
```
Expected: `2 failed` (the pre-existing live-plot pair), everything else passing.

- [ ] **Step 10: Commit**

```bash
git add acq4/experiment/actions/fsm.py acq4/experiment/actions/device.py acq4/experiment/actions/__init__.py acq4/experiment/tests/test_actions_fsm.py acq4/experiment/tests/test_actions_device.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "feat: collect, home_with_nucleus, and snap actions"
```

---

### Task 5: The site actions and the report

`actions/sites.py`: the exhaustion gate, the rack swap, and the cell-to-tube report derived from
the `.index` entries Task 4 writes.

**Files:**
- Create: `acq4/experiment/actions/sites.py`
- Create: `acq4/experiment/tests/test_actions_sites.py`
- Modify: `acq4/experiment/actions/__init__.py`

**Interfaces:**
- Consumes: `Pipette.getSiteDeviceFor` (Task 1); `tube_ids.generate_tube_ids`, `read_tube_count`, `write_tube_count`, `well_label` (Task 2); `TubeRackPrompt.prompt_tube_rack` (Task 3); the `.index` keys `collect` writes (Task 4); `InteractionSiteArray.clearUsedUp/rows/cols` (Tasks 1–2).
- Produces:
  - `nucleus_sites_exhausted(ctx) -> bool`
  - `swap_tubes(ctx, id_format, title="Swap nucleus tubes", message=...) -> bool`
  - `tube_report(ctx) -> str`
  - `build_tube_report(array, dirHandle) -> str`

- [ ] **Step 1: Write the failing tests**

Create `acq4/experiment/tests/test_actions_sites.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_actions_sites.py -q
```
Expected: collection error — `ModuleNotFoundError: No module named 'acq4.experiment.actions.sites'`.

- [ ] **Step 3: Write `sites.py`**

Create `acq4/experiment/actions/sites.py`:

```python
"""Site actions: notice an exhausted nucleus rack, have the operator label and
swap a fresh one, and report which cell's nucleus went into which tube."""
from __future__ import annotations

from acq4.util.TubeRackPrompt import prompt_tube_rack

from ..exceptions import OrchestrationError
from ..tube_ids import generate_tube_ids, read_tube_count, well_label, write_tube_count

_SWAP_MESSAGE = (
    "Every nucleus tube is used. Load a fresh rack, check the ids below, and "
    "confirm."
)


def nucleus_sites_exhausted(ctx) -> bool:
    """Whether this pipette has no nucleus site left to deposit into.

    Scoped to the nucleus role alone; no other role is checked. A pipette with
    nothing assigned reports exhausted, which is the same answer for a protocol
    gating on it: there is nowhere to put a nucleus either way.
    """
    return ctx.pipette.pipetteDevice.getSiteFor("nucleus") is None


def swap_tubes(
    ctx, id_format, title: str = "Swap nucleus tubes", message: str = _SWAP_MESSAGE
) -> bool:
    """Ask the operator to load and label a fresh rack; return whether they did.

    On confirm every site is cleared and relabelled, and the day's tube counter
    advances past the whole rack. On cancel nothing changes. What a protocol
    does with a False is the protocol's decision -- example_patch_seq aborts the
    run, because continuing would patch a cell with nowhere to put its nucleus.

    `id_format` is an operator's template string (see tube_ids.format_tube_id)
    or, for a scheme a template cannot express, a callable taking the namespace
    as keywords.
    """
    with ctx.log_action("Swap Nucleus Tubes") as action_entry:
        array = _nucleus_array(ctx)
        # Before the clear, which drops the tube ids the report joins on -- and
        # before the dialog, which is where the operator reads it with the old
        # rack still in hand.
        report = build_tube_report(array, _current_dir(ctx))
        rows, cols = array.rows, array.cols

        def make_ids(start, column_major):
            return generate_tube_ids(
                id_format, rows, cols, start, column_major=column_major
            )

        action_entry.set_status("waiting for the operator to swap the rack")
        answer = prompt_tube_rack(
            title,
            message,
            rows,
            cols,
            make_ids,
            read_tube_count(array),
            extra_text=report,
        )
        lines = report.split("\n")
        if answer is None:
            action_entry.set_status("operator cancelled")
            action_entry.set_details("text", {"lines": lines + ["", "operator cancelled"]})
            return False
        ids, confirmed_start_n = answer
        array.clearUsedUp()
        for index, site in enumerate(array.sites):
            site.tube_id = ids.get(index)
        write_tube_count(array, confirmed_start_n + len(array.sites))
        action_entry.set_status(f"loaded {len(array.sites)} fresh tubes")
        action_entry.set_details("text", {"lines": lines})
        return True


def tube_report(ctx) -> str:
    """The cell-to-tube table for this pipette's nucleus rack, retained for Area 5."""
    with ctx.log_action("Tube Report") as action_entry:
        report = build_tube_report(_nucleus_array(ctx), _current_dir(ctx))
        action_entry.set_details("text", {"lines": report.split("\n")})
        return report


def build_tube_report(array, dirHandle) -> str:
    """One row per tube: its index, its well, the cell whose nucleus is in it,
    and its id.

    Two sources, joined on the id string: the array supplies the rack as it
    stands now, including the tubes nothing went into, and a walk of the Day
    directory supplies which cell named which id. The join key is the id rather
    than the position because positions are reused by every rack.

    Takes a device and a directory handle rather than a context, so it has
    nothing to do with a run in progress.
    """
    cells = _cells_by_tube_id(_day_dir(dirHandle))
    headers = ("tube", "position", "cell", "tube id")
    rows = []
    for index, site in enumerate(array.sites):
        tube_id = site.tube_id or ""
        rows.append(
            (
                str(index),
                well_label(index, array.cols),
                cells.get(tube_id, "--") if tube_id else "--",
                tube_id,
            )
        )
    widths = [max(len(row[i]) for row in (headers, *rows)) for i in range(len(headers))]
    return "\n".join(
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip()
        for row in (headers, *rows)
    )


def _nucleus_array(ctx):
    """This pipette's nucleus rack, or an error naming what is missing."""
    device = ctx.pipette.pipetteDevice.getSiteDeviceFor("nucleus")
    if device is None or not hasattr(device, "getFirstAvailableSite"):
        raise OrchestrationError(
            "no InteractionSiteArray is assigned to this pipette's 'nucleus' role"
        )
    return device


def _current_dir(ctx):
    manager = getattr(ctx, "manager", None)
    return None if manager is None else manager.getCurrentDir()


def _day_dir(dirHandle):
    """The Day directory at or above `dirHandle`, or None.

    A rack outlives a slice, so the cell lookup has to start here rather than at
    the slice. Bounded the same way create_data_dir's walk is, since a directory
    tree's root is its own parent.
    """
    candidate = dirHandle
    for _ in range(5):
        if candidate is None or not candidate.isManaged():
            return None
        if candidate.info().get("dirType") == "Day":
            return candidate
        candidate = candidate.parent()
    return None


def _cells_by_tube_id(dayDir) -> dict:
    """{tube id: "Slice_000/Cell_003"} from the .index entries collect wrote."""
    if dayDir is None:
        return {}
    cells = {}
    for slice_name in dayDir.ls():
        if not dayDir.isDir(slice_name):
            continue
        slice_dir = dayDir[slice_name]
        for cell_name in slice_dir.ls():
            if not slice_dir.isDir(cell_name):
                continue
            tube_id = slice_dir[cell_name].info().get("nucleus_tube_id")
            if tube_id:
                cells[tube_id] = f"{slice_name}/{cell_name}"
    return cells
```

- [ ] **Step 4: Export the actions**

In `acq4/experiment/actions/__init__.py`, below the `.storage` import:

```python
from .sites import nucleus_sites_exhausted, swap_tubes, tube_report  # noqa: F401
```

- [ ] **Step 5: Run the tests to verify they pass**

Run:
```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_actions_sites.py -q
```
Expected: all pass.

- [ ] **Step 6: Run the whole experiment suite**

Run:
```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests acq4/devices/tests acq4/util/tests -q
```
Expected: `2 failed` (the pre-existing live-plot pair), everything else passing.

- [ ] **Step 7: Commit**

```bash
git add acq4/experiment/actions/sites.py acq4/experiment/actions/__init__.py acq4/experiment/tests/test_actions_sites.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "feat: nucleus rack gate, swap, and cell-to-tube report"
```

---

### Task 6: The `example_patch_seq` protocol

The bundled example that puts the pieces together, plus the end-to-end test that drives a
multi-cell run across a rack swap.

**Files:**
- Create: `acq4/modules/Autopatch/example_protocols/example_patch_seq.py`
- Modify: `acq4/modules/Autopatch/tests/test_example_protocols.py`

**Interfaces:**
- Consumes: every action from Tasks 4 and 5, plus the existing `clean`, `load_preset`, `verify_cell`, `go_search`, `sonicate`, `find_tip`, `go_above_target`, `cellfie`, `go_approach`, `patch`, `reseal`, `mark_important`, `run_task`, `go_park`, `prompt`.
- Produces: a third bundled protocol named `example_patch_seq`.

- [ ] **Step 1: Write the failing tests**

In `acq4/modules/Autopatch/tests/test_example_protocols.py`, first widen the four places that
name the bundled files. Replace each listed value with the three-item form:

```python
@pytest.mark.parametrize(
    "filename", ["example_prompt.py", "example_patch.py", "example_patch_seq.py"]
)
def test_bundled_example_loads_through_protocol_file(filename):
```

```python
@pytest.mark.parametrize(
    "filename", ["example_prompt.py", "example_patch.py", "example_patch_seq.py"]
)
def test_bundled_example_declares_a_tip_on_every_param(filename):
```

In `test_example_protocols_dir_points_at_the_bundled_package_files`:

```python
    for name in ("example_prompt.py", "example_patch.py", "example_patch_seq.py"):
```

and in each of `test_examples_are_never_copied_into_the_operators_protocol_dir`,
`test_protocol_directory_over_the_examples_dir_lists_exactly_the_two_examples`,
`test_an_operators_own_file_shadows_the_bundled_example_of_the_same_name` and
`test_autopatch_window_init_lists_the_examples_without_copying_them`, the expected set becomes:

```python
    {"example_prompt", "example_patch", "example_patch_seq"}
```

(In `test_protocol_directory_over_the_examples_dir_lists_exactly_the_two_examples`, also add
`assert directory.protocols["example_patch_seq"].is_loaded is True`. Leave the function names
alone — renaming them is churn in a file that already carries six unrelated failures.)

Add these to the imports at the top of the file, beside the existing ones:

```python
from unittest.mock import MagicMock

import acq4.modules.Autopatch.example_protocols.example_patch_seq as example_patch_seq_mod
from acq4.devices.InteractionSiteArray import InteractionSiteArray
from acq4.devices.MockStage import MockStage
from acq4.devices.Pipette.pipette import Pipette
from acq4.experiment.actions import fsm as fsm_mod
from acq4.experiment.actions import sites as sites_mod
from acq4.experiment.actions.sites import build_tube_report
from acq4.experiment.exceptions import AbortExperiment
```

Then append the new tests:

```python
# -- example_patch_seq -------------------------------------------------------


class _SeqPipette(Qt.QObject):
    """The least PatchPipette _drive_fsm needs: it reaches the requested entry
    state and then 'out', which is the only terminal collect declares."""

    sigStateChanged = Qt.Signal(object, object, object)
    sigNewEvent = Qt.Signal(object, object)

    def __init__(self, pipetteDevice):
        super().__init__()
        self.pipetteDevice = pipetteDevice
        self.clampDevice = None
        self.cell = None
        self._current = "out"

    def name(self):
        return "Pipette1"

    def setCell(self, cell, target=True):
        self.cell = cell

    def setState(self, state, **config):
        self._changeState(state)
        self._changeState("out")

    def _changeState(self, state):
        old, self._current = self._current, state
        self.sigStateChanged.emit(self, state, old)

    def getState(self):
        return None


def _rack_pipette(rows=1, cols=4):
    """A real InteractionSiteArray behind a Pipette stub carrying the real
    site-assignment methods, wrapped in the minimal PatchPipette above."""
    import os

    storage = {}
    # Populated as devices are built; the array resolves its parentDevice during
    # construction, so getDevice has to be live before that call -- hence a dict
    # the closure reads rather than a side_effect set afterwards.
    devices = {}
    device_manager = MagicMock()
    device_manager.readConfigFile.side_effect = lambda path: storage.get(path, {})
    device_manager.writeConfigFile.side_effect = lambda data, path: storage.update(
        {path: dict(data)}
    )
    device_manager.configFileName.side_effect = lambda path: path
    device_manager.listDevices.return_value = []
    device_manager.listInterfaces.return_value = []
    device_manager.getDevice.side_effect = devices.get

    devices["TestStage"] = stage = MockStage(device_manager, {"nAxes": 3}, "TestStage")
    devices["Rack"] = array = InteractionSiteArray(
        device_manager,
        {
            "rows": rows,
            "cols": cols,
            "siteRadius": 1e-3,
            "siteHeight": 5e-3,
            "parentDevice": "TestStage",
            "role": "nucleus",
        },
        "Rack",
    )

    class _StubPipette:
        def name(self_):
            return "TestPip"

        def configPath(self_):
            return os.path.join("devices", f"{self_.name()}_config")

        def readConfigFile(self_, filename):
            return self_.dm.readConfigFile(os.path.join(self_.configPath(), filename))

        def writeConfigFile(self_, data, filename):
            self_.dm.writeConfigFile(data, os.path.join(self_.configPath(), filename))

    _StubPipette._loadSiteAssignments = Pipette._loadSiteAssignments
    _StubPipette.getSiteFor = Pipette.getSiteFor
    _StubPipette.getSiteDeviceFor = Pipette.getSiteDeviceFor
    _StubPipette.setSiteFor = Pipette.setSiteFor

    pipette_device = _StubPipette()
    pipette_device.dm = device_manager
    pipette_device.config = {}
    pipette_device._site_assignments = {}
    pipette_device._loadSiteAssignments()
    pipette_device.setSiteFor("nucleus", array)

    return _SeqPipette(pipette_device), array, stage


def _seq_actions(monkeypatch, calls):
    """Stub everything that touches hardware or the FSM, leaving the three
    nucleus actions -- the gate, the swap, and collect -- real."""
    # collect drives the FSM for real, and _drive_fsm would otherwise start a
    # MultiPatchLogWriter against the cell directory. The event log is not what
    # this test is about, and a real one would write files into the tree the
    # report is read back out of.
    monkeypatch.setattr(fsm_mod, "_openWriter", lambda ctx, full: None)
    monkeypatch.setattr(
        example_patch_seq_mod,
        "clean",
        lambda ctx, only_if_needed=True: calls.append("clean"),
    )
    for name in (
        "verify_cell",
        "go_search",
        "find_tip",
        "go_above_target",
        "cellfie",
        "go_approach",
        "go_park",
        "run_task",
        "mark_important",
        "home_with_nucleus",
    ):
        monkeypatch.setattr(
            example_patch_seq_mod, name, lambda ctx, _n=name: calls.append(_n)
        )
    monkeypatch.setattr(
        example_patch_seq_mod, "load_preset", lambda ctx, preset: calls.append("preset")
    )
    monkeypatch.setattr(
        example_patch_seq_mod,
        "sonicate",
        lambda ctx, protocol, pressure=None, settle=0.0: calls.append("sonicate"),
    )
    monkeypatch.setattr(
        example_patch_seq_mod, "snap", lambda ctx, name="image": calls.append(("snap", name))
    )
    monkeypatch.setattr(
        example_patch_seq_mod, "prompt", lambda ctx, message: calls.append("prompt")
    )
    monkeypatch.setattr(example_patch_seq_mod, "patch", lambda ctx: "whole cell")
    monkeypatch.setattr(example_patch_seq_mod, "reseal", lambda ctx: "outside out")


@pytest.fixture
def seq_day(tmp_path):
    day = dm.getDirHandle(str(tmp_path / "2026.11.02_000"), create=True)
    day.setInfo({"dirType": "Day"})
    slice_dir = day.getDir("Slice_000", create=True)
    slice_dir.setInfo({"dirType": "Slice"})
    return day, slice_dir


class _SeqManager:
    """Hands out one fresh cell directory per cell, the way the orchestrator
    makes a cell's directory current before the protocol runs."""

    def __init__(self, slice_dir):
        self.slice_dir = slice_dir
        self.current = None
        self.made = 0

    def next_cell(self):
        name = f"Cell_{self.made:03d}"
        self.made += 1
        self.current = self.slice_dir.getDir(name, create=True)
        self.current.setInfo({"dirType": "Cell"})
        return self.current

    def getCurrentDir(self):
        return self.current


def test_example_patch_seq_fills_a_rack_cell_by_cell(qapp, monkeypatch, seq_day):
    """The defect the whole feature exists for: nothing used to set used_up, so
    every nucleus went into tube 0 forever."""
    day, slice_dir = seq_day
    pip, array, stage = _rack_pipette(cols=4)
    try:
        calls = []
        _seq_actions(monkeypatch, calls)
        monkeypatch.setattr(
            sites_mod,
            "prompt_tube_rack",
            lambda title, text, rows, cols, make_ids, start_n, extra_text=None: (
                make_ids(start_n, False),
                start_n,
            ),
        )
        manager = _SeqManager(slice_dir)

        cells = []
        for _ in range(4):
            cell_dir = manager.next_cell()
            cells.append(cell_dir)
            example_patch_seq_mod.run(
                ExecutionContext(pipette=pip, manager=manager),
                tube_id_format="T{tube_count}_{well}",
            )

        assert [c.info()["nucleus_tube_position"] for c in cells] == [
            "A01",
            "A02",
            "A03",
            "A04",
        ]
        assert [c.info()["nucleus_tube_id"] for c in cells] == [
            "T0_A01",
            "T1_A02",
            "T2_A03",
            "T3_A04",
        ]
    finally:
        stage.quit()


def test_example_patch_seq_swaps_the_rack_and_keeps_going(qapp, monkeypatch, seq_day):
    day, slice_dir = seq_day
    pip, array, stage = _rack_pipette(cols=4)
    try:
        calls = []
        _seq_actions(monkeypatch, calls)
        swaps = []

        def fake_prompt(title, text, rows, cols, make_ids, start_n, extra_text=None):
            swaps.append(extra_text)
            return make_ids(start_n, False), start_n

        monkeypatch.setattr(sites_mod, "prompt_tube_rack", fake_prompt)
        manager = _SeqManager(slice_dir)

        cells = []
        for _ in range(5):
            cells.append(manager.next_cell())
            example_patch_seq_mod.run(
                ExecutionContext(pipette=pip, manager=manager),
                tube_id_format="T{tube_count}_{well}",
            )

        # One swap, at the fifth cell -- the gate sits at the top of the
        # protocol, so the operator is called over at the START of the cell that
        # has nowhere to go rather than after the deposit that exhausted the rack.
        assert len(swaps) == 1
        # The fifth cell reuses position A01 of a NEW rack, whose id continues
        # the day's numbering rather than restarting it.
        assert cells[4].info()["nucleus_tube_position"] == "A01"
        assert cells[4].info()["nucleus_tube_id"] == "T4_A01"
        # And the report the operator was shown at the swap named the old rack's
        # tubes and the cells in them.
        assert "T0_A01" in swaps[0]
        assert "Slice_000/Cell_000" in swaps[0]
    finally:
        stage.quit()


def test_example_patch_seq_aborts_when_the_operator_cancels_the_swap(
    qapp, monkeypatch, seq_day
):
    """Carrying on would patch a cell with nowhere to put its nucleus."""
    day, slice_dir = seq_day
    pip, array, stage = _rack_pipette(cols=1)
    try:
        calls = []
        _seq_actions(monkeypatch, calls)
        monkeypatch.setattr(
            sites_mod,
            "prompt_tube_rack",
            lambda *a, **k: None,
        )
        manager = _SeqManager(slice_dir)
        for site in array.sites:
            site.used_up = True

        manager.next_cell()
        with pytest.raises(AbortExperiment):
            example_patch_seq_mod.run(ExecutionContext(pipette=pip, manager=manager))

        # Nothing was patched: the gate is ahead of the clean for exactly this.
        assert calls == []
    finally:
        stage.quit()


def test_example_patch_seq_skips_the_nucleus_tail_when_reseal_falls_back(
    qapp, monkeypatch, seq_day
):
    """reseal returning 'whole cell' means it fell back and there is no nucleus
    to deposit."""
    day, slice_dir = seq_day
    pip, array, stage = _rack_pipette(cols=2)
    try:
        calls = []
        _seq_actions(monkeypatch, calls)
        monkeypatch.setattr(example_patch_seq_mod, "reseal", lambda ctx: "whole cell")
        manager = _SeqManager(slice_dir)
        cell_dir = manager.next_cell()

        example_patch_seq_mod.run(ExecutionContext(pipette=pip, manager=manager))

        assert "home_with_nucleus" not in calls
        assert "nucleus_tube_id" not in cell_dir.info()
        assert array.sites[0].used_up is False
        assert calls[-1] == "go_park"
    finally:
        stage.quit()


def test_example_patch_seq_takes_one_image_of_the_resealed_nucleus(
    qapp, monkeypatch, seq_day
):
    day, slice_dir = seq_day
    pip, array, stage = _rack_pipette(cols=2)
    try:
        calls = []
        _seq_actions(monkeypatch, calls)
        manager = _SeqManager(slice_dir)
        manager.next_cell()

        example_patch_seq_mod.run(ExecutionContext(pipette=pip, manager=manager))

        # reseal -> home with nucleus -> one image -> deposit.
        assert calls.count(("snap", "nucleus")) == 1
        assert calls.index("home_with_nucleus") < calls.index(("snap", "nucleus"))
    finally:
        stage.quit()


def test_example_patch_seq_parks_the_pipette_however_the_attempt_ends(
    qapp, monkeypatch, seq_day
):
    day, slice_dir = seq_day
    pip, array, stage = _rack_pipette(cols=2)
    try:
        calls = []
        _seq_actions(monkeypatch, calls)
        monkeypatch.setattr(example_patch_seq_mod, "patch", lambda ctx: "bath")
        manager = _SeqManager(slice_dir)
        manager.next_cell()

        example_patch_seq_mod.run(ExecutionContext(pipette=pip, manager=manager))

        assert calls.index("go_approach") < calls.index("go_park")
        assert "home_with_nucleus" not in calls
    finally:
        stage.quit()


def test_the_finished_day_reports_every_cell_against_its_tube(
    qapp, monkeypatch, seq_day
):
    day, slice_dir = seq_day
    pip, array, stage = _rack_pipette(cols=3)
    try:
        calls = []
        _seq_actions(monkeypatch, calls)
        monkeypatch.setattr(
            sites_mod,
            "prompt_tube_rack",
            lambda title, text, rows, cols, make_ids, start_n, extra_text=None: (
                make_ids(start_n, False),
                start_n,
            ),
        )
        manager = _SeqManager(slice_dir)
        for _ in range(2):
            manager.next_cell()
            example_patch_seq_mod.run(
                ExecutionContext(pipette=pip, manager=manager),
                tube_id_format="T{tube_count}_{well}",
            )

        report = build_tube_report(array, manager.getCurrentDir())

        lines = report.split("\n")
        assert lines[1].split() == ["0", "A01", "Slice_000/Cell_000", "T0_A01"]
        assert lines[2].split() == ["1", "A02", "Slice_000/Cell_001", "T1_A02"]
        assert lines[3].split() == ["2", "A03", "--", "T2_A03"]
    finally:
        stage.quit()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_example_protocols.py -q
```
Expected: collection error — `ModuleNotFoundError: No module named 'acq4.modules.Autopatch.example_protocols.example_patch_seq'`.

- [ ] **Step 3: Write the protocol**

Create `acq4/modules/Autopatch/example_protocols/example_patch_seq.py`:

```python
"""Patch-seq run: everything example_patch does, plus the nucleus extraction
tail and the nucleus-tube bookkeeping around it.

The run opens by asking whether this pipette has a nucleus tube left. If it does
not, the operator is called over to swap the rack and label the fresh tubes; a
cancelled swap aborts the run. The gate sits ahead of the clean deliberately --
an unattended run must not spend ten minutes patching a cell it has nowhere to
put. The cost is that the operator is called over at the start of a cell rather
than right after the deposit that emptied the rack. That is the intended trade.

After a whole-cell recording the pipette reseals toward an outside-out patch,
carries the nucleus up to its home position, takes a single image of it above
the sample, and deposits it into the next free tube. `reseal` returning "whole
cell" means it fell back and there is no nucleus to deposit, so the tail is
skipped and the pipette parks.

`tube_id_format` is the template the swap dialog prefills from. It runs through
time.strftime first (so %y%m%d expands) and then as an f-string over `index`,
`row`, `col`, `well` and `tube_count` -- the day's running tube number, which is
what the dialog's start-number box and fill-order toggle move. A scheme the
template cannot express can be a callable instead; protocols are Python.

The remaining params behave exactly as they do in example_patch.
"""

from acq4.experiment.actions import (
    cellfie,
    clean,
    collect,
    find_tip,
    go_above_target,
    go_approach,
    go_park,
    go_search,
    home_with_nucleus,
    load_preset,
    mark_important,
    nucleus_sites_exhausted,
    patch,
    prompt,
    reseal,
    run_task,
    snap,
    sonicate,
    swap_tubes,
    verify_cell,
)

PARAMS = [
    {
        "name": "cellfie_preset",
        "type": "str",
        "default": "",
        "tip": "Configured microscope imaging preset (e.g. \"GFP\") to load "
        "before the cellfie. Leave empty to skip loading a preset.",
    },
    {
        "name": "post_task_cellfie_preset",
        "type": "str",
        "default": "GFP",
        "tip": "Configured microscope imaging preset to load before the "
        "cellfie taken after the TaskRunner sequence. Leave empty to skip "
        "loading a preset.",
    },
    {
        "name": "patch_preset",
        "type": "str",
        "default": "",
        "tip": "Configured microscope imaging preset (e.g. \"brightfield\") "
        "to load before the patch attempt. Leave empty to skip loading a "
        "preset.",
    },
    {
        "name": "force_clean",
        "type": "bool",
        "default": False,
        "tip": "Run the cleaning cycle at the start of the run even when the "
        "pipette reports its tip is already clean. Off by default: a tip only "
        "reads dirty once it has been onto a cell since its last clean, so an "
        "untouched pipette skips the several minutes the cycle costs.",
    },
    {
        "name": "quick_clean_protocol",
        "type": "str",
        "default": "quick clean",
        "tip": "Sonicator protocol run at the search position, before the tip "
        "finding, to expel debris the tip picked up leaving the clean well. "
        "Must name an entry in the Sonicator device's `protocols` config -- an "
        "unconfigured name fails the run and reports which names exist. Leave "
        "empty to skip the sonication (the search move still runs).",
    },
    {
        "name": "tube_id_format",
        "type": "str",
        "default": "PFS4_%y%m%d_{tube_count + 701}_{well}",
        "tip": "Template the rack-swap dialog prefills tube ids from. Run "
        "through strftime (%y%m%d and friends) and then as an f-string over "
        "index, row, col, well and tube_count -- the day's running tube "
        "number. The operator can retype any id at the dialog.",
    },
]


def run(
    ctx,
    cellfie_preset="",
    post_task_cellfie_preset="GFP",
    patch_preset="",
    force_clean=False,
    quick_clean_protocol="quick clean",
    tube_id_format="PFS4_%y%m%d_{tube_count + 701}_{well}",
):
    # Before the clean, and so before anything that costs time or touches the
    # slice: a run with nowhere to put a nucleus should stop at the operator,
    # not at the end of a patch attempt.
    if nucleus_sites_exhausted(ctx) and not swap_tubes(ctx, id_format=tube_id_format):
        ctx.abort()
    clean(ctx, only_if_needed=not force_clean)
    load_preset(ctx, patch_preset)
    verify_cell(ctx)
    go_search(ctx)
    sonicate(ctx, protocol=quick_clean_protocol, pressure=50e3, settle=4.0)
    find_tip(ctx)
    go_above_target(ctx)
    find_tip(ctx)
    load_preset(ctx, cellfie_preset)
    cellfie(ctx)
    load_preset(ctx, patch_preset)
    go_approach(ctx)
    outcome = None
    try:
        outcome = patch(ctx)
        ctx.log(f"patch outcome: {outcome}")
        if outcome == "whole cell":
            mark_important(ctx)
            run_task(ctx)
            load_preset(ctx, post_task_cellfie_preset)
            cellfie(ctx)
            load_preset(ctx, patch_preset)
            if reseal(ctx) == "outside out":
                home_with_nucleus(ctx)
                # The tip is already above the sample and in focus -- reseal
                # ends with goAboveTarget then focusTip -- so this images the
                # nucleus where it is rather than focusing anywhere.
                snap(ctx, name="nucleus")
                collect(ctx)
    finally:
        go_park(ctx)
    if outcome not in ("whole cell", "bath", "fouled"):
        prompt(ctx, message=f"Patch ended in {outcome!r} — intervene if needed")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_example_protocols.py -q
```
Expected: `6 failed` — exactly the six pre-existing `example_patch` failures named in Global
Constraints, and no others. Every `example_patch_seq` test passes.

- [ ] **Step 5: Run the whole affected surface**

Run:
```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests acq4/devices/tests acq4/devices/Pipette/tests acq4/util/tests acq4/modules/Autopatch/tests -q
```
Expected: `8 failed` — the same eight as the baseline, no more. If the count is higher, the
extra failures are yours; fix them before committing.

- [ ] **Step 6: Format the new files**

Run:
```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m black --line-length 100 acq4/experiment/tube_ids.py acq4/experiment/actions/sites.py acq4/util/TubeRackPrompt.py acq4/modules/Autopatch/example_protocols/example_patch_seq.py
```
If `black` is not installed in that environment, skip this step and say so in the commit
message body rather than installing it.

- [ ] **Step 7: Commit**

```bash
git add acq4/modules/Autopatch/example_protocols/example_patch_seq.py acq4/modules/Autopatch/tests/test_example_protocols.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "feat: example_patch_seq protocol with nucleus extraction"
```

---

## Self-review against the spec

| Spec section | Where it lands |
| --- | --- |
| §1 `format_tube_id` / `read_tube_count` / `write_tube_count` | Task 2 |
| §1 namespace (`index`, `row`, `col`, `well`, `tube_count`) | Task 2, `tube_namespace` |
| §1 `ValueError` naming the problem | Task 2, `format_tube_id` |
| §1 dated counter record, 0 on a date change | Task 2, `read_tube_count` |
| §2 `InteractionSite.tube_id` + `sigTubeIdChanged` | Task 2 |
| §2 `clearUsedUp()` extracted as its own `refactor:` commit | Task 1 (used_up), extended in Task 2 (tube_id) |
| §3 grid dialog, start-n spinbox, fill-order toggle, overrides | Task 3 |
| §3 headless path | Task 3, `prompt_tube_rack` |
| §3 prefill as a pure function | Task 2, `generate_tube_ids` (see Deviations) |
| §4 `home_with_nucleus`, `collect` + `mark_used` | Task 4 |
| §4 double site resolution recorded as a comment, no machinery | Task 4, `collect` docstring |
| §4 `nucleus_sites_exhausted`, `swap_tubes`, `tube_report` | Task 5 |
| §4 `snap` | Task 4 |
| §4 exports from `actions/__init__.py` | Tasks 4 and 5 |
| §5 `build_tube_report(array, dirHandle)`, Day walk, id join | Task 5 |
| §5 `"text"` details kind | Tasks 5 |
| §6 `example_patch_seq.py`, gate at the top, extraction tail | Task 6 |
| §6 `tube_id_format` as a `PARAM`, callable escape hatch | Task 6 PARAMS; Task 2 `format_tube_id` |
| Tests: unit / integration / e2e | Tasks 2–3 / 4–5 / 6 |

One spec item is **not** implemented as written: §3's `defaults` parameter, replaced by
`make_ids` — see Deviations above.

## Follow-up, out of scope here

`example_patch.py` on `mini-rig` dropped `check_cell_present` and gained
`post_task_cellfie_preset` without its tests following, leaving six failures in
`test_example_protocols.py`. That drift predates this work and is not ours to fix inside it.
