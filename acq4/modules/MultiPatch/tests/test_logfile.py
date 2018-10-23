from __future__ import print_function
import numpy as np
from acq4.modules.MultiPatch.logfile import MultiPatchLog, IrregularTimeSeries


def test_timeseries_index():
    
    ts1 = [
        (10, 0.5),
        (12, 13.4),
        (29.8, 5),
        (29.8, 5.5),
        (29.9, 6),
        (30.0, 7),
        (30.1, 8),
        (35, 0),
    ]
    
    ts2 = [
        (10, (0.5, 13.4)),
        (12, (13.4, 5)),
        (29.8, (5, 0)),
        (29.9, (6, -102.7)),
        (30.0, (7, 23.)),
        (30.0, (7, 24.)),
        (30.1, (8, 0)),
        (35, (0, 0)),
    ]
    
    ts3 = [
        (10, 'a'),
        (12, 'b'),
        (29.8, 'c'),
        (29.9, 'd'),
        (30.0, 'e'),
        (30.1, 'f'),
        (30.1, 'g'),
        (35, 'h'),
    ]
    
    def lookup(t, ts):
        # inefficient (but easier to test) method for doing timeseries lookup
        # for comparison
        low = None
        for i,ev in enumerate(ts.events):
            if ev[0] <= t:
                low = i
            else:
                break
        if low is None:
            return None
        if low+1 >= len(ts.events) or ts.interpolate is False:
            return ts.events[low][1]
        else:
            t1, v1 = ts.events[low]
            t2, v2 = ts.events[low+1]
            return ts._interpolate(t, v1, v2, t1, t2)
        
    for tsdata in (ts1, ts2, ts3):
        for interp in (True, False):
            if interp and isinstance(tsdata[0][1], str):
                # don't test interpolation on strings
                continue
            for res in (0.1, 1.0, 10.0):
                ts = IrregularTimeSeries(interpolate=interp, resolution=res)
                for t,v in tsdata:
                    ts[t] = v
                for t in np.arange(-1, 40, 0.05):
                    assert ts[t] == lookup(t, ts)
    