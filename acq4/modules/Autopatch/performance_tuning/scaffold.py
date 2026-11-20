"""Run-group scaffolding: trial directories, catalogue bookkeeping and mutator stubs."""

import importlib.util
import re
from datetime import date
from pathlib import Path

from . import arming, catalogue, record
from .mutators import MUTATORS
from .mutators.base import Mutator, ProfileParamMutator, ScopeMutator, ValueMutator

RUN_ID_MAX = 80
MUTATORS_DIR = Path(__file__).parent / "mutators"
STUB_BASES = ("ValueMutator", "ScopeMutator", "ProfileParamMutator")
SAMPLE_LIMITED_UNITS = ("survey", "slice")

STUB_TEMPLATE = '''"""Stub mutator for {name}: replace the placeholder conditions and implement the overrides.

Once it is finished, press Register mutator in the tuning window to add {cls} to MUTATORS.
"""

from acq4.modules.Autopatch.performance_tuning.mutators.base import {base}


class {cls}({base}):
    name = "{name}"
    unit = "cell"
    {attribute}
    conditions = ["replace me: first condition", "replace me: second condition"]
    # Optional: a condition every run includes, added to conditions if missing.
    baseline = None
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


class InvalidMutator(ValueError):
    """A mutator stub that cannot be registered yet."""


PLACEHOLDER = "replace me"
REGISTRY_CALL = re.compile(r"build_registry\(\((?P<names>[^)]*)\)\)")


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
        if cls.baseline is not None:
            snapshot[f.name]["baseline"] = cls.baseline
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


def mutator_stub(
    factor_name, base, point, mutators_dir=MUTATORS_DIR, param=None
) -> Path:
    """Write a stub mutator answering `point`; a ProfileParamMutator also takes `param` as "state.param"."""
    if base not in STUB_BASES:
        raise ValueError(f"base must be one of {STUB_BASES}, not {base!r}")
    if base == "ValueMutator":
        attribute = f"answers = {{{point!r}}}"
    elif base == "ScopeMutator":
        attribute = f"wraps = {{{point!r}}}"
    else:
        parts = (param or "").split(".")
        if len(parts) != 2 or not all(parts):
            raise ValueError(f"param must be state.param, not {param!r}")
        state, name = parts
        attribute = f"params = (({state!r}, {name!r}),)"
        if {point} != ProfileParamMutator.wraps:
            attribute += f"\n    wraps = {{{point!r}}}"
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


def awaiting_registration(
    mutators_dir=MUTATORS_DIR, catalogue_path=catalogue.DEFAULT_PATH
):
    """Factors with a stub file in `mutators_dir` but no mutator in the catalogue."""
    return [
        f.name
        for f in catalogue.load(catalogue_path)
        if f.mutator is None and (Path(mutators_dir) / f"{f.name}.py").exists()
    ]


def _load_stub_class(path, factor_name):
    spec = importlib.util.spec_from_file_location(f"_tuning_stub_{factor_name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    found = [
        v
        for v in vars(module).values()
        if isinstance(v, type)
        and issubclass(v, Mutator)
        and v.__module__ == module.__name__
        and getattr(v, "name", None) == factor_name
    ]
    if len(found) != 1:
        raise InvalidMutator(
            f"{path.name} must define exactly one mutator named {factor_name!r}"
        )
    return found[0]


def _stub_problems(cls, source) -> list[str]:
    problems = []
    if any(PLACEHOLDER in str(c) for c in cls.conditions):
        problems.append(
            f"{cls.name}: {PLACEHOLDER!r} conditions are still placeholders"
        )
    if "raise NotImplementedError" in source:
        method = "value" if issubclass(cls, ValueMutator) else "around"
        problems.append(
            f"{cls.name}: implement {method}; the stub still raises NotImplementedError"
        )
    problems += arming.check([cls()]).errors
    return problems


def _register_in_init(init_text, factor_name, cls_name) -> str:
    match = REGISTRY_CALL.search(init_text)
    if match is None:
        raise InvalidMutator("mutators/__init__.py has no build_registry((...)) call")
    names = [n.strip() for n in match["names"].split(",") if n.strip()]
    registry_call = f"build_registry(({', '.join(names + [cls_name])}))"
    text = init_text[: match.start()] + registry_call + init_text[match.end() :]
    imports = list(re.finditer(r"^from \.\w+ import \w+\n", text, re.M))
    at = imports[-1].end() if imports else 0
    return text[:at] + f"from .{factor_name} import {cls_name}\n" + text[at:]


def register_mutator(
    factor_name,
    mutators_dir=MUTATORS_DIR,
    catalogue_path=catalogue.DEFAULT_PATH,
    registry=MUTATORS,
):
    """Register a finished stub: add it to mutators/__init__.py and the live `registry`, and point the catalogue at it."""
    if factor_name in registry:
        raise InvalidMutator(f"{factor_name} is already registered")
    path = Path(mutators_dir) / f"{factor_name}.py"
    if not path.exists():
        raise InvalidMutator(f"no stub at {path}; create the mutator first")
    cls = _load_stub_class(path, factor_name)
    problems = _stub_problems(cls, path.read_text())
    if problems:
        raise InvalidMutator("; ".join(problems))
    init = Path(mutators_dir) / "__init__.py"
    init_text = _register_in_init(init.read_text(), factor_name, cls.__name__)
    factors = catalogue.load(catalogue_path)
    entry = next((f for f in factors if f.name == factor_name), None)
    if entry is None:
        raise InvalidMutator(f"no factor named {factor_name!r} in the catalogue")
    init.write_text(init_text)
    registry[factor_name] = cls
    entry.mutator = factor_name
    catalogue.save(factors, catalogue_path)
    return cls


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
