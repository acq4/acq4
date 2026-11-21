"""Full-chain replay: every ported function over each recorded cell, all feeding one notebook.

Unlike the per-function replays, no set takes its inputs from the MIES labnotebook: SquarePulse
feeds Rheobase, Rheobase feeds AdaptiveSupra, DAScale Sub and VM feed Chirp. Each mismatch with MIES
must be one of the per-function expected differences or listed in CHAIN_EXPECTED.
"""

import re
import types

import pytest

from acq4.util.allen_stimsets.functions.base import functionFor
from acq4.util.allen_stimsets.mies_nwb import MiesRecording
from acq4.util.allen_stimsets.notebook import Keys
from acq4.util.allen_stimsets.replay import replayRecording

from . import test_functions_sp_rb_ra_cr as icTests
from . import test_functions_vc as vcTests
from . import test_functions_vm_da as vmdaTests
from .test_functions_vm_da import test_daValues as checkDaValues
from .test_functions_vm_da import test_vmValues as checkVmValues
from .test_mies_nwb import HUMAN_CELLS, MOUSE_CELLS, cellFile

VC = set(vcTests.FUNCTIONS)
VM_DA = {'PSQ_TrueRestingMembranePotential', 'PSQ_DAScale'}
IC = set(icTests.FUNCTIONS)

# Mismatches that appear only when the functions feed each other: cell -> {mismatch: reason}.
CHAIN_EXPECTED: dict[str, dict[str, str]] = {}

FLOAT32_RESISTANCE = (
    "MIES stores the DAScale Sub fit resistance as float32 and Chirp reads it back; the port "
    "passes the double (relative difference within float32 resolution, same DAScales)"
)
_CHIRP_FROM_RESISTANCE = re.compile(r"sweep \d+: (initial|resistance) (\S+) != MIES (\S+)$")


def chainReason(cell, full) -> str | None:
    """Return the reason for a mismatch that appears only in the full chain, or None."""
    if full in CHAIN_EXPECTED.get(cell, {}):
        return CHAIN_EXPECTED[cell][full]
    m = _CHIRP_FROM_RESISTANCE.search(full)
    if m and full.startswith('C2CHIRP'):
        ours, mies = float(m.group(2)), float(m.group(3))
        if abs(ours - mies) <= 2**-23 * abs(mies):
            return FLOAT32_RESISTANCE
    return None


def _only(res, names):
    """Return *res* reduced to the sets of the functions in *names*."""
    return types.SimpleNamespace(sets=[c for c in res.sets if c.miesName in names])


@pytest.fixture(scope='module', params=MOUSE_CELLS + HUMAN_CELLS)
def chain(request):
    cell = request.param
    with MiesRecording(cellFile(cell)) as rec:
        functions = {name: functionFor(name) for name in VC | VM_DA | IC}
        functions['PSQ_Ramp'] = type('Ramp', (icTests.MiesZeroRamp,), {'recording': rec})
        res = replayRecording(rec, functions, chunk=icTests.CHUNK)
        yield cell, rec, res


def _vmdaReason(cell, cmp, sc, msg) -> str:
    """Name the test_functions_vm_da expected difference that *msg* is."""
    if (cell, cmp.mset.sci) in vmdaTests.LOST_FILLIN_SETS:
        return "AdaptiveSupra: MIES drops the negative-slope fill-in found at preSet"
    if sc is not None and sc.stoppedByUser:
        return "MIES DAQ stopped by the user; its early stop is not compared"
    if msg.startswith('action continue'):
        return "MIES acquisition stopped externally (e.g. operator changed stimset)"
    if msg.startswith('DAScale'):
        return "VM all-zero stimset: MIES keeps the panel DAScale, the port requests 1"
    return "VM baseline user epochs within one sample of MIES"


def classify(cell, rec, res) -> dict[str, str | None]:
    """Return {mismatch: reason}; reason is None for an unexplained mismatch."""
    vcExpected = vcTests._expectedMismatches(res, vcTests._asyncFailedSweeps(rec, _only(res, VC)))
    icSets = _only(res, IC)
    icUserStopped = icTests.userStoppedAfterBaselineFailure(rec, icSets)
    icExpected = icTests.EXPECTED.get(cell, {})

    def icReason(full):
        if full in icExpected:
            return icExpected[full]
        if full in icUserStopped:
            return "MIES stopped on the failed baseline; recorded as a DAQ-button stop"
        for pattern, reason in icTests.EXPECTED_ANY.items():
            if re.search(pattern, full):
                return reason
        return None

    out = {}
    for c in res.sets:
        prefix = f"{c.mset.stimset} (SCI {c.mset.sci}): "
        found = [prefix + m for m in c.mismatches()]
        if c.miesName in IC:
            found += icTests.detailMismatches(rec, c, res.notebook)
        for full in found:
            m = full[len(prefix) :]
            match = re.match(r'sweep (\d+): (.*)', m)
            sc, msg = None, m
            if match:
                sc = next((s for s in c.sweeps if s.sweep == int(match.group(1))), None)
                msg = match.group(2)
            reason = None
            if m.startswith('aborted'):
                reason = None
            elif c.miesName in VC and full in vcExpected:
                reason = "async (temperature) alarm QC is skipped"
            elif c.miesName in VM_DA and vmdaTests._expected(cell, rec, c, sc, msg):
                reason = _vmdaReason(cell, c, sc, msg)
            elif c.miesName in IC:
                reason = icReason(full)
            out[full] = reason or chainReason(cell, full)
    for full in icTests.zeroCommandMismatches(rec, icSets, res.notebook):
        out[full] = icReason(full) or chainReason(cell, full)
    return out


def test_chainDecisions(chain):
    """Every mismatch with MIES in the full chain is an expected difference."""
    cell, rec, res = chain
    assert {c.miesName for c in res.sets} <= VC | VM_DA | IC
    # only non-patch-seq sets (no function, or MIES generic ones like SetControlInEvent) are skipped
    assert not [m.stimset for m, _ in res.skipped if (m.analysisFunction or '').startswith('PSQ_')]
    found = classify(cell, rec, res)
    unexplained = [m for m, reason in found.items() if reason is None]
    assert unexplained == [], res.report()
    stale = set(icTests.EXPECTED.get(cell, {})) | set(CHAIN_EXPECTED.get(cell, {}))
    assert stale <= set(found), "stale expected differences"


def test_chainValues(chain):
    """DA and VM results against the labnotebook, with RB and SP inputs from the ported functions."""
    cell, rec, res = chain
    checkDaValues((cell, rec, res.sets, res.notebook))
    checkVmValues((cell, rec, res.sets, res.notebook))


def test_chainInputsComeFromPortedSets(chain):
    """Cross-function inputs exist where their consumers read them."""
    cell, rec, res = chain
    nb = res.notebook
    for c in res.sets:
        if c.result is None:
            continue
        sv = c.setRecord.values
        if c.miesName == 'PSQ_Rheobase':
            assert sv[Keys.PULSE_DURATION] > 0
            assert all(Keys.AP_CROSSINGS in nb.sweep(sw).values for sw in c.setRecord.sweeps)
        if c.miesName == 'PSQ_DAScale' and sv[Keys.OPERATION_MODE] == 'Sub' and c.result.passed:
            assert sv[Keys.RESISTANCE_FROM_FIT] > 0  # MOhm, read by Chirp
        if c.miesName == 'PSQ_TrueRestingMembranePotential' and c.result.passed:
            assert -100 < sv[Keys.FULL_AVERAGE] < 0  # mV, read by Chirp and autobias
