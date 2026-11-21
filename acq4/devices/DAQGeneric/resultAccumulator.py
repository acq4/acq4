"""A DAQ device task's result MetaArray, filled with settled values while the task runs."""

import functools
import threading
from typing import Callable, NamedTuple, Optional

import numpy as np

from MetaArray import axis
from acq4.util.partial_results import TaskResultArray

_FINISH_LOCK_TIMEOUT = 2.0  # s; getResult() raises if a chunk listener holds the result longer


class ResultColumn(NamedTuple):
    """One channel (row) of a device task's result."""

    name: str
    units: Optional[str]
    daqTask: object  # NiDAQ.Task
    channel: str  # DAQ channel name, as passed to daqTask.addChannel() and getData()
    mapping: Callable  # fn(daqData) -> data in device units; pointwise, and must not block


class ResultAccumulator:
    """Owns a DAQ device task's TaskResultArray: settled values while it runs, final values at getResult().

    *columns* is fn(final) -> [ResultColumn, ...] in result row order; it may raise if the task
    cannot produce a result. With final=False it may run on a DAQ reader thread, so it must not
    block or touch hardware. *buildInfo* is fn(results) -> MetaArray info list, where *results* is
    {name: daqTask.getData() result with 'data' mapped to device units and 'units' added}, in
    column order, each 'info' carrying 'validSamples'.

    The result is allocated at the first chunk, partialResult() or getResult(), once every column's
    channel has been passed to track(). getResult() completes that same object; settled values are
    never rewritten.
    """

    def __init__(self, columns, buildInfo, logger):
        self._columns = columns
        self._buildInfo = buildInfo
        self._logger = logger
        self._accs = {}  # (id(daqTask), channel) -> DaqChannelAccumulator
        self._listening = {}  # id(daqTask) -> daqTask
        self._lock = threading.Lock()  # partial state; never held while calling into a DAQ task
        self._finishLock = threading.Lock()  # serializes getResult()
        self.reset()

    def reset(self):
        """Discard the result for a new run. Tracked channels are kept."""
        with self._lock:
            self._result = None
            self._unavailable = False
            self._rows = []  # (row index, column, accumulator)
            self._settled = []  # settled count per row
            self._final = None
            self._complete = False

    def track(self, daqTask, channel):
        """Get *channel*'s accumulator and listen for *daqTask*'s chunks.

        Call from createChannels(), right after daqTask.addChannel(channel, ...).
        """
        acc = daqTask.channelAccumulator(channel)
        self._accs[(id(daqTask), channel)] = acc
        if id(daqTask) not in self._listening:
            self._listening[id(daqTask)] = daqTask
            daqTask.addChunkListener(functools.partial(self._onChunk, daqTask))
        return acc

    def settleSpecs(self):
        """Return {column name: SettleSpec} for tracked input channels."""
        try:
            columns = self._columns(False)
        except Exception:
            return {}
        specs = {}
        for col in columns:
            acc = self._accs.get((id(col.daqTask), col.channel))
            if acc is not None and acc.chanType in ('ai', 'di'):
                specs[col.name] = acc.settleSpec
        return specs

    def partialResult(self):
        """Return the object getResult() will return, or None if there is none yet. Called on DAQ reader threads."""
        if self._complete:
            return self._final
        with self._lock:
            return self._ensureResult()

    def _onChunk(self, daqTask):
        """Chunk listener (reader thread): copy newly settled values of *daqTask*'s input channels."""
        with self._lock:
            if self._complete or self._ensureResult() is None:
                return
            for row, col, acc in self._rows:
                if col.daqTask is daqTask and acc.chanType in ('ai', 'di'):
                    self._fillRow(row, col, acc)

    def _ensureResult(self):
        """Allocate the result if possible and copy settled values in; return it or None. Requires self._lock.

        A failure to allocate is logged and not retried until getResult().
        """
        if self._result is not None or self._unavailable:
            return self._result
        try:
            columns = self._columns(False)
            if not columns:
                return None
            accs = [self._accs.get((id(col.daqTask), col.channel)) for col in columns]
            if any(acc is None for acc in accs):
                return None
            result = self._allocate(columns, accs)
            rows = list(zip(range(len(columns)), columns, accs))
            self._result, self._rows, self._settled = result, rows, [0] * len(rows)
            for row, col, acc in rows:
                self._fillRow(row, col, acc)
        except Exception:
            self._result, self._rows, self._settled = None, [], []
            self._unavailable = True
            self._logger.warning("No partial results for this task", exc_info=True)
            return None
        return self._result

    @staticmethod
    def _allocate(columns, accs):
        """Return an unsettled TaskResultArray shaped and typed like the final result."""
        lengths = {acc.numOutput for acc in accs}
        if len(lengths) != 1:
            raise ValueError(f"channels have different lengths {sorted(lengths)}")
        n = lengths.pop()
        dtype = np.result_type(*[
            np.asarray(col.mapping(np.zeros(1, dtype=acc.output.dtype))).dtype
            for col, acc in zip(columns, accs)
        ])
        rate = float(accs[0].outputRate)
        info = [
            axis(name='Channel', cols=[(col.name, col.units) for col in columns]),
            axis(name='Time', units='s', values=np.linspace(0, float(n - 1) / rate, n)),
            {},
        ]
        result = TaskResultArray(np.zeros((len(columns), n), dtype=dtype), info=info)
        result._initSettlement([col.name for col in columns])
        return result

    def _fillRow(self, row, col, acc):
        """Copy *acc*'s settled values not yet in the result into *row*, then raise its settled count."""
        data = self._result.asarray()
        s = min(acc.nSettled, data.shape[1])
        prev = self._settled[row]
        if s <= prev:
            return
        data[row, prev:s] = col.mapping(acc.output[prev:s])
        self._settled[row] = s
        self._result._setSettled(col.name, s)

    def getResult(self):
        """Return the completed result, or None if there are no columns.

        Fills each row's unsettled part from daqTask.getData(); settled values are never rewritten.
        If the DAQ run was stopped early (getData() info 'stoppedEarly'), every row is cut to the
        acquired length, settlement() drops to that length, and info[-1] gets 'stoppedEarly',
        'numPtsRequested', 'numPtsAcquired' and 'stopTime'. Call once the DAQ tasks are stopped.
        Every call after the first success returns the same object. Logs an error and raises
        RuntimeError if the result cannot be completed as the object partialResult() returns
        (layout or settled values disagree, or a chunk listener holds it for longer than
        _FINISH_LOCK_TIMEOUT).
        """
        with self._finishLock:
            if not self._complete:
                self._final = self._finish()
                self._complete = True
            return self._final

    def _fail(self, msg):
        self._logger.error(msg)
        raise RuntimeError(msg)

    def _finish(self):
        columns = self._columns(True)
        if len(columns) == 0:
            return None
        results = {}
        for col in columns:
            res = col.daqTask.getData(col.channel)
            res['data'] = np.asarray(col.mapping(res['data']))
            res['units'] = col.units
            res['info']['validSamples'] = int(len(res['data']))
            results[col.name] = res
        names = list(results)

        if not self._lock.acquire(timeout=_FINISH_LOCK_TIMEOUT):
            self._fail("Partial results did not finish updating; the task result cannot be completed")
        try:
            target = self._result
            if target is None:
                accs = [self._accs.get((id(col.daqTask), col.channel)) for col in columns]
                if any(acc is None for acc in accs):
                    self._fail(f"Result channels {names} were not all passed to track()")
                target = self._allocate(columns, accs)
                self._settled = [0] * len(columns)
            rows = [results[n]['data'] for n in names]
            early = self._earlyStop(results, names)
            nTime = target.shape[1]
            if early is not None:
                nTime = early['numPts']
                if any(row.shape != (nTime,) for row in rows) or nTime > target.shape[1]:
                    self._fail(f"Early-stopped DAQ channels {names} have inconsistent lengths")
            if not self._fits(target, names, rows, nTime):
                self._fail("Final DAQ data does not match the layout of the partial result object")
            data = target.asarray()[:, :nTime]
            for row, name in enumerate(names):
                final = results[name]['data'].astype(data.dtype, copy=False)
                s = min(self._settled[row], nTime)
                if not _sameValues(data[row, :s], final[:s]):
                    self._fail(f"Final DAQ data for {name!r} differs from its published settled values")
                data[row, s:] = final[s:]
            info = self._buildInfo(results)
            if early is not None:
                data = np.ascontiguousarray(data)
                info[-1].update(early['info'])
            target._info = TaskResultArray(data, info=info)._info  # validated as by MetaArray()
            if early is not None:
                target._data = data
                # settled counts of output rows drop from the planned length to nTime
                target._settled = dict.fromkeys(names, nTime)
            else:
                for name in names:
                    target._setSettled(name, nTime)
            target._setComplete()
            self._result = target
            self._complete = True  # later chunk listeners must not write
            return target
        finally:
            self._lock.release()

    def _earlyStop(self, results, names):
        """Return {'numPts': result length, 'info': info[-1] entries} if stopped early, else None.

        Raises RuntimeError if only some channels were stopped early.
        """
        flags = [bool(results[n]['info'].get('stoppedEarly', False)) for n in names]
        if not any(flags):
            return None
        if not all(flags):
            self._fail(f"Only some of DAQ channels {names} were stopped early")
        first = results[names[0]]['info']
        return {
            'numPts': len(results[names[0]]['data']),
            'info': {
                'stoppedEarly': True,
                'numPtsRequested': first['numPtsRequested'],
                'numPtsAcquired': first['numPtsAcquired'],
                'stopTime': first['stopTime'],
            },
        }

    @staticmethod
    def _fits(target, names, rows, nTime):
        if [c['name'] for c in target._info[0]['cols']] != names:
            return False
        if any(row.shape != (nTime,) for row in rows):
            return False
        return np.result_type(*[row.dtype for row in rows]) == target.dtype


def _sameValues(a, b):
    return np.array_equal(a, b, equal_nan=a.dtype.kind in 'fc')
