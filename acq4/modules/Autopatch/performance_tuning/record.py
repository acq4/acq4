"""Trial records: read, write and validate trial.yaml, and instantiate the mutators a trial armed.

The `mutators` snapshot is keyed by factor name, which is also the key into MUTATORS.
"""

import json
from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml

import acq4

from .mutators import MUTATORS

TRIALS_DIR = Path(__file__).parent / "trials"
STATUSES = ("planned", "collecting", "closed", "abandoned")
FILE_NAME = "trial.yaml"
RUN_GROUP_FIELDS = ("protocol", "mutators", "data")


def _acq4_root() -> Path:
    for parent in Path(acq4.__file__).resolve().parents:
        if (parent / "pyproject.toml").exists():
            return parent
    raise FileNotFoundError("no pyproject.toml above the acq4 package")


@dataclass
class Trial:
    dir: Path
    id: str
    slug: str
    run_id: str
    title: str
    status: str
    created: str
    primary_factor: str
    hypothesis: str
    protocol: str
    mutators: dict
    interaction_signoff: str = ""
    quality_gate: dict | None = None
    data: list[str] = field(default_factory=list)
    results: dict | None = None
    verdict: str | None = None
    closed_on: str | None = None
    review_notes: list[str] = field(default_factory=list)


def load(trial_dir) -> Trial:
    trial_dir = Path(trial_dir)
    entry = yaml.safe_load((trial_dir / FILE_NAME).read_text())
    known = {f.name for f in fields(Trial)} - {"dir"}
    unknown = sorted(set(entry) - known)
    if unknown:
        raise ValueError(f"{trial_dir.name}: unknown keys {unknown}")
    for key in ("created", "closed_on"):
        if entry.get(key) is not None:
            entry[key] = str(entry[key])
    return Trial(dir=trial_dir, **entry)


def save(trial) -> None:
    entry = {f.name: getattr(trial, f.name) for f in fields(Trial) if f.name != "dir"}
    (trial.dir / FILE_NAME).write_text(yaml.safe_dump(entry, sort_keys=False, width=80))


def all_trials(trials_dir=TRIALS_DIR) -> list[Trial]:
    return [load(p.parent) for p in sorted(Path(trials_dir).glob(f"*/{FILE_NAME}"))]


def _protocol_errors(protocol) -> list[str]:
    root = _acq4_root()
    path = Path(protocol)
    if path.is_absolute():
        return [f"protocol {protocol!r} must be relative to the acq4 root"]
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root):
        return [f"protocol {protocol!r} is outside the acq4 root"]
    if not resolved.is_file():
        return [f"protocol {protocol!r} does not exist"]
    return []


def validate(trial, siblings) -> list[str]:
    errors = []
    if trial.status not in STATUSES:
        errors.append(f"status {trial.status!r} is not one of {STATUSES}")
    if trial.primary_factor not in trial.mutators:
        errors.append(f"primary_factor {trial.primary_factor!r} is not in mutators")
    errors += _protocol_errors(trial.protocol)
    if len(trial.mutators) > 1 and not trial.interaction_signoff.strip():
        errors.append(
            "interaction_signoff is required when mutators holds more than one entry"
        )
    for other in siblings:
        for name in RUN_GROUP_FIELDS:
            if getattr(other, name) != getattr(trial, name):
                errors.append(
                    f"trial {other.id} in run {trial.run_id} disagrees about {name}"
                )
    return errors


def _conditions_key(conditions) -> str:
    return json.dumps(conditions, sort_keys=True)


def stale_snapshot(trial) -> list[str]:
    problems = []
    for name, spec in trial.mutators.items():
        cls = MUTATORS.get(name)
        if cls is None:
            problems.append(f"{name}: no mutator registered under this name")
        elif cls.__name__ != spec["class"]:
            problems.append(
                f"{name}: unknown class {spec['class']!r}, registry has {cls.__name__!r}"
            )
        else:
            if cls.unit != spec["unit"]:
                problems.append(
                    f"{name}: unit was {spec['unit']!r}, is now {cls.unit!r}"
                )
            if _conditions_key(cls.conditions) != _conditions_key(spec["conditions"]):
                problems.append(
                    f"{name}: conditions were {spec['conditions']}, are now {cls.conditions}"
                )
    return problems


def instantiate(trial) -> list:
    return [MUTATORS[name]() for name in trial.mutators]
