"""A DAQ device task's result MetaArray, filled with settled values while the task runs."""

import functools
import threading
from typing import Callable, NamedTuple, Optional

import numpy as np

from MetaArray import axis
from acq4.util.partial_results import TaskResultArray

_FINISH_LOCK_TIMEOUT = 2.0  # s; getResult() gives up on the partial object if a chunk listener holds it longer


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
    channel has been passed to track(). getResult() writes the final values into that same object.
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

    def _ensureResult(self, fill=True):
        """Allocate the result if possible; return it or None. Requires self._lock.

        With *fill*, settled values are copied in and a failure to allocate is logged; getResult()
        passes False since it writes every row and handles the failure itself.
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
            if fill:
                for row, col, acc in rows:
                    self._fillRow(row, col, acc)
        except Exception:
            self._result, self._rows, self._settled = None, [], []
            self._unavailable = True
            if fill:
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

        Final values come from daqTask.getData(); call once the DAQ tasks are stopped. Every call
        after the first success returns the same object.
        """
        with self._finishLock:
            if not self._complete:
                self._final = self._finish()
                self._complete = True
            return self._final

    def _finish(self):
        results = {}
        for col in self._columns(True):
            res = col.daqTask.getData(col.channel)
            res['data'] = col.mapping(res['data'])
            res['units'] = col.units
            results[col.name] = res
        if len(results) == 0:
            return None
        for res in results.values():
            res['info']['validSamples'] = int(len(res['data']))
        names = list(results)
        chanList = [np.atleast_2d(res['data']) for res in results.values()]

        if not self._lock.acquire(timeout=_FINISH_LOCK_TIMEOUT):
            self._logger.warning("Partial results did not finish updating; returning a new result object")
        else:
            try:
                target = self._ensureResult(fill=False)
                if target is not None and self._fits(target, names, chanList):
                    info = self._buildInfo(results)
                    data = target.asarray()
                    for row, arr in enumerate(chanList):
                        data[row] = arr[0]
                    target._info = TaskResultArray(data, info=info)._info  # validated as by MetaArray()
                    self._completeSettlement(target, names, chanList)
                    self._final = target
                    self._complete = True  # later chunk listeners must not write
                    return target
            finally:
                self._lock.release()
            if target is not None:
                self._logger.warning("Final result does not match the partial result's layout; returning a new object")

        target = TaskResultArray(np.concatenate(chanList), info=self._buildInfo(results))
        target._initSettlement(names)
        self._completeSettlement(target, names, chanList)
        return target

    @staticmethod
    def _completeSettlement(target, names, chanList):
        for name, arr in zip(names, chanList):
            target._setSettled(name, arr.shape[1])
        target._setComplete()

    @staticmethod
    def _fits(target, names, chanList):
        if [c['name'] for c in target._info[0]['cols']] != names:
            return False
        if any(arr.shape != (1, target.shape[1]) for arr in chanList):
            return False
        return np.result_type(*[arr.dtype for arr in chanList]) == target.dtype
