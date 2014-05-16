from __future__ import division
import numpy as np
from acq4.devices.Scanner.ScanProgram.rect import RectScan

def assertState(rs, state):
    #print "=== assert state:"
    #print rs.saveState()
    #print state
    for name, var in rs._vars.items():
        expect = state.get(name, None)
        if isinstance(expect, np.ndarray):
            assert var[0].shape == expect.shape and np.all(var[0] == expect)
        else:
            assert var[0] == expect

def isMultiple(x, y):
    return (x%y) == 0

def test_RectScan():
    global rs
    rs = RectScan()
    assertState(rs, {})
    
    rs.p0 = (5,6)
    
    # can't compute width yet
    try:
        rs.width
        raise Exception("Expected RuntimeError.")
    except RuntimeError:
        pass
    
    # Add a second point; now width is available.
    rs.p1 = (11, 14)
    assert rs.width == 10
    
    # Add a third point to define height
    rs.p2 = (9, 3)
    assert rs.height == 5
    
    # Check the complete state
    state = {'p0': np.array([5,6]),
             'p1': np.array([11,14]),
             'p2': np.array([9,3]),
             'height': 5,
             'width': 10
             }
    assertState(rs, state)
    
    # Setting p2 a second time causes width, height to reset.
    rs.p2 = (9, 4) 
    rs.p2 = (9, 3) # ..and reset it to keep the nice round distances
    state.pop('width')
    state.pop('height')
    assertState(rs, state)

    # ..but we can still easily regenerate width
    assert rs.width == 10
    state['width'] = 10
    assertState(rs, state)
    
    # Assigning a new p1 should cause width to change
    rs.p1 = (14, 18)
    assert rs.width == 15
    
    # Now something more complex:
    sr = 1000
    rs.sampleRate = sr
    ds = 1
    rs.downsample = ds
    ss = 1e-6 / 1e-3  # 1 um/ms
    rs.scanSpeed = ss
    assert rs.pixelWidth == (ss / sr) * ds
    
    rs.scanSpeed = None
    try:
        rs.pixelWidth
        raise Exception("Expected RuntimeError")
    except RuntimeError:
        pass
    
    # can we determine the size of a pixel given the desired scan duration 
    # and pixel aspect ratio?
    # size is now 15x5, so we will shoot for a 16x6 = 96 pixel grid
    rs.duration = 96e-3
    rs.overscan = 0.0
    rs.pixelAspectRatio = 1.0
    assert np.all(rs.scanShape == (16, 6))
    assert rs.pixelWidth == 1.0
    assert rs.pixelHeight == 1.0
    
    # other aspect ratios?
    rs.duration = 48e-3
    rs.overscan = 0.0
    rs.pixelAspectRatio = 2.0
    assert np.all(rs.scanShape == (8, 6))
    assert rs.pixelWidth == 2.0
    assert rs.pixelHeight == 1.0
    
    # Can we determine duration given the desired pixel size?
    rs.duration = None
    rs.pixelWidth = 1.0
    rs.pixelHeight = 1.0
    # todo: setting pxw and pxh should be impossible if pxar is already specified.
    assert np.all(rs.scanShape == (16, 6))
    assert rs.duration == 96e-3
    
    # overscan has the intended effect?
    pxTime = rs.pixelWidth / rs.scanSpeed
    rs.overscan = pxTime  # should add 1 pixel to either side
    assert np.all(rs.scanShape == (18, 6))
    assert np.all(rs.imageShape == (16, 6))
    assert rs.duration == 108e-3
    
    # downsampling?
    rs.overscan = 0
    rs.downsample = 10
    assert rs.duration == 0.96
    assert np.all(rs.scanShape == (160, 6))
    assert np.all(rs.imageShape == (16, 6))

    # downsampling + overscan
    rs.overscan = 0.01
    assert rs.duration == 1.08
    assert np.all(rs.scanShape == (180, 6))
    assert np.all(rs.imageShape == (16, 6))
    
    # todo: make sure that all offsets and strides are integer multiples of downsampling
    rs.overscan = 0.025
    assert isMultiple(rs.scanShape[0], rs.downsample)
    assert isMultiple(rs.scanStride[0], rs.downsample)
    assert isMultiple(rs.activeShape[0], rs.downsample)
    assert isMultiple(rs.activeStride[0], rs.downsample)
    assert isMultiple(rs.activeOffset, rs.downsample)
    
    # todo: make sure that the complete state does not depend on the order
    # in which parameters are accessed
    rs.bidirectional = True
    np.random.seed(1245)
    unfixed = [n for n in rs._vars if rs._vars[n][2] is None]
    for n in unfixed: # initialize all
        getattr(rs, n)
    state = dict([(n,v[0]) for n,v in rs.saveState().items()])
    for i in range(30):
        print "================== reset ===================="
        rs.resetUnfixed()
        np.random.shuffle(unfixed)
        for n in unfixed:
            v = getattr(rs, n)
            print n, v, state[n]
        assertState(rs, state)
    
    # test save/restore
    
if __name__ == '__main__':
    import user
    test_RectScan()