from __future__ import print_function
from __future__ import division
import numpy as np
from acq4.devices.Scanner.ScanProgram.rect import RectScan, RectScanParameter
from acq4.pyqtgraph.parametertree import ParameterTree
import acq4.pyqtgraph as pg

def assertState(rs, state):
    #print "=== assert state:"
    #print rs.saveState()
    #print state
    for name, var in rs._vars.items():
        expect = state.get(name, None)
        try:
            if isinstance(expect, np.ndarray):
                assert var[0].shape == expect.shape and np.all(var[0] == expect)
            else:
                assert var[0] == expect
        except AssertionError:
            raise ValueError("State key '%s' does not match expected value: %s != %s" % (name, var[0], expect))

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
    ## setting scan speed is currently disabled.
    # ss = 1e-6 / 1e-3  # 1 um/ms
    # rs.scanSpeed = ss
    # assert rs.pixelWidth == (ss / sr) * ds    
    # rs.scanSpeed = None
    # try:
    #     rs.pixelWidth
    #     raise Exception("Expected RuntimeError")
    # except RuntimeError:
    #     pass
    
    # can we determine the size of a pixel given the desired scan duration 
    # and pixel aspect ratio?
    # size is now 15x5, so we will shoot for a 16x6 = 96 pixel grid
    rs.frameDuration = 96e-3
    rs.minOverscan = 0.0
    rs.pixelAspectRatio = 1.0
    rs.numFrames = 1
    rs.interFrameDuration = 0.
    assert np.all(rs.scanShape == (1, 6, 16))
    assert rs.pixelWidth == 1.0
    assert rs.pixelHeight == 1.0
    
    # other aspect ratios?
    rs.frameDuration = 48e-3
    rs.minOverscan = 0.0
    rs.pixelAspectRatio = 2.0
    assert np.all(rs.scanShape == (1, 6, 8))
    assert rs.pixelWidth == 2.0
    assert rs.pixelHeight == 1.0
    
    # Can we determine duration given the desired pixel size?
    rs.frameDuration = None
    rs.pixelWidth = 1.0
    rs.pixelHeight = 1.0
    # todo: setting pxw and pxh should be impossible if pxar is already specified.
    assert np.all(rs.scanShape == (1, 6, 16))
    assert rs.frameDuration == 96e-3
    
    # overscan has the intended effect?
    pxTime = rs.pixelWidth / rs.scanSpeed
    rs.minOverscan = pxTime  # should add 1 pixel to either side
    assert np.all(rs.scanShape == (1, 6, 18))
    assert np.all(rs.imageShape == (1, 6, 16))
    assert rs.frameDuration == 108e-3
    
    # downsampling?
    rs.minOverscan = 0
    rs.downsample = 10
    assert rs.frameDuration == 0.96
    assert np.all(rs.scanShape == (1, 6, 160))
    assert np.all(rs.imageShape == (1, 6, 16))

    # downsampling + overscan
    rs.minOverscan = 0.01
    assert rs.frameDuration == 1.08
    assert np.all(rs.scanShape == (1, 6, 180))
    assert np.all(rs.imageShape == (1, 6, 16))
    
    # make sure that all offsets and strides are integer multiples of downsampling
    rs.minOverscan = 0.025
    rs.startTime = 0
    ds = rs.downsample
    assert ds > 1
    assert isMultiple(rs.osLen, ds)
    assert isMultiple(rs.scanShape[2], ds)
    assert isMultiple(rs.scanStride[1], ds)
    assert isMultiple(rs.scanStride[0], ds)
    assert isMultiple(rs.scanOffset, ds)
    assert isMultiple(rs.activeShape[2], ds)
    assert isMultiple(rs.activeStride[1], ds)
    assert isMultiple(rs.activeStride[0], ds)
    assert isMultiple(rs.activeOffset, ds)
    
    # make sure that the complete state does not depend on the order
    # in which parameters are accessed
    rs.bidirectional = True
    rs.interFrameDuration = 0
    rs.numFrames = 1
    np.random.seed(1245)
    unfixed = [n for n in rs._vars if rs._vars[n][2] is None]
    rs.solve()  # initialize all
    state = dict([(n,v[0]) for n,v in rs.saveState().items()])
    for i in range(30):
        #print "================== reset ===================="
        rs.resetUnfixed()
        np.random.shuffle(unfixed)
        for n in unfixed:
            v = getattr(rs, n)
            #print n, v, state[n]
        assertState(rs, state)
    
    # test save/restore
    rs.solve()
    state = rs.saveState()
    rs.reset()
    rs.restoreState(state)
    state = dict([(n,v[0]) for n,v in state.items()])
    assertState(rs, state)

def test_RectScanParameter():
    p = RectScanParameter()
    p.system.defaultState['sampleRate'][0] = 1e4
    p.system.defaultState['sampleRate'][2] = 'fixed'
    p.system.defaultState['downsample'][0] = 1
    p.system.defaultState['downsample'][2] = 'fixed'
    p.system.defaultState['p0'][0] = np.array([0,0])
    p.system.defaultState['p0'][2] = 'fixed'
    p.system.defaultState['p1'][0] = np.array([150e-6,0])
    p.system.defaultState['p1'][2] = 'fixed'
    p.system.defaultState['p2'][0] = np.array([0,-100e-6])
    p.system.defaultState['p2'][2] = 'fixed'
    p.system.defaultState['numFrames'][0] = 1
    p.updateSystem()
    w = ParameterTree()
    w.setParameters(p)
    w.show()
    return p, w
    
if __name__ == '__main__':
    import user
    test_RectScan()
    p, w = test_RectScanParameter()
    w.resize(300, 700)
    plt = pg.plot()
    def update():
        global p, plt
        arr = np.zeros((100000,2))
        plt.clear()
        try:
            p.system.writeArray(arr)
            plt.plot(arr[:,0], arr[:,1])
            r = p.system.numCols - 1
            e = p.system.numCols * p.system.numRows - 1
            x = [arr[0,0], arr[r,0], arr[e,0]]
            y = [arr[0,1], arr[r,1], arr[e,1]]
            b = list(map(pg.mkBrush, ['g', 'b', 'r']))
            plt.plot(x, y, pen=None, symbol='o', symbolBrush=b)
            plt.plotItem.setAspectLocked()
            plt.autoRange()
            plt.plotItem.setAspectLocked(False)
            
        except RuntimeError:
            pass
    p.sigTreeStateChanged.connect(update)

