from scipy.signal import butter, lfilter, sosfilt

import pyqtgraph as pg


def butter_transform(x, y, order, cutoff):
    sample_rate = (len(x) - 1) / (x[-1] - x[0])
    sos = butter(order, cutoff, fs=sample_rate, btype="low", analog=False, output="sos")
    return x, sosfilt(sos, y)


if hasattr(pg.PlotItem, "addDefaultDataTransformOption"):
    pg.PlotItem.addDefaultDataTransformOption(
        "Butter Low-pass",
        butter_transform,
        params=[
            {"name": "cutoff", "type": "float", "siPrefix": True, "suffix": "Hz", "min": 0, "value": 5000},
            {"name": "order", "type": "int", "min": 1, "value": 5},
        ],
    )
    pg.PlotItem.addDefaultDataTransformOption(
        "Gaussian Low-pass",
        lambda _x, _y, sigma: (_x, pg.gaussianFilter(_y, sigma)),
        params=[{"name": "sigma", "type": "float", "suffix": "", "min": 0, "value": 5}],
    )
