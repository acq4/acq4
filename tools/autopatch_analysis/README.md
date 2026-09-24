# Autopatch demo performance analysis

Tools for analyzing the throughput and efficiency of an extended autopatch demo
run from its saved `MultiPatch_*.log` files.

## Files

- `autopatch_log.py` — parse one log into per-attempt records; reconstruct the
  find/seal/break-in funnel from the `state_change` sequence and pull
  whole-cell quality numbers from `test_pulse` events.
- `autopatch_session_log.py` — parse ACQ4's own session log (`log.json`) for the
  time the MultiPatch logs never saw: cleaning, cell detection, and idle between
  attempts (see *Time between attempts* below).
- `autopatch_metrics.py` — aggregate attempts into funnel / throughput /
  time-budget / failure-mode / timeline DataFrames.
- `autopatch_analysis.ipynb` — set `ROOTS`, load a run, and render the graphs.
- `tests/` — unit tests for the parsing and metrics (`pytest tools/autopatch_analysis/tests`).

## Usage

Open `autopatch_analysis.ipynb`, edit the `ROOTS` list in the first code cell to
point at the directory(ies) holding the run's logs, and run all cells. Logs are
found recursively; point each root at a single contiguous demo run for
meaningful throughput rates.

## What's measured

The analysis is restricted to attempts that actually **approached** a cell.
Attempts that never got past bath/clean/out are pipette setup and cleaning
cycles, not real patch attempts, and are excluded (set `ONLY_APPROACHED=False`
to keep them). This keeps the funnel base and the active time honest: the
active time is the demo window (first to last approached attempt), not the whole
recording including pre/post-demo idle.

- **Funnel:** approached → found cell → sealed → whole-cell, with per-stage
  conversion, based on approached attempts.
- **Throughput:** attempts/hour, whole-cells/hour, overall yield, active time
  (demo window, summed per-log — patch work only, see *Time between attempts*).
- **Time budget:** per-attempt duration and total time spent in each patch state.
- **Time between attempts:** cleaning, cell detection, and idle — the run's
  wall-clock split into patching / cleaning / idle / recording, plus the cost of
  each tile survey. Read from the session log, not the MultiPatch logs.
- **Failure modes:** the terminal state each attempt gave up in.
- **Quality:** peak seal resistance, and access resistance / holding current
  during whole-cell.
- **Timeline:** a per-folder Gantt of every device's patch states over
  wall-clock (using all attempts), with the analyzed demo window shaded.

## Notes

Success is reconstructed from the state machine because the richer `patchRecord`
(with tidy `detectedCell` / `sealSuccessful` / `breakinSuccessful` flags) is
emitted as a Qt signal and is **not** written to the log. "Cell found" means the
attempt reached the `seal` state (only entered on `detectedCell=True`); "sealed"
means it reached `cell attached`; "broke in" means it reached `whole cell`.
Cell health scores from the detection model are saved with ranked-cell exports,
not the logs, so they are not covered here.

## Time between attempts

The MultiPatch recorder only runs while a cell directory is open, so a
`MultiPatch_*.log` covers the patch work and nothing else. Cleaning the tip,
surveying a tile for the next cells, and parking between attempts happen with no
recorder attached — on a 16-attempt demo run that was 53 % of the clock, which
the summed per-log "active time" does not include.

ACQ4's session log does record it. `log.json` is written for the whole run, the
patch state machine names every state it enters on the gentletask throughline
(`<device> -> state '<state>'`), and `tile_detector` brackets each survey between
its "Surveying tile" and "yielded N candidates" records. `ROOTS` may point at the
run directory holding `log.json` or at any directory inside it.

Cleaning (`clean`, `blowout`), idle (`out`, `bath`, `fouled`, `broken`), and
patching (approach through break-in) partition the run's wall-clock; the
`whole cell` states are reported separately because their length is the
experiment's task protocol, not a cost of the rig. Cell detection is reported
apart from all of them: a survey runs *concurrently* with whatever state the
pipette is in, so adding it to the partition would double-count
(`survey_time`'s `blocking_minutes` is the part that overlapped non-patching
time).
