"""Action: the composable unit of orchestration work. Subclasses declare their
possible outcomes and params, and implement run() to do the work synchronously."""
from __future__ import annotations

from typing import Any

from acq4.util import Qt
from pyqtgraph.parametertree import Parameter

from .context import ExecutionContext


class Action(Qt.QObject):
    """A unit of work bound at run time to a cell + pipette via ExecutionContext.

    Subclasses set `outcomes` (the names run() may return) and optionally
    `paramSpec` (a pyqtgraph Parameter config list). run() executes synchronously
    inside an orchestrator worker thread and must return one of `outcomes`.
    """

    outcomes: tuple[str, ...] = ()
    paramSpec: tuple[dict, ...] = ()

    sigStateChanged = Qt.Signal(object, str)  # self, message

    def __init__(self, name: str | None = None, params: dict | None = None):
        Qt.QObject.__init__(self)
        self.name = name or type(self).__name__
        self.params = self._buildParams(params or {})
        self.results: dict[str, Any] = {}

    @classmethod
    def _buildParams(cls, values: dict) -> Parameter:
        children = [dict(spec) for spec in cls.paramSpec]
        group = Parameter.create(name="params", type="group", children=children)
        valid = {spec["name"] for spec in cls.paramSpec}
        for key, val in values.items():
            if key not in valid:
                raise KeyError(f"{cls.__name__} has no param {key!r}")
            group.child(key).setValue(val)
        return group

    def paramValue(self, name: str) -> Any:
        return self.params.child(name).value()

    def setState(self, message: str) -> None:
        self.sigStateChanged.emit(self, message)

    def run(self, ctx: ExecutionContext) -> str:
        raise NotImplementedError

    def safeAbort(self, ctx: ExecutionContext) -> None:
        """Unwind devices to a safe state when the action is stopped. Default no-op."""

    def show(self):
        """Return a live QWidget for this action, or None. Default None."""
        return None
