"""The factor catalogue: load, save and validate factors.yaml, and rank candidates for the next run."""

from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import yaml

from . import arming
from .mutators import MUTATORS

DEFAULT_PATH = Path(__file__).with_name("factors.yaml")
PRIORITIES = ("high", "medium", "low")
STATUSES = ("untested", "running", "tested")


@dataclass
class Factor:
    name: str
    summary: str
    mutator: str | None
    hypothesis: str
    priority: str
    status: str
    trials: list[str] = field(default_factory=list)
    notes: str = ""


def load(path=DEFAULT_PATH) -> list[Factor]:
    known = {f.name for f in fields(Factor)}
    factors = []
    for entry in yaml.safe_load(Path(path).read_text())["factors"]:
        unknown = sorted(set(entry) - known)
        if unknown:
            raise ValueError(f"{entry.get('name')}: unknown keys {unknown}")
        factors.append(Factor(**entry))
    return factors


def save(factors, path=DEFAULT_PATH) -> None:
    text = yaml.safe_dump(
        {"factors": [asdict(f) for f in factors]}, sort_keys=False, width=80
    )
    Path(path).write_text(text)


def validate(factors) -> list[str]:
    errors = []
    seen = set()
    for f in factors:
        if f.name in seen:
            errors.append(f"{f.name}: duplicate factor name")
        seen.add(f.name)
        if f.priority not in PRIORITIES:
            errors.append(f"{f.name}: bad priority {f.priority!r}")
        if f.status not in STATUSES:
            errors.append(f"{f.name}: bad status {f.status!r}")
        if f.mutator is None:
            continue
        if f.mutator not in MUTATORS:
            errors.append(f"{f.name}: mutator {f.mutator!r} is not in MUTATORS")
        elif MUTATORS[f.mutator].name != f.name:
            errors.append(
                f"{f.name}: mutator {f.mutator!r} is named {MUTATORS[f.mutator].name!r}"
            )
    return errors


def check_combination(chosen) -> arming.CheckResult:
    return arming.check([MUTATORS[f.mutator]() for f in chosen])


def candidates(k: int, factors=None) -> list[Factor]:
    if factors is None:
        factors = load()
    eligible = [f for f in factors if f.status == "untested" and f.mutator]
    eligible.sort(key=lambda f: PRIORITIES.index(f.priority))
    chosen = []
    for f in eligible:
        if len(chosen) == k:
            break
        if not check_combination(chosen + [f]).errors:
            chosen.append(f)
    return chosen
