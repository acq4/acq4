"""Per-channel NI-DAQ result processing, for the whole record or incrementally while it is acquired."""

import logging
import math

import numpy as np
import pyqtgraph as pg
import scipy.signal

from acq4.util.partial_results import SettleSpec

_defaultLogger = logging.getLogger(__name__)

SETTLE_EPS = 1e-6  # bidirectional filter: residual edge transient, as a fraction, treated as settled
_PAD = 100  # samples of edge padding in NiDAQ.lowpass
_REVERSE_PASS_TOL = 1e-6  # max relative error of an edge-started reverse pass accepted at configure time
_RAW_DTYPES = {'ai': np.float64, 'di': np.uint32, 'ao': np.float64, 'do': np.uint32}  # expected until known


def _NiDAQ():
    from .nidaq import NiDAQ  # nidaq imports this module

    return NiDAQ


def processChannelData(res, cmd, logger):
    """Apply *cmd*'s filter, downsampling and denoising to one channel's result, as NiDAQ.Task.getData returns it.

    *res* is SuperTask.getResult(channel)'s {'data', 'info'}; it is updated in place and returned.
    """
    NiDAQ = _NiDAQ()
    data = res['data']

    if 'downsample' in cmd:
        ds = cmd['downsample']
    else:
        ds = 1

    if 'filterMethod' in cmd:
        method = cmd['filterMethod']

        if method == 'None':
            pass
        # elif method == 'gaussian':
        # width = cmd['gaussianWidth']

        # data = scipy.ndimage.gaussian_filter(data, width)

        # res['info']['filterMethod'] = method
        # res['info']['filterWidth'] = width
        elif method == 'Bessel':
            cutoff = cmd['besselCutoff']
            order = cmd['besselOrder']
            bidir = cmd.get('besselBidirectional', True)
            data = NiDAQ.lowpass(data, filter='bessel', bidir=bidir, cutoff=cutoff, order=order,
                                 samplerate=res['info']['rate'])

            res['info']['filterMethod'] = method
            res['info']['filterCutoff'] = cutoff
            res['info']['filterOrder'] = order
            res['info']['filterBidirectional'] = bidir
        elif method == 'Butterworth':
            passF = cmd['butterworthPassband']
            stopF = cmd['butterworthStopband']
            passDB = cmd['butterworthPassDB']
            stopDB = cmd['butterworthStopDB']
            bidir = cmd.get('butterworthBidirectional', True)

            data = NiDAQ.lowpass(data, filter='butterworth', bidir=bidir, cutoff=passF, stopCutoff=stopF,
                                 gpass=passDB, gstop=stopDB, samplerate=res['info']['rate'])

            res['info']['filterMethod'] = method
            res['info']['filterPassband'] = passF
            res['info']['filterStopband'] = stopF
            res['info']['filterPassbandDB'] = passDB
            res['info']['filterStopbandDB'] = stopDB
            res['info']['filterBidirectional'] = bidir

        else:
            logger.exception(f"Unknown filter method '{method}'")

    if ds > 1:
        if res['info']['type'] in ['di', 'do']:
            res['data'] = (res['data'] > 0).astype(np.byte)
            data = data[::ds]
            res['info']['downsampling'] = ds
            res['info']['downsampleMethod'] = 'subsample'
            res['info']['rate'] = res['info']['rate'] / ds
        elif res['info']['type'] in ['ai', 'ao']:
            data = NiDAQ.meanResample(data, ds)
            res['info']['downsampling'] = ds
            res['info']['downsampleMethod'] = 'mean'
            res['info']['rate'] = res['info']['rate'] / ds

    if 'denoiseMethod' in cmd:
        method = cmd['denoiseMethod']
        if method == 'None':
            pass
        elif method == 'Pointwise':
            width = cmd['denoiseWidth']
            thresh = cmd['denoiseThreshold']

            res['info']['denoiseMethod'] = method
            res['info']['denoiseWidth'] = width
            res['info']['denoiseThreshold'] = thresh
            data = NiDAQ.denoise(data, width, thresh)
        else:
            logger.exception(f"Unknown denoise method '{method}'")

    res['data'] = data
    res['info']['numPts'] = data.shape[0]

    return res


class _QuietLogger:
    def exception(self, *args, **kwargs):
        pass


def _decayLength(poles, eps=SETTLE_EPS):
    """Return the samples needed for a transient of *poles* to decay by *eps*.

    len(poles) if every pole is at the origin (FIR); math.inf if any is on or outside the unit circle.
    """
    r = float(np.max(np.abs(poles))) if len(poles) else 0.0
    if r == 0:
        return len(poles)
    if not r < 1:
        return math.inf
    return math.ceil(math.log(eps) / math.log(r))


def _reversePassAccurate(b, a, depth, zi):
    """Return True if a reverse pass started *depth* samples ahead matches one started at the record end.

    Checked on in-band random test signals, with and without a dominant DC level, relative to
    max(1, signal amplitude). *zi* is the unit-step steady state used to seed the edge-started pass.
    Fails for transfer functions too ill-conditioned for partial results to match the final ones.
    """
    n = 4 * depth + 64
    edge = n - depth
    with np.errstate(all='ignore'):
        band = scipy.signal.lfilter(b, a, np.random.default_rng(0).standard_normal(n))
        band = band / band.std()
        for f in (1.0 + band, 1.0 + 1e-3 * band):
            exact = scipy.signal.lfilter(b, a, f[::-1])[::-1]
            part = scipy.signal.lfilter(b, a, f[edge - 1::-1], zi=zi * f[edge - 1])[0][::-1]
            m = edge - depth
            err = np.abs(part[:m] - exact[:m]).max() / max(1.0, np.abs(exact).max())
            if not err <= _REVERSE_PASS_TOL:
                return False
    return True


class DaqChannelAccumulator:
    """One channel's getData() output, settled progressively while the task acquires it.

    Attributes:
        channel: absolute channel name.
        chanType: 'ai', 'ao', 'di' or 'do'.
        numOutput: length of output.
        outputRate: output sample rate (Hz).
        output: 1-D array; output[:nSettled] is within 1e-5 * max(1, max|final|) of the final values.
            May be replaced by a new array (reset(), finalize()); copy out of it rather than keep it.
        nSettled: settled output samples; never decreases within a run.
        settleDepth: input samples behind the acquisition edge at which output settles (math.inf: at finalize).
        settleSpec: SettleSpec for settleDepth.

    Output channels (ao/do) are settled by setOutputWaveform(); input channels by update().
    """

    def __init__(self, channel, chanType, cmd, logger=None):
        """*cmd* is the DAQ task command (rate, numPts, downsample, filter and denoise settings)."""
        self.channel = channel
        self.chanType = chanType
        self._cmd = cmd
        self._logger = logger if logger is not None else _defaultLogger
        self._numInput = int(cmd['numPts'])
        self._rate = cmd['rate']
        ds = cmd['downsample'] if 'downsample' in cmd else 1
        self._ds = int(ds) if ds > 1 and ds == int(ds) else 1
        self._mean = self._ds > 1 and chanType in ('ai', 'ao')
        self._subsample = self._ds > 1 and chanType in ('di', 'do')
        self._filtered = cmd.get('filterMethod') in ('Bessel', 'Butterworth')
        self._filter = None  # (b, a, bidir, depth, zi) when filtering incrementally

        n = self._numInput
        if self._filtered:
            n = n if n >= _PAD else max(0, 3 * n - 2 * _PAD)
        if self._subsample:
            n = -(-n // self._ds)
        elif self._mean:
            n //= self._ds
        self.numOutput = n
        self.outputRate = self._rate / ds if ds > 1 else self._rate

        self.settleDepth, reason = self._planSettling(ds)
        self.settleSpec = SettleSpec(self.settleDepth / self._rate, reason)
        self._incremental = chanType in ('ai', 'di') and math.isfinite(self.settleDepth)

        self.output = np.empty(n, dtype=self._outputDtype(_RAW_DTYPES[chanType]))
        self.reset()

    def _filterDesign(self):
        """Return (lowpassDesign kwargs, label, bidir) for the command's filter."""
        cmd = self._cmd
        if cmd['filterMethod'] == 'Bessel':
            cutoff = cmd['besselCutoff']
            design = dict(filter='bessel', cutoff=cutoff, order=cmd['besselOrder'], samplerate=self._rate)
            label = f"Bessel, {pg.siFormat(cutoff, suffix='Hz')} cutoff"
            bidir = cmd.get('besselBidirectional', True)
        else:
            passF = cmd['butterworthPassband']
            design = dict(filter='butterworth', cutoff=passF, stopCutoff=cmd['butterworthStopband'],
                          gpass=cmd['butterworthPassDB'], gstop=cmd['butterworthStopDB'], samplerate=self._rate)
            label = f"Butterworth, {pg.siFormat(passF, suffix='Hz')} passband"
            bidir = cmd.get('butterworthBidirectional', True)
        return design, label, bool(bidir)

    def _planSettling(self, ds):
        """Return (settle depth, reason); set up incremental filtering."""
        if self.chanType in ('ao', 'do'):
            return 0, "output waveform"
        if self._cmd.get('denoiseMethod') == 'Pointwise':
            return math.inf, "denoise needs the whole record"
        if ds > 1 and ds != int(ds):
            return math.inf, "non-integer downsampling"
        depth = 0
        reasons = []
        if self._filtered:
            if self.chanType == 'di':
                return math.inf, "filtering is not computed incrementally for digital channels"
            if self._numInput <= _PAD:
                return math.inf, f"record too short for incremental filtering ({self._numInput} samples)"
            try:
                design, label, bidir = self._filterDesign()
                b, a = _NiDAQ().lowpassDesign(**design)
                poles = _NiDAQ().lowpassDesign(output='zpk', **design)[1]
                filtDepth = _decayLength(poles) if bidir else 0
                zi = scipy.signal.lfilter_zi(b, a) if bidir and math.isfinite(filtDepth) else None
            except Exception as exc:  # getData() raises it; here it only means no partial results
                return math.inf, f"invalid filter settings ({exc})"
            if bidir:
                if not math.isfinite(filtDepth):
                    return math.inf, f"unstable filter ({label})"
                if filtDepth < self._numInput and not _reversePassAccurate(b, a, filtDepth, zi):
                    return math.inf, f"filter too ill-conditioned for partial results ({label})"
                depth += filtDepth
                reasons.append(f"bidirectional {label}")
            else:
                reasons.append(f"causal {label}")
            self._filter = (b, a, bidir, filtDepth, zi)
        if self._mean:
            depth += self._ds - 1
            reasons.append(f"{self._ds}x mean downsampling")
        return depth, "; ".join(reasons) or "unfiltered"

    def _outputDtype(self, rawDtype):
        return np.dtype(np.float64) if self._filtered or self._mean else np.dtype(rawDtype)

    def reset(self, rawDtype=None):
        """Start a new run: discard settled values and incremental state.

        *rawDtype* is the dtype of the channel's raw buffer, if known.
        """
        self._finalized = False
        self.nSettled = 0
        self._nIn = 0  # input samples consumed by update()
        self._fwdIn = None  # input samples through the forward filter; None until the leading pad is filtered
        self._zf = None
        self._pending = np.empty(0)  # bidirectional: forward output not yet settled
        self._ySettled = 0  # filter-stage samples settled
        self._carry = np.empty(0)  # mean downsampling: settled samples of the incomplete bin
        self._nReversed = 0  # samples run through partial reverse passes this run
        if rawDtype is not None:
            self._useRawDtype(rawDtype)

    def _useRawDtype(self, rawDtype):
        dtype = self._outputDtype(rawDtype)
        if self.chanType in ('ai', 'di') and self.output.dtype != dtype:
            self.output = np.empty(self.numOutput, dtype=dtype)

    def setOutputWaveform(self, waveform):
        """Fill output from the full *waveform* written to this output channel and mark it all settled."""
        info = {'startTime': None, 'numPts': self._numInput, 'rate': self._rate, 'type': self.chanType}
        res = processChannelData({'data': np.asarray(waveform), 'info': info}, self._cmd, _QuietLogger())
        self._store(res['data'])

    def _store(self, data):
        n = data.shape[0]
        if self.output.shape != (n,) or self.output.dtype != data.dtype:
            self.output = np.empty(n, dtype=data.dtype)
            self.numOutput = n
        self.output[...] = data
        self.nSettled = n

    def update(self, raw, nAcquired):
        """Process raw input up to sample *nAcquired* and advance nSettled.

        *raw* is the channel's full-length raw buffer. Called on the DAQ reader thread with
        non-decreasing *nAcquired*; the call at nAcquired == numPts settles everything that ever
        settles before finalize(). No-op for output channels and once finalized.
        """
        if self._finalized or not self._incremental:
            return
        n = min(int(nAcquired), self._numInput)
        if n <= self._nIn:
            return
        if self._nIn == 0:
            self._useRawDtype(raw.dtype)
        y0, y = self._advanceFilter(raw, n)
        self._nIn = n
        if y is not None and len(y) > 0:
            self._advanceOutput(y0, y)

    def _advanceFilter(self, raw, n):
        """Return (start, values) of newly settled filter-stage samples, given input through *n*."""
        if self._filter is None:
            return self._nIn, raw[self._nIn:n]
        b, a, bidir, depth, zi = self._filter
        if self._fwdIn is None:
            if n < _PAD:
                return 0, None
            # NiDAQ.lowpass's leading pad is the record's first _PAD samples
            self._zf = scipy.signal.lfilter(b, a, raw[:_PAD], zi=np.zeros(max(len(a), len(b)) - 1))[1]
            self._fwdIn = 0
        fwd, self._zf = scipy.signal.lfilter(b, a, raw[self._fwdIn:n], zi=self._zf)
        start = self._fwdIn
        self._fwdIn = n
        if not bidir:
            return start, fwd

        pending = np.concatenate([self._pending, fwd]) if len(self._pending) else fwd
        s = self._ySettled
        N = self._numInput
        if n == N:
            # whole record known: reverse pass from the padded end, exactly as NiDAQ.lowpass
            tail = scipy.signal.lfilter(b, a, raw[N - _PAD:N], zi=self._zf)[0]
            seq = np.concatenate([pending, tail])
            self._nReversed += len(seq)
            self._pending = np.empty(0)
            self._ySettled = N
            return s, scipy.signal.lfilter(b, a, seq[::-1])[::-1][:N - s]
        settled = n - depth
        if settled <= s:
            self._pending = pending
            return s, None
        rev = scipy.signal.lfilter(b, a, pending[::-1], zi=zi * pending[-1])[0][::-1]
        self._nReversed += len(pending)
        self._pending = pending[settled - s:]
        self._ySettled = settled
        return s, rev[:settled - s]

    def _advanceOutput(self, y0, y):
        """Downsample settled filter-stage values *y* (starting at index *y0*) into output."""
        ds = self._ds
        if self._mean:
            if len(self._carry):
                y0 -= len(self._carry)
                y = np.concatenate([self._carry, y])
            j0 = y0 // ds
            nb = min(len(y) // ds, self.numOutput - j0)
            if nb > 0:
                self.output[j0:j0 + nb] = y[:nb * ds].reshape(nb, ds).mean(axis=1)
                self.nSettled = j0 + nb
            self._carry = np.array(y[max(nb, 0) * ds:])
        elif self._subsample:
            j0 = -(-y0 // ds)
            j1 = min(-(-(y0 + len(y)) // ds), self.numOutput)
            if j1 > j0:
                self.output[j0:j1] = y[j0 * ds - y0::ds][:j1 - j0]
                self.nSettled = j1
        else:
            j1 = min(y0 + len(y), self.numOutput)
            self.output[y0:j1] = y[:j1 - y0]
            self.nSettled = j1

    def finalize(self, res):
        """Return getData()'s result from SuperTask.getResult(channel)'s *res*, and settle all of output.

        Runs the full processing over *res* (updated in place), independent of update(). The
        returned 'data' is output. Safe to call more than once.
        """
        self._finalized = True
        res = processChannelData(res, self._cmd, self._logger)
        self._store(res['data'])
        res['data'] = self.output
        return res
