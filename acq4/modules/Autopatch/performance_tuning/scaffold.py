"""Run-group scaffolding: trial directories, catalogue bookkeeping and mutator stubs."""

from datetime import date
from pathlib import Path

from . import catalogue, record
from .mutators import MUTATORS
from .mutators.base import ProfileParamMutator

RUN_ID_MAX = 80
MUTATORS_DIR = Path(__file__).parent / "mutators"
STUB_BASES = ("ValueMutator", "ScopeMutator", "ProfileParamMutator")
SAMPLE_LIMITED_UNITS = ("survey", "slice")

STUB_TEMPLATE = '''"""Stub mutator for {name}: replace the placeholder conditions and implement the overrides.

Add {cls} to the MUTATORS registry in mutators/__init__.py by hand once it is finished.
"""

from acq4.modules.Autopatch.performance_tuning.mutators.base import {base}


class {cls}({base}):
    name = "{name}"
    unit = "cell"
    {attribute}
    conditions = ["replace me: first condition", "replace me: second condition"]
{methods}'''

STUB_METHODS = {
    "ValueMutator": """
    def value(self, point, default, condition, facts):
        raise NotImplementedError
""",
    "ScopeMutator": """
    def around(self, point, condition, facts):
        raise NotImplementedError
""",
    "ProfileParamMutator": "",
}


class InvalidRunGroup(ValueError):
    """A run group that cannot be made as asked."""


def next_trial_id(trials_dir) -> str:
    trials_dir = Path(trials_dir)
    numbers = [
        int(p.name.split("-")[0])
        for p in trials_dir.glob("*")
        if p.is_dir() and p.name.split("-")[0].isdigit()
    ]
    return f"{max(numbers, default=0) + 1:03d}"


def _snapshot(factors) -> dict:
    snapshot = {}
    for f in factors:
        cls = MUTATORS[f.mutator]
        snapshot[f.name] = {
            "class": cls.__name__,
            "unit": cls.unit,
            "conditions": list(cls.conditions),
        }
    return snapshot


def new_run_group(
    factors,
    protocol,
    interactions_expected=None,
    interaction_notes="",
    run_id=None,
    trials_dir=record.TRIALS_DIR,
    catalogue_path=catalogue.DEFAULT_PATH,
) -> list:
    errors = catalogue.check_combination(factors).errors
    if errors:
        raise InvalidRunGroup(f"factors cannot run together: {errors}")
    if len(factors) > 1 and interactions_expected is None:
        raise InvalidRunGroup(
            "say whether these factors could interact before making a run group"
        )
    today = date.today().isoformat()
    if run_id is None:
        run_id = f"{today}-{'-'.join(f.name for f in factors)}"[:RUN_ID_MAX]
    snapshot = _snapshot(factors)
    trials_dir = Path(trials_dir)
    trials_dir.mkdir(parents=True, exist_ok=True)

    trials = []
    for f in factors:
        trial_id = next_trial_id(trials_dir)
        slug = f.name.replace("_", "-")
        trial_dir = trials_dir / f"{trial_id}-{slug}"
        (trial_dir / "analyses").mkdir(parents=True)
        (trial_dir / "data").mkdir()
        trial = record.Trial(
            dir=trial_dir,
            id=trial_id,
            slug=slug,
            run_id=run_id,
            title=f.summary,
            status="planned",
            created=today,
            primary_factor=f.name,
            hypothesis=f.hypothesis,
            protocol=protocol,
            mutators=snapshot,
            interactions_expected=interactions_expected,
            interaction_notes=interaction_notes,
            data=[],
        )
        record.save(trial)
        trials.append(trial)

    problems = []
    for trial in trials:
        siblings = [t for t in trials if t is not trial]
        problems += record.validate(trial, siblings)
    if problems:
        raise InvalidRunGroup(f"run group does not validate: {problems}")

    entries = catalogue.load(catalogue_path)
    for trial in trials:
        entry = next(e for e in entries if e.name == trial.primary_factor)
        entry.status = "running"
        entry.trials.append(trial.id)
    catalogue.save(entries, catalogue_path)
    return trials


def mutator_stub(factor_name, base, point, mutators_dir=MUTATORS_DIR) -> Path:
    if base not in STUB_BASES:
        raise ValueError(f"base must be one of {STUB_BASES}, not {base!r}")
    if base == "ValueMutator":
        attribute = f"answers = {{{point!r}}}"
    elif base == "ScopeMutator":
        attribute = f"wraps = {{{point!r}}}"
    else:
        state, param = point.split(".")
        attribute = f"params = (({state!r}, {param!r}),)"
    path = Path(mutators_dir) / f"{factor_name}.py"
    if path.exists():
        raise FileExistsError(path)
    path.write_text(
        STUB_TEMPLATE.format(
            name=factor_name,
            cls="".join(part.title() for part in factor_name.split("_")),
            base=base,
            attribute=attribute,
            methods=STUB_METHODS[base],
        )
    )
    return path


def profile_params() -> list[str]:
    """Every patch profile param, as sorted "state.param" strings."""
    from acq4.devices.PatchPipette.states import PatchPipetteState

    def subclasses(cls):
        for sub in cls.__subclasses__():
            yield sub
            yield from subclasses(sub)

    names = set()
    for cls in subclasses(PatchPipetteState):
        if cls.stateName:
            names.update(
                f"{cls.stateName}.{c['name']}" for c in cls.parameterTreeConfig()
            )
    return sorted(names)


def statistics_warning(factors) -> str | None:
    limited = [
        f"{f.name} ({MUTATORS[f.mutator].unit})"
        for f in factors
        if MUTATORS[f.mutator].unit in SAMPLE_LIMITED_UNITS
    ]
    if not limited:
        return None
    return (
        "Factors with survey or slice units have about as many samples as "
        f"surveys or slices, not cells: {', '.join(limited)}"
    )
