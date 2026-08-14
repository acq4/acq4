"""Each patch state's throughline names that state, not the whole history of states.

A state's job is constructed from inside the outgoing state's finish handling, so the
task inherits the outgoing state's context. Left alone, states accumulate: by the tenth
transition every log line carries all ten state names.
"""
from __future__ import annotations

from gentletask import task_chain, throughline

from acq4.util.task import QtFriendlyTask


def test_state_job_does_not_inherit_the_outgoing_state_chain(qtbot):
    """A state job built while an outgoing state is current is named only for itself."""
    from acq4.devices.PatchPipette.statemanager import stateJobContext

    seen = []
    with throughline(name="State bath for PatchPipette1"):
        with stateJobContext():
            job = QtFriendlyTask(
                lambda: seen.append(task_chain()),
                name="State clean for PatchPipette1",
                detach=True,
                start=False,
            )
        job.start()
        job.wait(timeout=5)

    assert seen == [("State clean for PatchPipette1",)]
