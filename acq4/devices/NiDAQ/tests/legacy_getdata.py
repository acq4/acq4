"""Frozen copy of the original NiDAQ.Task.getData pipeline and the NiDAQ helpers it calls: the test oracle."""
import numpy
import scipy.signal


class LegacyNiDAQ:
    @staticmethod
    def meanResample(data, ds, binary=False):
        """Resample data by taking mean of ds samples at a time"""
        newLen = int(data.shape[0] / ds) * ds
        data = data[:newLen]
        data.shape = (int(data.shape[0] / ds), ds)
        if binary:
            return data.mean(axis=1).round().astype(numpy.byte)
        else:
            return data.mean(axis=1)

    @staticmethod
    def lowpass(data, cutoff, order=4, bidir=True, filter='bessel', stopCutoff=None, gpass=2., gstop=20.,
                samplerate=None):
        """Bi-directional bessel/butterworth lowpass filter"""
        if samplerate is not None:
            cutoff /= 0.5 * samplerate
            if stopCutoff is not None:
                stopCutoff /= 0.5 * samplerate

        if filter == 'bessel':
            b, a = scipy.signal.bessel(order, cutoff, btype='low')
        elif filter == 'butterworth':
            if stopCutoff is None:
                stopCutoff = cutoff * 2.0
            ord, Wn = scipy.signal.buttord(cutoff, stopCutoff, gpass, gstop)
            b, a = scipy.signal.butter(ord, Wn, btype='low')
        else:
            raise ValueError(f'Unknown filter type "{filter}"')

        padded = numpy.hstack(
            [data[:100], data, data[-100:]])  ## can we intelligently decide how many samples to pad with?

        if bidir:
            data = scipy.signal.lfilter(b, a, scipy.signal.lfilter(b, a, padded)[::-1])[::-1][
                   100:-100]  ## filter twice; once forward, once reversed. (This eliminates phase changes)
        else:
            data = scipy.signal.lfilter(b, a, padded)[100:-100]
        return data

    @staticmethod
    def denoise(data, radius=2, threshold=4):
        """Very simple noise removal function. Compares a point to surrounding points,
        replaces with nearby values if the difference is too large."""

        r2 = radius * 2
        d2 = data[radius:] - data[:-radius]  # a derivative
        stdev = d2.std()
        mask1 = d2 > stdev * threshold  # where derivative is large and positive
        mask2 = d2 < -stdev * threshold  # where derivative is large and negative
        maskpos = mask1[:-radius] * mask2[radius:]  # both need to be true
        maskneg = mask1[radius:] * mask2[:-radius]
        mask = maskpos + maskneg
        # where both are true replace the value with the value from 2 points before
        d5 = numpy.where(mask, data[:-r2], data[radius:-radius])
        d6 = numpy.empty(data.shape, dtype=data.dtype)  # add points back to the ends
        d6[radius:-radius] = d5
        d6[:radius] = data[:radius]
        d6[-radius:] = data[-radius:]
        return d6


def legacyGetData(self, channel):
    """The original NiDAQ.Task.getData; *self* needs .st, .cmd and .dev.logger."""
    NiDAQ = LegacyNiDAQ
    res = self.st.getResult(channel)
    data = res['data']

    if 'downsample' in self.cmd:
        ds = self.cmd['downsample']
    else:
        ds = 1

    if 'filterMethod' in self.cmd:
        method = self.cmd['filterMethod']

        if method == 'None':
            pass
        elif method == 'Bessel':
            cutoff = self.cmd['besselCutoff']
            order = self.cmd['besselOrder']
            bidir = self.cmd.get('besselBidirectional', True)
            data = NiDAQ.lowpass(data, filter='bessel', bidir=bidir, cutoff=cutoff, order=order,
                                 samplerate=res['info']['rate'])

            res['info']['filterMethod'] = method
            res['info']['filterCutoff'] = cutoff
            res['info']['filterOrder'] = order
            res['info']['filterBidirectional'] = bidir
        elif method == 'Butterworth':
            passF = self.cmd['butterworthPassband']
            stopF = self.cmd['butterworthStopband']
            passDB = self.cmd['butterworthPassDB']
            stopDB = self.cmd['butterworthStopDB']
            bidir = self.cmd.get('butterworthBidirectional', True)

            data = NiDAQ.lowpass(data, filter='butterworth', bidir=bidir, cutoff=passF, stopCutoff=stopF,
                                 gpass=passDB, gstop=stopDB, samplerate=res['info']['rate'])

            res['info']['filterMethod'] = method
            res['info']['filterPassband'] = passF
            res['info']['filterStopband'] = stopF
            res['info']['filterPassbandDB'] = passDB
            res['info']['filterStopbandDB'] = stopDB
            res['info']['filterBidirectional'] = bidir

        else:
            self.dev.logger.exception(f"Unknown filter method '{method}'")

    if ds > 1:
        if res['info']['type'] in ['di', 'do']:
            res['data'] = (res['data'] > 0).astype(numpy.byte)
            data = data[::ds]
            res['info']['downsampling'] = ds
            res['info']['downsampleMethod'] = 'subsample'
            res['info']['rate'] = res['info']['rate'] / ds
        elif res['info']['type'] in ['ai', 'ao']:
            data = NiDAQ.meanResample(data, ds)
            res['info']['downsampling'] = ds
            res['info']['downsampleMethod'] = 'mean'
            res['info']['rate'] = res['info']['rate'] / ds

    if 'denoiseMethod' in self.cmd:
        method = self.cmd['denoiseMethod']
        if method == 'None':
            pass
        elif method == 'Pointwise':
            width = self.cmd['denoiseWidth']
            thresh = self.cmd['denoiseThreshold']

            res['info']['denoiseMethod'] = method
            res['info']['denoiseWidth'] = width
            res['info']['denoiseThreshold'] = thresh
            data = NiDAQ.denoise(data, width, thresh)
        else:
            self.dev.logger.exception(f"Unknown denoise method '{method}'")

    res['data'] = data
    res['info']['numPts'] = data.shape[0]

    return res
