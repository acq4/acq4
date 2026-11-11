"""Frozen copy of the original NiDAQ.Task.getData pipeline, restricted to unfiltered commands: the test oracle."""
import numpy


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


def legacyGetData(self, channel):
    """The original NiDAQ.Task.getData without its filter and denoise stages; *self* needs .st and .cmd."""
    for key in ('filterMethod', 'denoiseMethod'):
        assert self.cmd.get(key, 'None') == 'None', "the oracle covers unfiltered commands only"
    NiDAQ = LegacyNiDAQ
    res = self.st.getResult(channel)
    data = res['data']

    if 'downsample' in self.cmd:
        ds = self.cmd['downsample']
    else:
        ds = 1

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

    res['data'] = data
    res['info']['numPts'] = data.shape[0]

    return res
