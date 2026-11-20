"""Per-channel NI-DAQ result processing (downsampling), computed incrementally while the record is acquired."""

import logging

import numpy as np

from acq4.util.partial_results import SettleSpec

_defaultLogger = logging.getLogger(__name__)

_RAW_DTYPES = {'ai': np.float64, 'di': np.uint32, 'ao': np.float64, 'do': np.uint32}  # expected until known


def checkCommand(cmd):
    """Raise ValueError if DAQ task command *cmd* requests filtering or non-integer downsampling.

    'filterMethod' and 'denoiseMethod' may be absent or 'None'.
    """
    for key in ('filterMethod', 'denoiseMethod'):
        method = cmd.get(key, 'None')
        if method != 'None':
            raise ValueError(
                f"DAQ task command requests {key}={method!r}, but filtering was removed from the NI-DAQ "
                "device; filter the data downstream"
            )
    ds = cmd.get('downsample', 1)
    if ds > 1 and ds != int(ds):
        raise ValueError(f"DAQ downsampling must be a whole number (got {ds!r})")


def _sameArray(a, b):
    if a.dtype != b.dtype or a.shape != b.shape:
        return False
    return np.array_equal(a, b, equal_nan=a.dtype.kind in 'fc')


class DaqChannelAccumulator:
    """One channel's getData() output, settled progressively while the task acquires it.

    Settled values are final: getData() computes the rest with the same code and never rewrites them.

    Attributes:
        channel: absolute channel name.
        chanType: 'ai', 'ao', 'di' or 'do'.
        numOutput: length of output.
        outputRate: output sample rate (Hz).
        output: 1-D array; output[:nSettled] holds final values. May be replaced by a new array
            (reset(), setOutputWaveform(), first update()); copy out of it rather than keep it.
        nSettled: settled output samples; never decreases within a run.
        settleDepth: input samples behind the acquisition edge at which output settles.
        settleSpec: SettleSpec for settleDepth.

    Output channels (ao/do) are settled by setOutputWaveform(); input channels by update().
    """

    def __init__(self, channel, chanType, cmd, logger=None):
        """*cmd* is the DAQ task command (rate, numPts, downsample); raises ValueError as checkCommand()."""
        checkCommand(cmd)
        self.channel = channel
        self.chanType = chanType
        self._logger = logger if logger is not None else _defaultLogger
        self._numInput = int(cmd['numPts'])
        rate = cmd['rate']
        ds = cmd.get('downsample', 1)
        self._dsCmd = ds  # as given; recorded in the result info
        self._ds = int(ds) if ds > 1 else 1
        if self._ds == 1:
            self._method = None
        else:
            self._method = 'subsample' if chanType in ('di', 'do') else 'mean'
        self.numOutput = self._outputCount(self._numInput)
        self.outputRate = rate / ds if ds > 1 else rate

        if chanType in ('ao', 'do'):
            self.settleDepth, reason = 0, "output waveform"
        elif self._method == 'mean':
            self.settleDepth, reason = self._ds - 1, f"{self._ds}x mean downsampling"
        else:
            self.settleDepth, reason = 0, ""
        self.settleSpec = SettleSpec(self.settleDepth / rate, reason)

        self.output = np.empty(self.numOutput, dtype=self._outputDtype(_RAW_DTYPES[chanType]))
        self.reset()

    def _outputCount(self, nIn):
        """Return the number of output samples computable from the first *nIn* input samples."""
        if self._method == 'mean':
            return nIn // self._ds
        if self._method == 'subsample':
            return -(-nIn // self._ds)
        return nIn

    def _outputDtype(self, rawDtype):
        if self._method == 'mean':
            return np.zeros((1, self._ds), dtype=rawDtype).mean(axis=1).dtype
        return np.dtype(rawDtype)

    def _compute(self, raw, j0, j1):
        """Return output samples [j0, j1) from *raw*, which holds at least the input they need."""
        ds = self._ds
        if self._method == 'mean':
            return raw[j0 * ds:j1 * ds].reshape(j1 - j0, ds).mean(axis=1)
        if self._method == 'subsample':
            return raw[j0 * ds:j1 * ds:ds]
        return raw[j0:j1]

    def reset(self, rawDtype=None):
        """Start a new run: discard settled values.

        *rawDtype* is the dtype of the channel's raw buffer, if known.
        """
        self._finalized = False
        self.nSettled = 0
        if rawDtype is not None:
            self._useRawDtype(rawDtype)

    def _useRawDtype(self, rawDtype):
        dtype = self._outputDtype(rawDtype)
        if self.chanType in ('ai', 'di') and self.output.dtype != dtype:
            self.output = np.empty(self.numOutput, dtype=dtype)

    def _checkLength(self, data):
        if data.shape != (self._numInput,):
            raise ValueError(f"{self.channel}: expected {self._numInput} samples, got shape {data.shape}")

    def setOutputWaveform(self, waveform):
        """Fill output from the full *waveform* written to this output channel and mark it all settled."""
        waveform = np.asarray(waveform)
        self._checkLength(waveform)
        values = self._compute(waveform, 0, self.numOutput)
        if self.output.dtype != values.dtype:
            self.output = np.empty(self.numOutput, dtype=values.dtype)
        self.output[...] = values
        self.nSettled = self.numOutput

    def update(self, raw, nAcquired):
        """Settle the output computable from raw input up to sample *nAcquired*.

        *raw* is the channel's full-length raw buffer. Called on the DAQ reader thread with
        non-decreasing *nAcquired*. No-op for output channels and once finalized.
        """
        if self._finalized or self.chanType not in ('ai', 'di'):
            return
        self._advance(raw, nAcquired)

    def _advance(self, raw, nAcquired):
        """Compute and settle output samples from nSettled up to what *nAcquired* inputs allow."""
        j0 = self.nSettled
        j1 = self._outputCount(min(int(nAcquired), self._numInput))
        if j1 <= j0:
            return
        self._checkLength(raw)
        if j0 == 0:
            self._useRawDtype(raw.dtype)
        self.output[j0:j1] = self._compute(raw, j0, j1)
        self.nSettled = j1

    def finalize(self, res):
        """Return getData()'s result from SuperTask.getResult(channel)'s *res*, and settle all of output.

        Input channels: computes only the unsettled rest of output from res['data'] (the raw buffer).
        Output channels: settles from res['data'] if not yet settled, else raises RuntimeError if
        it differs from what was settled. *res* is updated in place; its 'data' becomes output.
        Safe to call more than once.
        """
        raw = res['data']
        if self.chanType in ('ai', 'di'):
            self._checkLength(raw)
            self._advance(raw, self._numInput)
        elif self.nSettled < self.numOutput:
            self.setOutputWaveform(raw)
        else:
            self._checkLength(raw)
            if not _sameArray(self._compute(raw, 0, self.numOutput), self.output):
                msg = f"Waveform of output channel {self.channel} changed after its partial result was settled"
                self._logger.error(msg)
                raise RuntimeError(msg)
        self._finalized = True

        info = res['info']
        if self._method is not None:
            info['downsampling'] = self._dsCmd
            info['downsampleMethod'] = self._method
            info['rate'] = info['rate'] / self._dsCmd
        info['numPts'] = self.output.shape[0]
        res['data'] = self.output
        return res
