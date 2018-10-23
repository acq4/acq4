from __future__ import print_function
from __future__ import division
import numpy as np
from acq4.devices.Scanner.scan_program.spiral import SpiralScan


def test_spiral():
    r1 = 10e-6
    r2 = 20e-6
    a1 = 1.
    a2 = 30.
    ss = SpiralScan((r1, r2), (a1, a2))
    
    # check that analytically computed path length matches numerically computed
    # paths
    l1 = ss.length()
    
    npts = ss.path(10000, uniform=False)
    dif = npts[1:] - npts[:-1]
    l2 = ((dif**2).sum(axis=1)**0.5).sum()
    assert np.allclose(l1, l2)

    upts = ss.path(10000, uniform=True)
    dif = upts[1:] - upts[:-1]
    ulengths = (dif**2).sum(axis=1)**0.5
    l3 = ulengths.sum()
    assert np.allclose(l1, l3)
    
    assert ulengths.std() / ulengths.mean() < 1e-5

    # check that uniform spacing actually works
    assert np.allclose(upts[0], npts[0])
    assert np.allclose(upts[-1], npts[-1])
    assert np.allclose(ulengths, l1 / (len(upts)-1))
    
    