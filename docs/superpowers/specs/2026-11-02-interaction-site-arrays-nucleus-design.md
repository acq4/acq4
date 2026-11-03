# InteractionSiteArray support for nucleus extraction during Autopatch

Date: 2026-11-02
Branch: `claude/interaction-site-arrays-nucleus-053b36` (off `mini-rig`)

## Problem

The target rig carries an array of nucleus deposition tubes. Each tube is used
once; when they are all full, the operator swaps the whole rack. Autopatch has
no way to notice that the rack is exhausted, no way to run the nucleus
extraction tail of a patch-seq protocol, and no record of which tube a given
cell's nucleus went into.

What exists today:

- `InteractionSite.used_up` (persisted in `saved_positions`, with
  `sigUsedUpChanged`) and `InteractionSiteArray.getFirstAvailableSite()`, which
  returns the first site that is not used up.
- `InteractionSiteArray`'s device GUI: a per-site toggle grid and a
  "Mark all unused" button.
- `Pipette.getSiteFor(role)` / `setSiteFor(role, dev)`, with persisted
  per-pipette role assignments. An array satisfies a role only when
  `array.role == role`.
- PatchPipette FSM states `reseal`, `collect` (`NucleusCollectState`) and
  `home with nucleus` (`MoveNucleusToHomeState`).

What is missing:

- **Nothing ever sets `used_up`.** `NucleusCollectState` resolves
  `pip.getSiteFor('nucleus')` and deposits into it, but never marks it. On a
  real array every nucleus goes into tube 0, forever. This is a bug, not a
  missing feature.
- No protocol action drives the `collect` or `home with nucleus` states.
- No gate telling a protocol the rack is exhausted.
- No way to clear `used_up` across an array from a protocol.
- No record of which cell went into which tube, and no tube identifiers at all.

## Scope

In scope: the actions, the device-level attributes, the operator dialog, one
new example protocol, and tests. Out of scope: crash recovery of in-progress
rack state (there is an open, unsolved Autopatch recovery problem; this design
deliberately does not anticipate it), multi-role exhaustion checks, tube
capacity look-ahead, and site reservation.

## Design

### 1. `acq4/experiment/tube_ids.py`

Three module-level functions, no classes:

```python
format_tube_id(template, **namespace) -> str
read_tube_count(array) -> int
write_tube_count(array, count) -> None
```

`format_tube_id` runs `time.strftime(template)` first, then evaluates the
result as an f-string against `namespace`. Both halves have precedent in this
tree: `create_data_dir` in `acq4/experiment/actions/storage.py` runs folder-type
name templates through `strftime`, and `NucleusCollectState` evaluates its
`pressureSequence` config string with `eval(sequence, units.__dict__)`.

Composing them means no date mini-language and no format vocabulary has to be
invented. An operator's real format,
`PFS4_%y%m%d_{tube_count + 701}_{well}`, works as written.

Namespace:

- `index` (0-based), `row`, `col`, `well` (`"A01"`) — the site's *physical*
  position in the array, independent of fill order.
- `tube_count` — the day's running tube number for this tube: the confirmed
  start-n plus the tube's ordinal in the chosen fill order. This is the name
  that increments, and the one the row-major / column-major toggle changes.

It is a plain dict, so adding names later is one line. Slice name and operator
initials are deliberately absent — nothing currently supplies them.

A template that raises (bad name, syntax error) raises `ValueError` naming the
problem. The dialog catches it and shows it in the field; the operator types
ids by hand. An id must never fail a run.

**The counter.** `read_tube_count` / `write_tube_count` persist one record —
`{"date": "251103", "count": 12}` — through the array's own
`readConfigFile`/`writeConfigFile`, the mechanism `role` and `used_up` already
use. Reading compares the stored date against today and returns 0 when they
differ.

That single record satisfies all three constraints on "tube n":

- *tubes filled today*: the date comparison.
- *survives slices and restarts*: a consequence of the file being rig-level
  rather than slice-level. There is no code for this.
- *operator override regenerates subsequent ns*: the dialog's start-n spinbox,
  below.

### 2. Device layer

`InteractionSite` gains a persisted `tube_id: str | None` — property, setter,
and `sigTubeIdChanged`, mirroring `used_up` exactly and stored alongside it in
`saved_positions`.

`InteractionSiteArray` gains `clearUsedUp()`, clearing `used_up` and `tube_id`
across every site. The array GUI's `_markAllUnused` currently does this inline;
it becomes a call to the device method so the button and the action share one
implementation.

**This extraction lands as its own `refactor:` commit, before any feature
commit.** It is behaviour-preserving and sits inside code the feature touches.

No attribute records which cell consumed a site. See §5.

### 3. `acq4/util/TubeRackPrompt.py`

A sibling to `PromptUser.py`, under the same discipline: the dialog is built,
shown and destroyed entirely on the GUI thread, and only plain data crosses
back to the calling worker thread.

```python
prompt_tube_rack(title, text, rows, cols, defaults, start_n, extra_text=None)
    -> tuple[dict[int, str], int] | None
```

Returns `({site_index: id_string}, confirmed_start_n)`, or `None` if the
operator cancels.

- A grid of line edits laid out physically like the array.
- A start-n spinbox above the grid.
- A row-major / column-major toggle.

Editing the spinbox or flipping the toggle refills the grid from the format —
except fields the operator has edited, which stay as typed. Prefill order is
the only thing the toggle changes.

Headless (`Qt.QApplication.instance() is None`) returns the generated defaults
unedited, the way `actions.prompt.prompt` returns its first choice when there
is no UI. This is what makes the actions testable.

The prefill logic — given a format, a start-n, a fill order and a set of
overridden indices, produce the grid contents — is a pure function, tested
without a widget.

### 4. Actions

**`acq4/experiment/actions/fsm.py`** — two thin `_drive_fsm` wrappers:

- `home_with_nucleus(ctx, **entry_config) -> str`: entry `"home with nucleus"`,
  terminal `{"out"}`, `record=False` (like `clean` — there is nothing an
  operator reads off it).
- `collect(ctx, mark_used=True, **entry_config) -> str`: entry `"collect"`,
  terminal `{"out"}`. Resolves `pip.getSiteFor("nucleus")` *before* driving,
  drives, and on success sets `used_up` and writes two scalars to the cell
  directory's `.index`: `nucleus_tube_id` and `nucleus_tube_position`
  (the well label, `"A02"`). With `mark_used=False` it drives and does nothing
  else — no flag, no metadata. A drive that does not reach `"out"` marks
  nothing.

  `collect` resolving the site independently of `NucleusCollectState`, which
  resolves it again, is a known cost: two resolutions that must agree. They do
  agree today because `getFirstAvailableSite` is deterministic, the rig has one
  pipette, and nothing mutates `used_up` between the two calls. This is
  recorded as a comment at the call site. No defensive machinery is built for
  it — only what this rig needs.

**`acq4/experiment/actions/sites.py`** (new):

- `nucleus_sites_exhausted(ctx) -> bool`: `pip.getSiteFor("nucleus") is None`.
  The whole function. Scoped to the nucleus role only; other roles are not
  checked.
- `swap_tubes(ctx, id_format, title=...) -> bool`: builds the report, opens the
  dialog preloaded from the format and today's count, and on confirm calls
  `clearUsedUp()`, writes every `tube_id`, and sets the stored count to the
  confirmed start-n plus the number of sites in the array. Returns whether the
  operator confirmed. Retains the report as `"text"` details for Area 5.

  On cancel it changes nothing and returns False. What a protocol does with
  that is the protocol's decision; `example_patch_seq` calls `ctx.abort()`,
  because continuing would patch a cell with nowhere to put its nucleus.
- `tube_report(ctx) -> str`: the table alone, for a protocol that wants it
  logged at end of slice. Resolves the array from `ctx.pipette` and the
  directory from `ctx.manager`, then defers to `build_tube_report` (§5).

**`acq4/experiment/actions/device.py`**:

- `snap(ctx, name="image") -> None`: `run_image_sequence(imager, z_stack=None,
  storage_dir=..., name=name)`, which saves a single `image.tif`. Moves no
  focus — `reseal` ends with `goAboveTarget` then `focusTip`, so the tip is
  already above the sample and in focus when this runs. `cellfie` is not
  reusable here: it focuses on the *target*, not the tip.

All new actions are exported from `acq4/experiment/actions/__init__.py`.

### 5. The report

The cell-to-tube mapping is held nowhere in memory. `collect` writes
`nucleus_tube_id` and `nucleus_tube_position` into each cell directory's
`.index`; the report reads them back.

```python
build_tube_report(array, dirHandle) -> str
```

Takes a device and a directory handle, returns a string. It touches no
execution context.

Two sources, joined on the tube id string: the array supplies the rack as it
stands now (every site's position and `tube_id`, including the empty ones),
and the directory walk supplies which cell went into each id. The join key is
the id rather than the position, because positions are reused by every rack and
joining on them would attribute a previous rack's cell to a fresh tube.

A site with no `tube_id` — a rack the operator never labelled — shows its
position with both the id and cell columns empty. There is nothing to join on,
and inventing a key would be the position join this design just rejected.

It walks the **Day** directory, not the Slice directory: a rack can outlive a
slice, and a slice-scoped report would silently drop the cells of an earlier
slice that used the same tubes. The cell column therefore reads
`Slice_000/Cell_003`. Finding the Day directory uses the same idiom
`create_data_dir` already uses — climb parents comparing `info()["dirType"]`.

Rendered through the existing `"text"` details kind, whose builder is a
read-only `QPlainTextEdit`, so a monospace-aligned table needs no new renderer:

```
tube  position  cell                tube id
0     A01       Slice_000/Cell_000  PFS4_251103_701_A01
1     A02       Slice_000/Cell_003  PFS4_251103_702_A02
2     A03       --                  PFS4_251103_703_A03
```

The same string is passed as the dialog's `extra_text`, so the operator reads
the table while standing at the rig with the rack in hand.

If the storage directory moved mid-session the walk finds nothing and the
report comes back empty rather than wrong — degraded, not broken, and visible
to the operator at the dialog.

### 6. `example_patch_seq.py`

A new bundled example alongside `example_patch.py`, listed in place by
`ProtocolDirectory`'s `extra_paths`. It keeps `example_patch.py`'s structure —
same clean, same tip-finding, same `try/finally: go_park(ctx)` — and adds the
gate at the top and the extraction tail:

```python
if nucleus_sites_exhausted(ctx):
    swap_tubes(ctx, id_format=tube_id_format)
clean(ctx, only_if_needed=not force_clean)
...                                   # identical through patch()
outcome = patch(ctx)
if outcome == "whole cell":
    mark_important(ctx)
    run_task(ctx)
    load_preset(ctx, post_task_cellfie_preset)
    cellfie(ctx)
    load_preset(ctx, patch_preset)
    if reseal(ctx) == "outside out":
        home_with_nucleus(ctx)
        snap(ctx, name="nucleus")
        collect(ctx)
```

The gate sits ahead of the clean deliberately: an unattended run must not spend
ten minutes patching a cell it has nowhere to put. The consequence is that the
operator is called over at the *start* of a cell rather than immediately after
the deposit that exhausted the rack. That is the intended trade.

`reseal` returning `"whole cell"` means it fell back and there is no nucleus to
deposit, so the tail is skipped and the pipette parks.

`tube_id_format` is a protocol `PARAM` (a string), so an operator sets it from
the protocol panel. A protocol needing something the template cannot express
passes a callable as `id_format` instead — protocols are Python, so a callable
crosses that boundary fine.

## Containment

Everything date-, counter- and template-shaped lives in `tube_ids.py` and stops
at the dialog's OK button:

```
tube_ids.py  -->  swap dialog  -->  site.tube_id = "PFS4_251103_713_A01"
  (template,        (fills grid,              |
   counter,          operator edits)          v
   date rollover)                    collect reads a string
                                     .index gets a string
                                     report prints a string
```

Nothing downstream sees the template, the counter, or the date. `collect` does
not compute an id; it reads one. None of this is on the per-cell path — it runs
once per rack, in a dialog, with the operator present.

The blast radius of any of it being wrong is one string in one `.index` field.
It cannot fail a patch, move hardware, or halt a run.

## Tests

Written first, per TDD.

**Unit**

- `format_tube_id`: strftime codes expand; arithmetic in the f-string
  evaluates; every namespace name is reachable; a bad name or syntax error
  raises `ValueError` naming the problem.
- `read_tube_count` / `write_tube_count`: round-trip; a record from another
  date reads as 0; a missing record reads as 0.
- `InteractionSite.tube_id`: round-trips through `saved_positions`; emits
  `sigTubeIdChanged`; setting the same value twice emits once (matching
  `used_up`).
- `InteractionSiteArray.clearUsedUp()`: clears `used_up` and `tube_id` on every
  site, including sites that were already clear.
- The dialog's prefill as a pure function: fill order, start-n, and overridden
  indices surviving a toggle.
- `build_tube_report`: finds the Day directory from a Cell directory; includes
  cells from more than one slice; renders an empty table when no cell names a
  tube.

**Integration** — the actions against the existing fakes
(`acq4/experiment/tests/conftest.py`, `acq4/modules/Autopatch/tests/fakes.py`):

- `collect` marks the site the state used and writes both `.index` keys.
- `collect(mark_used=False)` writes neither and marks nothing.
- A drive that does not reach `"out"` marks nothing.
- `home_with_nucleus` drives the right entry state and opens one Area 5 row.
- `nucleus_sites_exhausted` flips exactly when the last site is consumed, and
  is False again after `clearUsedUp()`.
- `swap_tubes` headless: clears the array, writes generated ids to every site,
  advances the counter, and returns True.
- `swap_tubes` on cancel: changes nothing and returns False.
- `snap` saves one file into the cell directory and moves no focus.

**End-to-end**

- `example_patch_seq` driven through the orchestrator with the Autopatch fakes:
  a multi-cell run that exhausts a 4-site array, swaps the rack, and keeps
  going. Asserts each cell directory's `.index` names the tube that cell
  actually got, and that the second rack's ids continue the day's numbering.
- The existing `test_example_protocols.py` checks extend to the new protocol:
  it imports, its `PARAMS` are well-formed, and its `run()` signature agrees
  with them.

## Decisions and their reasons

| Decision | Reason |
| --- | --- |
| `collect` sets `used_up` behind a param flag | The tube is consumed by the deposit; the flag lets a protocol opt out without a second action. |
| No `mark_site_used` action | Nothing would call it; `collect` covers the only real case, and the array GUI already has per-site toggles for operator correction. |
| No site reservation | One pipette, sequential cells. Nothing to race. |
| No new persistence beyond `tube_id` | Rack state surviving a crash belongs to the unsolved Autopatch recovery problem, not here. |
| Gate checks the nucleus role only | The rig has one consumable array. A multi-role check is speculative. |
| Gate at the top of the protocol | An unattended run must not patch a cell it cannot deposit. |
| Mapping derived from `.index`, not held in memory | One source of truth, no new state on the device, the orchestrator, or the context. |
| Report walks the Day directory | A rack can outlive a slice. |
| `"text"` details kind, not a new table renderer | A monospace `QPlainTextEdit` renders an aligned table; a new renderer would need its own tests for no gain. |

## Commit sequence

1. `refactor:` extract `InteractionSiteArray.clearUsedUp()` from the GUI's
   `_markAllUnused`.
2. `feat:` `tube_ids.py` and `InteractionSite.tube_id`.
3. `feat:` `TubeRackPrompt.py`.
4. `feat:` `collect`, `home_with_nucleus`, `snap`.
5. `feat:` `sites.py` actions and `build_tube_report`.
6. `feat:` `example_patch_seq.py`.
