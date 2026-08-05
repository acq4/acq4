# .acqtrack files in the Data Manager

**Date:** 2026-08-05
**Base branch:** `_reviewed` (41a5e0783)

## Problem

`Autopatcher._saveTrackingHistory` writes `tracking_history.acqtrack` with a raw
`pathlib` write derived from `cell_dir.name()`. The `DirHandle` is never told, so:

- the file does not appear in the Data Manager file tree until a manual refresh,
- no `.index` entry is created, so `FileHandle.fileType()` has nothing recorded, and
- no `FileType` claims the `.acqtrack` extension, so selecting the file in the Data
  tab yields "No file type could be detected".

A saved tracking history is only replayable through
`python -m acq4_automation.feature_tracking.replay_history <file>`, outside acq4.

## Goals

1. Saving an `.acqtrack` file notifies the Data Manager, so it shows up live and
   carries its type in the index.
2. Selecting an `.acqtrack` file in the Data tab offers a **Visualize** button that
   opens the tracking history in `LiveTrackerVisualizer`, in-process.

## Non-goals

- No generic `FileType.widget()` rendering hook; `FileDataView` keeps its explicit
  per-type branch, as it already does for `MultiPatchLog`.
- No changes to the `acq4-automation` repository.
- No summary/metadata panel for the file — a bare Visualize button.

## Design

### `acq4/filetypes/AcqTrackFile.py` (new)

The `FileType` and its Data-tab widget live in one module, mirroring
`MultiPatchLog.py`, which already houses `MultiPatchLogWidget` beside its `FileType`.

```python
class AcqTrackFile(FileType):
    extensions = ['.acqtrack']
    dataTypes = []              # written via explicit fileType=; nothing auto-detects a tracker

    @classmethod
    def write(cls, data, dirHandle, fileName, **args):
        fileName = cls.addExtension(fileName)
        data.save_history(os.path.join(dirHandle.name(), fileName))
        return fileName

    @classmethod
    def read(cls, fileHandle):
        return _loadHistory(fileHandle.name())   # -> ReplayTracker
```

`filetypes.listFileTypes()` imports every module in `acq4/filetypes/` at acq4
startup, and `acq4_automation` is an optional dependency, so the module must not
import it at module level. Two named module-level seams hold the lazy imports:

- `_loadHistory(path)` — imports and calls
  `acq4_automation.feature_tracking.tracking_history.load_history`.
- `_openVisualizer(tracker)` — imports `LiveTrackerVisualizer`, appends the window to
  a module-level `_openVisualizers` list, shows it, returns it.

The module-level list is load-bearing. `FileDataView.clear()` calls `w.close()` and
`w.setParent(None)` and drops its reference to the widget, so a list owned by the
widget would let the visualizer window be garbage collected — and thereby vanish —
as soon as the user selects a different file.

`AcqTrackWidget(Qt.QWidget)` holds a single `QPushButton("Visualize")` whose handler
is `_openVisualizer(self._fh.read())`. It reads nothing at construction.

Failures — `acq4_automation` absent, corrupt file, unsupported format version —
propagate to acq4's excepthook (error dialog plus log). They are not caught and
rendered inline.

### Writer notifies the Data Manager

In `acq4/modules/AutomationDebug/autopatch.py::_saveTrackingHistory`, the body inside
the existing `try:` becomes:

```python
fh = cell_dir.writeFile(tracker, "tracking_history", fileType="AcqTrackFile")
logger.info(f"Saved tracking history to {fh.name()}")
```

`DirHandle.writeFile` does what the raw write skipped: applies the extension via
`addExtension`, calls `_childChanged()` and `emitChanged('children', fileName)` so
`DirTreeWidget.dirChanged` rebuilds the tree and the file appears live, and records
`__object_type__: AcqTrackFile` in `.index` so the Data tab dispatches without
sniffing extensions.

`DirHandle.indexFile` is *not* the right call here: it emits only `'meta'`, which
updates an existing item's bold state but never rebuilds a directory's children.

The three guard clauses (no cell, no tracker, no tracking results) and the
log-and-swallow `except` are unchanged: a failed save must never abort the demo loop.
The now-unused `from pathlib import Path` import is removed.

### `FileDataView` branch

```python
if typ == 'MultiPatchLog':
    self.displayMultiPatchLog(fh)
elif typ == 'AcqTrackFile':
    self.displayAcqTrack(fh)
else:
    data = fh.read()
    ...
```

`displayAcqTrack(fh)` clears, builds `AcqTrackWidget(fh)`, adds it, and tracks it in
`self._widgets`. The branch sits ahead of the `fh.read()` line deliberately: reading
an `.acqtrack` deserializes every image and object stack it contains, so merely
selecting the file must not load it. Nothing loads until Visualize is clicked.

## Testing

Run with the `acq4-gl` environment.

`acq4/filetypes/tests/test_acqtrack_file.py` (new directory, with `__init__.py`
following `AutomationDebug/tests`). These patch the two seams, so they run without
`acq4_automation` installed and stay outside conftest's skip list:

- `acceptsFile` accepts `*.acqtrack` and `.ACQTRACK`, rejects other names;
  `addExtension` is idempotent.
- `write` calls `tracker.save_history` with `dirHandle.name()/fileName` and returns
  the filename with extension applied.
- `read` delegates to `_loadHistory` with the handle's path.
- `filetypes.suggestReadType` on a real `tmp_path/*.acqtrack` returns
  `'AcqTrackFile'`, proving `listFileTypes()` discovers the module.
- The widget exposes a button labelled `Visualize`; clicking it passes the object
  returned by `fh.read()` to `_openVisualizer`; construction performs no read.
- Integration, against a real `DirHandle`: `writeFile` puts the file on disk, records
  `fileType() == 'AcqTrackFile'`, and emits a `'children'` change naming it.
- End-to-end, against the real format: a real `CellTracker` seeded from a synthetic
  z-stack, written through a real `DirHandle` and read back through the `FileType`,
  with nothing faked. Guarded by `importorskip('acq4_automation')`, since the file
  format lives in that repository.

`acq4/modules/DataManager/tests/test_file_data_view_acqtrack.py`:

- `setCurrentFile` with `fileType() == 'AcqTrackFile'` installs an `AcqTrackWidget`,
  and `fh.read` is never called.

`acq4/modules/AutomationDebug/tests/test_save_tracking_history.py`:

- `test_saves_to_cell_dir` asserts
  `cell_dir.writeFile(tracker, "tracking_history", fileType="AcqTrackFile")`.
- The three skip cases are unchanged, and a `writeFile` that raises `OSError` must
  still only log.
