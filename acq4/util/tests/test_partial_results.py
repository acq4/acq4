import dataclasses
import math

import numpy as np
import pytest
from MetaArray import MetaArray

import acq4.util.DataManager as DataManager
from acq4.util.partial_results import SettleSpec, SettlementMixin, TaskResultArray


def _info():
    return [
        {'name': 'Channel', 'cols': [{'name': 'primary', 'units': 'V'}, {'name': 'command', 'units': 'A'}]},
        {'name': 'Time', 'units': 's', 'values': np.arange(6) * 1e-3},
        {'DAQ': {'primary': {'validSamples': 6}}, 'startTime': 12.5},
    ]


def _assertInfoEqual(a, b):
    if isinstance(a, dict):
        assert isinstance(b, dict) and a.keys() == b.keys()
        for k in a:
            _assertInfoEqual(a[k], b[k])
    elif isinstance(a, (list, tuple)):
        assert len(a) == len(b)
        for x, y in zip(a, b):
            _assertInfoEqual(x, y)
    elif isinstance(a, np.ndarray):
        assert np.array_equal(a, b)
    else:
        assert a == b


# SettleSpec


def test_settle_spec_updates():
    assert SettleSpec(0.0).updates
    assert SettleSpec(0.0335, "10x mean downsampling").updates
    assert not SettleSpec(math.inf, "fixed frame count").updates


def test_settle_spec_fields():
    spec = SettleSpec(0.01)
    assert spec.reason == ''
    assert spec == SettleSpec(0.01, '')
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.delay = 1.0


@pytest.mark.parametrize('delay', [-1.0, math.nan])
def test_settle_spec_rejects_invalid_delay(delay):
    with pytest.raises(ValueError):
        SettleSpec(delay)


# SettlementMixin


class _Result(SettlementMixin):
    def __init__(self, components=()):
        self._initSettlement(components)


def test_settlement_starts_at_zero():
    r = _Result(['primary', 'command'])
    assert r.settlement() == {'primary': 0, 'command': 0}
    assert not r.isComplete()
    assert _Result().settlement() == {}


def test_settlement_returns_copy():
    r = _Result(['primary'])
    s = r.settlement()
    s['primary'] = 99
    s['other'] = 1
    assert r.settlement() == {'primary': 0}
    r._setSettled('primary', 10)
    assert s['primary'] == 99


def test_set_settled():
    r = _Result(['primary'])
    r._setSettled('primary', 100)
    r._setSettled('primary', 100)
    r._setSettled('primary', np.int64(250))
    assert r.settlement() == {'primary': 250}
    assert type(r.settlement()['primary']) is int
    r._setSettled('frames', 3)
    assert r.settlement() == {'primary': 250, 'frames': 3}


def test_set_settled_never_decreases():
    r = _Result(['primary'])
    r._setSettled('primary', 100)
    with pytest.raises(ValueError):
        r._setSettled('primary', 99)
    with pytest.raises(ValueError):
        r._setSettled('new', -1)
    assert r.settlement() == {'primary': 100}


def test_is_complete():
    r = _Result(['primary'])
    r._setComplete()
    assert r.isComplete()
    r._initSettlement(['primary'])
    assert not r.isComplete()
    assert r.settlement() == {'primary': 0}


# TaskResultArray


def test_task_result_array_constructs_like_metaarray():
    arr = np.arange(12, dtype=float).reshape(2, 6)
    t = TaskResultArray(arr, info=_info())
    m = MetaArray(arr, info=_info())
    assert isinstance(t, MetaArray)
    assert t.implements('MetaArray')
    assert t.asarray() is arr  # wraps without copying
    assert t.shape == m.shape and t.dtype == m.dtype
    _assertInfoEqual(t.infoCopy(), m.infoCopy())
    assert np.array_equal(t['primary'].asarray(), m['primary'].asarray())
    assert np.array_equal(t.xvals('Time'), m.xvals('Time'))
    assert t.settlement() == {}
    assert not t.isComplete()

    shaped = TaskResultArray((2, 3), dtype=np.float32)
    assert shaped.shape == (2, 3) and shaped.dtype == np.float32

    t._initSettlement(['primary', 'command'])
    wrapped = MetaArray(t)
    assert type(wrapped) is MetaArray and wrapped.asarray() is arr


def test_task_result_array_in_place_fill_is_visible():
    t = TaskResultArray(np.zeros((2, 6)), info=_info())
    t.asarray()[0, :3] = [1, 2, 3]
    t[1, 2] = 7
    assert list(t['primary'].asarray()[:3]) == [1, 2, 3]
    assert t[1, 2] == 7


@pytest.mark.parametrize('index', [
    0,
    'primary',
    slice(0, 1),
    (slice(None), slice(1, 4)),
    ('Time', slice(0, 3)),
])
def test_task_result_array_slices_are_plain_metaarray(index):
    t = TaskResultArray(np.ones((2, 6)), info=_info())
    t._initSettlement(['primary'])
    if isinstance(index, tuple) and isinstance(index[0], str):
        sub = t[index[0]:index[1]]
    else:
        sub = t[index]
    assert type(sub) is MetaArray
    assert not hasattr(sub, 'settlement')


def test_task_result_array_derived_objects_are_plain_metaarray():
    t = TaskResultArray(np.ones((2, 6)), info=_info())
    assert type(t.copy()) is MetaArray
    assert type(t * 2) is MetaArray
    assert type(abs(t)) is MetaArray


def test_task_result_array_storage_round_trip(tmp_path):
    arr = np.random.default_rng(0).normal(size=(2, 6))
    t = TaskResultArray(arr.copy(), info=_info())
    t._initSettlement(['primary', 'command'])
    t._setSettled('primary', 6)
    t._setComplete()

    dh = DataManager.getDirHandle(str(tmp_path))
    fh = dh.writeFile(t, 'clamp1')
    plainFh = dh.writeFile(MetaArray(arr.copy(), info=_info()), 'plain')

    assert fh.shortName().lower() == 'clamp1.ma'
    assert fh.info()['__object_type__'] == plainFh.info()['__object_type__'] == 'MetaArray'

    readBack = fh.read()
    plainReadBack = plainFh.read()
    assert type(readBack) is MetaArray
    assert np.array_equal(readBack.asarray(), arr)
    assert readBack.dtype == arr.dtype
    _assertInfoEqual(readBack.infoCopy(), plainReadBack.infoCopy())
    _assertInfoEqual(readBack.infoCopy(), _info())
