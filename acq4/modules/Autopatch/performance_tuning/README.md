# Autopatch performance tuning

A system for running, tracking and concluding experiments that try to make
Autopatch better: patch profile parameters, orchestrator behaviour, detectors.
Each experiment leaves a paper trail: what was varied, the code it ran on,
the analysis applied, the numbers produced and a human verdict.
`factors.yaml` lists everything worth trying. `tracking.md` is generated from
it and the trial records, and shows what has been tried, what is running and
what is still open.

It is not for multipatch. The runtime is a process global that assumes one
cell in hand at a time. Multipatch will get its own system.

Open the review window from the Autopatch window's tuning button, or run
`python -m acq4.modules.Autopatch.performance_tuning`. It runs from an acq4
source checkout, not an installed wheel: protocols, trials and the catalogue
are paths in the checkout, and provenance reads its git state.

## Terms

- **tuning point**: a named place in acq4 that asks "is an experiment
  changing this?". A *value* point asks for a value and gets its default
  back when nothing answers. A *scope* point wraps a block of work.
- **mutator**: a class that answers points. It declares its `conditions`
  (control included) and the `unit` it is randomized over: `cell`, `survey`
  or `slice`.
- **factor**: one catalogue entry in `factors.yaml`, with its hypothesis and
  priority. A factor with `mutator: null` needs a mutator before it can run.
- **trial**: one factor against one dataset, stored at `trials/NNN-slug/trial.yaml`.
- **run group**: the trials armed together on one dataset, sharing a `run_id`.

## Adding a tuning point

1. Add a `Point` to `POINTS` in `acq4/util/tuning_points.py`, giving its kind,
   unit hint, the facts the call site offers, a doc line and the site. A call
   whose `facts` keys differ from the entry raises, so a typo fails in tests.
2. Call it at the site, asking where the thing is used rather than where it
   is constructed:
   `tuning_points.value("min_health", default, facts={"score": score})`, or
   `with tuning_points.scope("patching", facts={"ctx": ctx}):`. A fact that
   costs work to compute is passed as a zero-argument callable.
3. Write a call-site test beside the site's code. It installs a recording
   mutator, drives the real code path inside a unit, and asserts that the
   mutator was asked. For examples, see
   `acq4/experiment/tests/test_cell_producer.py` and
   `acq4/devices/Pipette/tests/test_tracker_tuning_point.py`. A point that is
   read once at import or construction fails this test.

`tuning_points.py` must not import from `acq4.modules` or `acq4.experiment`.

## Adding a mutator

For a catalogue factor with no mutator, the review window's **Create
mutator…** button writes a stub for steps 1 and 2 and opens it in your
editor.

1. Subclass one of the base classes in `mutators/base.py`:
   - `ValueMutator`: set `answers` and implement `value`.
   - `ScopeMutator`: set `wraps` and implement `around`, which returns a
     context manager.
   - `ProfileParamMutator`: set `params = (("seal", "autoSealTimeout"),)`.
     It pins those patch profile params for the length of `patching`.

   Set `name`, `unit` and `conditions`. Override `eligible(facts)` to test
   only some units. Put the class in the module for what it touches, for
   example `mutators/seal.py`.
2. Register it in `MUTATORS` in `mutators/__init__.py`. The registry is
   explicit, so a broken mutator fails at import.
3. Point a `factors.yaml` entry at it (`mutator: <name>`). The catalogue
   owns the hypothesis, priority and status. The class owns the conditions
   and the unit.

`arming.check` refuses combinations it can prove are wrong, such as two
answers to one value point or one profile key set twice. It warns about
combinations it cannot prove are safe, such as two scope mutators on one
point. A run group with a warning can be armed only once the run group
records whether its factors could interact.

## Run-group lifecycle

1. **New run group**: pick factors from the ranked candidates, choose a
   protocol. With two or more factors, say whether they could interact; if
   they might, notes are optional. This writes one `trial.yaml` per factor
   and marks each factor `running`.
2. **Arm**, from a review window opened by Autopatch, on a slice that has a
   directory. The protocol is pinned, the mutators are installed, and the
   trials become `collecting`. Assignment is lazy and balanced: a unit gets
   a condition the first time its mutator is asked. Each cell's index records
   its conditions and provenance under `performance_tuning`. Arming and
   disarming are refused while the orchestrator is running.
3. **Link data**: symlink the slice directories named by the ledger into
   each trial's `data/`.
4. **New analysis / Run analysis**: write an ad hoc analysis under
   `analyses/NNN-slug/`. It uses `join.attempts_with_conditions` and
   `report.write` to produce `out/summary.json`.
5. **Accept** an analysis with a one-line verdict. The trial closes, its
   headline numbers go into `results`, its script is copied to
   `accepted_analysis.py`, the factor becomes `tested`, and `tracking.md` is
   regenerated. **Reject** adds a note and changes nothing else. **Abandon**
   marks the trial abandoned and sets the factor back to `untested`.

Committed: `trial.yaml`, `accepted_analysis.py`, `factors.yaml` and
`tracking.md`. Each trial's `data/` and `analyses/` are git-ignored.

## The ledger

Assignments are appended to
`<configDir>/modules/AutopatchTuning/runs/<run_id>.jsonl`. The ledger is the
authority for balance, and it survives restarts. It does not live in the
code tree, because a worktree or checkout switch would silently reset
balance. It does not live in the data tree, because a run spans slices and
days. On first write it creates `AutopatchTuning/.gitignore` so the rig's
config repo stays clean. Every line is also mirrored to
`<slice>/performance_tuning_ledger.jsonl`, so a dataset carries its own
eligibility and asked rates off the rig.

## Building an analysis with Claude

**New analysis** writes a `BRIEF.md` that holds everything the trial knows.
It then runs the `misc.analysisAgent` command from the acq4 config in that
directory:

```
misc:
    analysisAgent: 'konsole --workdir {dir} -e claude "Read BRIEF.md and build the analysis it asks for."'
```

`{dir}` is the only substitution. It arrives already shell-quoted, so do not
wrap it in quotes. The prompt is a fixed string, and everything variable
lives in `BRIEF.md`, so no trial text or operator question ever reaches a
shell. When the key is unset, `BRIEF.md` opens in the code editor instead.
