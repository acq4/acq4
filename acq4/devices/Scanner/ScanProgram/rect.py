# -*- coding: utf8 -*-

import weakref
import numpy as np
from collections import OrderedDict
import acq4.pyqtgraph as pg
from acq4.pyqtgraph import QtGui, QtCore
import acq4.pyqtgraph.parametertree.parameterTypes as pTypes
from acq4.pyqtgraph.parametertree import Parameter, ParameterTree, ParameterItem, registerParameterType
from .component import ScanProgramComponent

class RectScanComponent(ScanProgramComponent):
    """
    Does a raster scan of a rectangular area.
    """
    name = 'rect'
    
    def __init__(self, cmd=None, scanProgram=None):
        ScanProgramComponent.__init__(self, cmd, scanProgram)
        self.ctrl = RectScanControl(self)
        
    def setSampleRate(self, rate, downsample):
        ScanProgramComponent.setSampleRate(rate, downsample)
        self.ctrl.update()

    def ctrlParameter(self):
        """
        The Parameter (see acq4.pyqtgraph.parametertree) set used to allow the 
        user to define this component.        
        """
        return self.ctrl.parameters()
    
    def graphicsItems(self):
        """
        A list of GraphicsItems to be displayed in a camera module or image
        analysis module. These show the location and shape of the scan 
        component, and optionally offer user interactivity to define the shape.
        """
        return self.ctrl.getGraphicsItems()

    def generateTask(self):
        return self.ctrl.generateTask()

    @classmethod
    def generateVoltageArray(cls, array, dt, dev, cmd, startInd, stopInd):
        pts = cmd['points']
        # print 'cmd: ', cmd
        SUF = ScannerUtility()
        SUF.setScannerDev(dev)
        SUF.setLaserDev(cmd['laser'])
        
        width  = (pts[1] -pts[0]).length() # width is x in M
        height = (pts[2]- pts[0]).length() # heigh in M
        rect = [pts[0][0], pts[0][1], width, height]
        overScanPct = cmd['overScan']
        SUF.setRectRoi(pts)
        SUF.setOverScan(overScanPct)
        SUF.setDownSample(1)
        SUF.setBidirectional(True)
        pixelSize = cmd['pixelSize']
        # recalulate pixelSize based on:
        # number of scans (reps) and total duration
        nscans = cmd['nScans']
        dur = cmd['duration']#  - cmd['startTime'] # time for nscans
        durPerScan = dur/nscans # time for one scan
        SUF.setPixelSize(cmd['pixelSize']) # pixelSize/np.sqrt(pixsf)) # adjust the pixel size
        SUF.setSampleRate(1./dt) # actually this is not used... 
        (x,y) = SUF.designRectScan() # makes one rectangle
        effScanTime = (SUF.getPixelsPerRow()/pixelSize)*(height/pixelSize)*dt # time it actually takes for one scan 
        pixsf = durPerScan/effScanTime # correction for pixel size based pm to,e

        cmd['imageSize'] = (SUF.getPixelsPerRow(), SUF.getnPointsY())

        printParameters = False
        if printParameters:
            print 'scans: ', nscans
            print 'width: ', width
            print 'points in width: ', width/pixelSize
            print 'dt: ', dt
            print 'points in a scan: ', (width/pixelSize)*(height/pixelSize)
            print 'effective scan time: ', effScanTime
            print 'pixsf: ', pixsf
            print 'original: ', pixelSize
            print 'new pix size: ', pixelSize*pixsf
        
        n = SUF.getnPointsY() # get number of rows
        m = SUF.getPixelsPerRow() # get nnumber of points per row

        ## Build array with scanner voltages for rect repeated once per scan
        for i in range(cmd['nScans']):
            thisStart = startInd+i*n*m
            array[0, thisStart:thisStart + len(x)] = x
            array[1, thisStart:thisStart + len(y)] = y
        array[0, startInd+n*m*cmd['nScans']:stopInd] = array[0, startInd+n*m*cmd['nScans'] -1] # fill in any unused sample on this scan section
        array[1, startInd+n*m*cmd['nScans']:stopInd] = array[1, startInd+n*m*cmd['nScans'] -1]
        lastPos = (x[-1], y[-1])
            
            
        # A side-effect modification of the 'command' dict so that analysis can access
        # this information later
        cmd['scanParameters'] = SUF.packScannerParams()
        cmd['scanInfo'] = SUF.getScanInfo()

        return stopInd

class RectScanROI(pg.ROI):
    def __init__(self, size, pos):
        pg.ROI.__init__(self, size=size, pos=pos)
        self.addScaleHandle([1,1], [0.5, 0.5])
        self.addRotateHandle([0,0], [0.5, 0.5])
        self.overScan = 0

    def setOverScan(self, os):
        self.overScan = os
        self.prepareGeometryChange()
        self.update()

    def boundingRect(self):
        br = pg.ROI.boundingRect(self)
        os = br.width() * 0.5 * self.overScan/100.
        return br.adjusted(-os, 0, os, 0)

    def paint(self, p, *args):
        p.setPen(pg.mkPen(0.3))
        p.drawRect(self.boundingRect())
        pg.ROI.paint(self, p, *args)




class RectScanControl(QtCore.QObject):
    
    sigStateChanged = QtCore.Signal(object)
    
    def __init__(self, component):
        QtCore.QObject.__init__(self)
        ### These need to be initialized before the ROI is initialized because they are included in stateCopy(), which is called by ROI initialization.
        self.name = component.name
        self.blockUpdate = False
        self.component = weakref.ref(component)
        
        self.params = pTypes.SimpleParameter(name=self.name, type='bool', value=True, removable=True, renamable=True, children=[
            dict(name='width', readonly=True, type='float', value=2e-5, suffix='m', siPrefix=True, bounds=[1e-6, None], step=1e-6),
            dict(name='height', readonly=True, type='float', value=1e-5, suffix='m', siPrefix=True, bounds=[1e-6, None], step=1e-6),
            dict(name='overScan', type='float', value=70., suffix='%', siPrefix=False, bounds=[0, 200.], step = 1),
            dict(name='pixelSize', type='float', value=4e-7, suffix='m', siPrefix=True, bounds=[2e-7, None], step=2e-7),
            dict(name='startTime', type='float', value=1e-2, suffix='s', siPrefix=True, bounds=[0., None], step=1e-2),
            dict(name='nScans', type='int', value=10, bounds=[1, None]),
            dict(name='duration', type='float', value=5e-1, suffix='s', siPrefix=True, bounds=[0., None], step=1e-2),
            dict(name='imageSize', type='str', readonly=True),
            dict(name='scanSpeed', type='float', readonly=True, suffix='m/ms', siPrefix=True), 
            dict(name='frameExp', title=u'frame exposure/μm²', type='float', readonly=True, suffix='s', siPrefix=True), 
            dict(name='totalExp', title=u'total exposure/μm²', type='float', readonly=True, suffix='s', siPrefix=True),
        ])
        self.params.component = self.component
        
        self.roi = RectScanROI(size=[self.params['width'], self.params['height']], pos=[0.0, 0.0])
        self.roi.setOverScan(self.params['overScan'])

        self.params.sigTreeStateChanged.connect(self.paramsChanged)
        self.roi.sigRegionChangeFinished.connect(self.roiChanged)
        
    def getGraphicsItems(self):
        return [self.roi]

    def isActive(self):
        return self.params.value()
 
    def setVisible(self, vis):
        if vis:
            self.roi.setOpacity(1.0)  ## have to hide this way since we still want the children to be visible
            for h in self.roi.handles:
                h['item'].setOpacity(1.0)
        else:
            self.roi.setOpacity(0.0)
            for h in self.roi.handles:
                h['item'].setOpacity(0.0)
                
    def parameters(self):
        return self.params

    def paramsChanged(self, param, changes):
        self.update(changed=[changes[0][0].name()])
        
    def update(self, changed=()):
        # Update all parameters to ensure consistency. 
        # *changed* may be a list of parameter names that have changed;
        # these will be kept constant during the update, if possible.
        
        if self.blockUpdate:
            return

        try:
            self.blockUpdate = True

            if 'overScan' in changed:
                self.roi.setOverScan(self.params['overScan'])

            self.setVisible(self.params.value())
            
            # TODO: this should be calculated by the same code that is used to generate the voltage array
            # (as currently written, it is unlikely to match the actual output exactly)

            w = self.params['width'] * (1.0 + self.params['overScan']/100.)
            h = self.params['height']
            sampleRate = float(self.component().sampleRate)
            downsample = self.component().downsample
            
            if 'duration' in changed:
                # Set pixelSize to match duration
                duration = self.params['duration']
                maxSamples = int(duration * sampleRate)
                maxPixels = maxSamples / downsample
                ar = w / h
                pxHeight = int((maxPixels / ar)**0.5)
                pxWidth = int(ar * pxHeight)
                imgSize = (pxWidth, pxHeight)
                pxSize = w / (pxWidth-1)
                self.params['pixelSize'] = pxSize
            else:
                # set duration to match pixelSize
                pxSize = self.params['pixelSize']
                imgSize = (int(w / pxSize) + 1, int(h / pxSize) + 1) 
                samples = imgSize[0] * imgSize[1] * downsample
                duration = samples / sampleRate
                self.params['duration'] = duration

            # Set read-only parameters:

            self.params['imageSize'] = str(imgSize)
            
            speed = w / (imgSize[0] * downsample / sampleRate)
            self.params['scanSpeed'] = speed * 1e-3

            samplesPerUm2 = 1e-12 * downsample / pxSize**2
            frameExp = samplesPerUm2 / sampleRate
            totalExp = frameExp * self.params['nScans']
            self.params['frameExp'] = frameExp
            self.params['totalExp'] = totalExp

        finally:
            self.blockUpdate = False

    
    def roiChanged(self):
        """ read the ROI rectangle width and height and repost
        in the parameter tree """
        state = self.roi.getState()
        w, h = state['size']
        self.params['width'] = w
        self.params['height'] = h
        
    def generateTask(self):
        state = self.roi.getState()
        w, h = state['size']
        p0 = pg.Point(0,0)
        p1 = pg.Point(w,0)
        p2 = pg.Point(0, h)
        points = [p0, p1, p2]
        points = [pg.Point(self.roi.mapToView(p)) for p in points] # convert to view points (as needed for scanner)
        return {'type': self.name, 'active': self.isActive(), 'points': points, 'startTime': self.params['startTime'], 
                'endTime': self.params['duration']+self.params['startTime'], 'duration': self.params['duration'],
                'nScans': self.params['nScans'],
                'pixelSize': self.params['pixelSize'], 'overScan': self.params['overScan'],
                }
        





class RectScan(object):
    """
    Manages the system of equations necessary to define a rectangular scanning area. 

    * Input parameters may be specified in any combination (as long as all DOF are fixed). 
    * Parameters may be individually locked 
    * Able to save and reload state information to disk

    Input parameters:

        * 3 corners of the scan area:

            p0______p1
            |
            |
            p2 

            * height / width
            * overscan (measured in us)

        * Horizontal / vertical sample density
        * Sample rate
        * Downsampling
        * Pixel size
        * Bidirectional
        * Total duration

    Output parameters:

        * scan offset, shape, strides  (includes overscan, ignores downsampling)
        * start position, delta vectors
        * bidirectionality
        * position array, voltage array, laser mask array

        * exposure time per um^2
        * image offset, shape, strides  (excludes overscan, includes downsampling)
        * image transform

    Theory:
    
        * There are 6 degrees of freedom that determine which array index 
          represents which point: scan shape (w, h), scan strides (x, y),
          bidirectionality, and overscan. With these variables one can 
          reconstruct an image from a PMT signal. 
        * There are 6 degrees of freedom that determine the placement of the 
          scan rectangle: p0(x,y), width, height, and angle. With these 
          variables, one can place the image into the global coordinate system.
          (For coding simplicity, it may be easier to consider a 6DOF 
          parallelogram instead, defined by p0,p1,p2)
        * There are 2 degrees of freedom affecting timing: sample rate and 
          downsampling. With these, the start/stop times, exposure times, etc.
          can be determined.
        * Various constraints may be applied:
            * fixed pixel shape (usually square)
            * maximum / fixed exposure
            * maximum / fixed duration
            * maximum / fixed pixel size
    """
    def __init__(self):
        self.reset()
        
        #self._dof = {
            #'p0': 2, 'p1': 2, 'p2': 2, 
            #'density': 2, 'pixelSize': 2,
            #'scanOffset': 2, 'scanShape': 2, 'scanStrides': 2,
            #'sampleVectors': 2,
            #'imageOffset': 2, 'imageShape': 2, 'imageStrides': 2,
            #}
    def reset(self):
        
        # name: [value, type, constraint, allowed_constraints]
        #       *value* may always be None if it has not been specified yet.
        #       *type* may be float, int, bool, np.ndarray
        #       *constraint* may be None, single value, or (min, max) 
        #       *allowed_constraints* is a string composed of (n)one, (f)ixed, and (r)ange. 
        arr = np.ndarray
        self._vars = OrderedDict([
            ('p0', [None, arr, None, 'f']),
            ('p1', [None, arr, None, 'f']),
            ('p2', [None, arr, None, 'f']),
            ('width', [None, float, None, 'n']),
            ('height', [None, float, None, 'n']),
            #('angle', [None, float, None, 'n']),
            ('overscan', [None, float, None, 'f']),
            ('osp0', [None, arr, None, 'n']),
            ('osp1', [None, arr, None, 'n']),
            ('oswidth', [None, float, None, 'n']),
            ('pixelWidth', [None, float, None, 'nfr']),
            ('pixelHeight', [None, float, None, 'nfr']),
            ('pixelAspectRatio', [None, float, None, 'nf']),
            ('bidirectional', [None, bool, None, 'f']),
            ('sampleRate', [None, float, None, 'f']),
            ('downsample', [None, int, None, 'f']),
            ('duration', [None, float, None, 'nfr']),
            ('scanOffset', [None, int, None, 'n']),
            ('scanShape', [None, arr, None, 'n']),
            ('scanStrides', [None, arr, None, 'n']),
            ('sampleVectors', [None, arr, None, 'n']),
            ('exposurePerUm2', [None, float, None, 'nfr']),
            ('scanSpeed', [None, float, None, 'nfr']),
            ('imageOffset', [None, int, None, 'n']),
            ('imageShape', [None, arr, None, 'n']),
            ('imageStrides', [None, arr, None, 'n']),
            ])
        
    def get(self, name):
        return self._vars[name][0]
    
    def set(self, name, value=None, constraint=True):
        """
        Set a variable *name* to *value*.
        
        If *value* is None, then the value is left to be determined in the 
        future. At any time, the value may be re-assigned arbitrarily unless
        a constraint is given.
        
        If *constraint* is True (the default), then supplying a value that 
        violates a previously specified constraint will raise an exception.
        
        If *constraint* is 'fixed', then the value is set (if provided) and
        the variable will not be updated automatically in the future.

        If *constraint* is a tuple, then the value is constrained to be within the 
        given (min, max). Either constraint may be None to disable 
        it. In some cases, a constraint cannot be satisfied automatically,
        and the user will be forced to resolve the constraint manually.
        
        If *constraint* is None, then any constraints are removed for the variable.
        """
        var = self._vars[name]
        if constraint is None:
            if 'n' not in var[3]:
                raise TypeError("Empty constraints not allowed for '%s'" % name)
            var[2] = constraint
        if constraint == 'fixed':
            if 'f' not in var[3]:
                raise TypeError("Fixed constraints not allowed for '%s'" % name)
            var[2] = constraint
        elif isinstance(constraint, tuple):
            if 'r' not in var[3]:
                raise TypeError("Range constraints not allowed for '%s'" % name)
            assert len(constraint) == 2
            var[2] = constraint
        elif constraint is not True:
            raise TypeError("constraint must be None, True, 'fixed', or tuple. (got %s)" % constraint)
        
        if value is not None:
            # type checking / massaging
            if var[1] is np.ndarray:
                value = np.array(value)
                
            # constraint checks
            if constraint is True and not self.check_constraint(name, value):
                raise ValueError("Setting %s = %s violates constraint %s" % (name, value, var[2]))
            
            # invalidate other dependent values
            if var[0] is not None:
                # todo: we can make this more clever..(and might need to) 
                # we just know that a value of None cannot have dependencies
                # (because if anyone else had asked for this value, it wouldn't be 
                # None anymore)
                self.resetUnfixed()
                
            var[0] = value
    
    def check_constraint(self, name, value):
        c = self._vars[name][2]
        if c is None or value is None:
            return True
        if isinstance(c, tuple):
            return ((c[0] is None or c[0] <= value) and
                    (c[1] is None or c[1] >= value))
        else:
            return value == c
    
    def saveState(self):
        state = OrderedDict
        for name, var in self._values.items():
            state[name] = (var[0], var[2])
        return state
    
    def restoreState(self, state):
        for name, var in state.items():
            self.set(name, var[0], var[2])
    
    def resetUnfixed(self):
        """
        For any variable that does not have a fixed value, reset
        its value to None.
        """
        for var in self._vars.values():
            if var[2] != 'fixed':
                var[0] = None
    
    @property
    def p0(self): return self.get('p0')
    @p0.setter
    def p0(self, pt): self.set('p0', pt, 'fixed')
            
    @property
    def p1(self): return self.get('p1')
    @p1.setter
    def p1(self, pt): self.set('p1', pt, 'fixed')
    
    @property
    def p2(self): return self.get('p2')
    @p2.setter
    def p2(self, pt): self.set('p2', pt, 'fixed')
            
    @property
    def width(self):
        """
        Distance from the first point in the scan to the last point, excluding
        any overscan samples.
        """
        w = self.get('width')
        if w is None:
            w = np.linalg.norm(self.p1 - self.p0)
            self.set('width', w)
        return w
    #@width.setter
    #def width(self, w): self.set('width', w, 'fixed')
            
    @property
    def height(self):
        """
        Distance from the first scanline to the last scanline.
        """
        h = self.get('height')
        if h is None:
            h = np.linalg.norm(self.p2 - self.p0)
            self.set('height', h)
        return h
    #@height.setter
    #def height(self, h): self.set('height', h, 'fixed')
            
    #@property
    #def angle(self): return self.get('angle')
    #@angle.setter
    #def angle(self, a): self.set('angle', a, 'fixed')
            
    @property
    def overscan(self): return self.get('overscan')
    @overscan.setter
    def overscan(self, o): self.set('overscan', o, 'fixed')
            
    @property
    def osp0(self): 
        """
        Origin (top-left corner) of the scan rectangle _including_ overscan.
        This is the actual starting point for the laser.
        """
        pt = self.get('osp0')
        if pt is None:
            speed = self.scanSpeed
            os = self.overscan
            osDist = speed * os
            
        return pt
    
    @property
    def osp1(self):
        """
        End of the first raster line (top-right corner) _including_ overscan.
        """
        return self.get('osp1')
    
    @property
    def oswidth(self):
        """
        Distance from the first point in the scan to the last point, including
        overscan samples.
        """
        w = self.get('oswidth')
        if w is None:
            w = np.linalg.norm(self.osp1 - self.osp0)
            self.set('oswidth', w)
        return w
    
    @property
    def pixelWidth(self): return self.get('pixelWidth')
    @pixelWidth.setter
    def pixelWidth(self, w): # nfr 
        self.set('pixelWidth', w, 'fixed')
            
    @property
    def pixelHeight(self): return self.get('pixelHeight')
    @pixelHeight.setter
    def pixelHeight(self, h): # nfr 
        self.set('pixelHeight', h, 'fixed')
    
    @property
    def pixelAspectRatio(self): return self.get('pixelAspectRatio')
    @pixelAspectRatio.setter
    def pixelAspectRatio(self, ar): # nf
        self.set('pixelAspectRatio', ar, 'fixed')
    
    @property
    def bidirectional(self): return self.get('bidirectional')
    @bidirectional.setter
    def bidirectional(self, bd): self.set('bidirectional', bd, 'fixed')
    
    @property
    def sampleRate(self): return self.get('sampleRate')
    @sampleRate.setter
    def sampleRate(self, sr): self.set('sampleRate', sr, 'fixed')
            
    @property
    def downsample(self): return self.get('downsample')
    @downsample.setter
    def downsample(self, ds): # nfr
        self.set('downsample', ds, 'fixed')

    @property
    def duration(self):
        # Note: duration calculation cannot depend on osp0, osp1, oswidth.
        # must be calculated from scan region excluding overscan.
        # (and then we can directly add 2*overscan*nlines)
        return self.get('duration')
    @duration.setter
    def duration(self, d): self.set('duration', d, 'fixed')
    
    @property
    def scanSpeed(self): 
        # Note: scanSpeed calculation cannot depend on osp0, osp1, oswidth.
        # must be calculated from scan region excluding overscan.
        return self.get('scanSpeed')
    @scanSpeed.setter
    def scanSpeed(self, d): self.set('scanSpeed', d, 'fixed')
    
    

class RectScanVideo:
    """
    Manages the system of equations necessary to define a sequence of rectangular scans.
    (note this appears to be a general-case loop)

    Input parameters:

        * # of frames
        * Frame exposure duration
        * Inter-frame duration
        * Frame rate
        * Total duration

    Output parameters:

        * total exposure time per um^2
        * position array, voltage array, laser mask array
        * scan offset, shape, strides
        * video offset, shape, strides
        * image transform


    """



class ScannerUtility:
    """
    1. Decombing routine for scanned images. 
    2. Compute scan voltages for a recangular region
    adding an overscan region.
    3. Create an image with overscan removed.
    """
    def __init__(self):
        self.scannerDev = None
        self.laserDev = None
        self.rectRoi = [pg.Point(0., 0.), pg.Point(0., 1e-4), pg.Point(1e-4, 0.)]
        self.pixelSize = 1e-6
        self.sampleRate = 100000. 
        self.downSample = 5
        self.overScan = 0.
        self.bidirectional = True
        
        # define set/get routines to control the parameters
    def setScannerDev(self, dev):
        self.scannerDev = dev
    
    def getScannerDev(self):
        return(self.scannerDev)
    
    def setLaserDev(self, dev):
        self.laserDev = dev
    
    def getLaserDev(self):
        return(self.laserDev)
    
    def setRectRoi(self, rect):
        if len(rect) == 3: # must specify all coordinates
            self.rectRoi = rect
        else:
            raise Exception("Scanner Utility: setRectRoi requires array of 3 values")
    
    def getRectRoi(self):
        return(self.rectRoi)
    
    def setPixelSize(self, size):
        self.pixelSize = size
        
    def getPixelSize(self):
        return(self.pixelSize)
    
    def setSampleRate(self, sampleRate):
        if sampleRate < 0:
            raise Exception("Scanner Utility: setSampleRate requires positive rate")
        self.sampleRate = sampleRate
    
    def getSampleRate(self):
        return(self.sampleRate)
    
    def setDownSample(self, downsample):
        if downsample < 1 or downsample > 100:
            raise Exception("Scanner Utility: setDownSample requires positive downsample number")
        self.downSample = downsample
        
    def getDownSample(self):
        return(self.downSample)

    def setOverScan(self, overscan):
        if overscan < 0 or overscan > 200:
            raise Exception("ScannerUtility: setOverScan requires number >0 and < 200")
        self.overScan = overscan
        
    def getOverScan(self):
        return self.overScan
    
    def setBidirectional(self, bidirection):
        self.bidirectional = bidirection
        
    def getBidirectional(self):
        return(self.bidirectional)

    def packScannerParams(self):
        """
        put the current scanner parameters into a dictionary with their names
        and return the value
        """
        scannerParams = {'scannerDev': self.scannerDev, 'laserDev': self.laserDev,
                         'rectRoi': self.rectRoi, 'pixelSize': self.pixelSize, 
                         'sampleRate': self.sampleRate, 'downSample': self.downSample,
                         'overScan': self.overScan, 'bidirectional': self.bidirectional}
        return scannerParams

    def setScannerParameters(self, sp):
        """
        set the paramereters from the dictionary retrieved by packScannerParameters
        """
        self.scannerDev = sp['scannerDev']
        self.laserDev = sp['laserDev']
        self.rectRoi = sp['rectRoi']
        self.pixelSize = sp['pixelSize']
        self.sampleRate = sp['sampleRate']
        self.downSample = sp['downSample']
        self.overScan = sp['overScan']
        self.bidirectional = sp['bidirectional']     
        return # just in case we want it as well...

    def getScanInfo(self):
        """
        convenience function - get several scan parameters after the scan
        as a dictionary
        This routine is used, for example in the Imaging (task) module to retrieve
        the scan parameters to reconstruct the image.
        """
        return {'pixelsPerRow': self.pixelsPerRow, 'overScanPixels': self.overScanPixels,
                'nPointsY': self.nPointsY, 'nPointsX': self.nPointsX,
                'samples': self.samples}
    
    def setScanInfo(self, sp):
        """
        convenience function - gst several scan parameters after the scan
        as a dictionary, if the form returned by getScanInfo
        This routine is used, for example in the Imaging (task) module to retrieve
        the scan parameters to reconstruct the image.
        """
        self.pixelsPerRow = sp['pixelsPerRow']
        self.overScanPixels  = sp['overScanPixels']
        self.nPointsY = sp['nPointsY']
        self.nPointsX = sp['nPointsX']       
        self.samples = sp['samples']
        
        
    def checkScannerParams(self):
        sp = self.packScannerParams()
        for p in sp.keys():
            if sp[p] is None:
                raise Exception("ScannerUtility: parameter %s is not set" % p)
        
    def packArgs(self, **kwargs):
        sp = self.packScannerParams() # get the current parameters
        for k, v in kwargs.iteritems():
            if k in sp.keys():
                sp[k] = v
        # now update the instance-specific values from the dictionary
        self.scannerDev = sp['scannerDev']
        self.laserDev = sp['laserDev']
        self.rectRoi = sp['rectRoi']
        self.pixelSize = sp['pixelSize']
        self.sampleRate = sp['sampleRate']
        self.downSample = sp['downSample']
        self.overScan = sp['overScan']
        self.bidirectional = sp['bidirectional']     
        return sp # just in case we want it as well...
    

        
    def designRectScan(self, **kwargs):
        """
        compute the scan voltages for the scanner, corrected by the laser calibration,
        to scan the rectangle specified in standard coordinates, with the rate,
        downsample, overscan and bidirectional flags as set. 
        Pulled from Imager.py, 11/21/2013.
        """
        prof = pg.debug.Profiler(disabled=False)
        self.packArgs(**kwargs) # update any specified arguments
        self.checkScannerParams() # verify all are loaded in in range.
        printPars = True
        if 'printPars' in kwargs.keys():
            printPars = kwargs['printPars']
        
        prof()
        pts = self.rectRoi
        xPos = pts[0][0]
        yPos = pts[0][1]

        width  = (pts[1] -pts[0]).length() # width is x in M
        height = (pts[2]- pts[0]).length() # heigh in M
        self.nPointsX = int(width/self.pixelSize)
        self.nPointsY = int(height/self.pixelSize)
        xScan = np.linspace(0., width, self.nPointsX)
        xScan += xPos
        #print 'design: width: ', width
        #print 'design: height: ', height
        #print 'overscan: ', self.overScan
        
        
        overScanWidth = width*self.overScan/100.
        self.overScanPixels = int((self.nPointsX / 2.) * (self.overScan/100.))
        
        self.pixelsPerRow = self.nPointsX + 2 * self.overScanPixels  ## make sure width is increased by an even number.
        samplesPerRow = self.pixelsPerRow * self.downSample
        self.samples = samplesPerRow * self.nPointsY
        if printPars:
            print 'rectRoi: ', self.rectRoi
            print 'pixelsPer Row: ', self.pixelsPerRow
            print 'nPointsX: ', self.nPointsX
            print 'nPointsY: ', self.nPointsY
            print 'overScan: ', self.overScan
            print 'overScanPixels: ', self.overScanPixels
            print 'downSample: ', self.downSample
            print 'overscanWidth: ', overScanWidth
            print 'samplesperrow: ', samplesPerRow
            print 'xPos, yPos: ', xPos, yPos
        useOldCode = False
        prof()
        if useOldCode:
            if not self.bidirectional:
                saw1 = np.linspace(0., width+overScanWidth, num=samplesPerRow)
                saw1 += xPos-overScanWidth/2.0
                xSaw = np.tile(saw1, (1, self.nPointsY))[0,:]
            else:
                saw1 = np.linspace(0., width+overScanWidth, num=samplesPerRow)
                saw1 += xPos-overScanWidth/2.0
                rows = [saw1, saw1[::-1]] * int(self.nPointsY/2)
            if len(rows) < self.nPointsY:
                rows.append(saw1)
            xSaw = np.concatenate(rows, axis=0)

            yvals = np.linspace(0., width, num=self.nPointsY)
            yvals += yPos
            yScan = np.empty(self.samples)
            for y in range(self.nPointsY):
                yScan[y*samplesPerRow:(y+1)*samplesPerRow] = yvals[y]
                # now translate this scan into scanner voltage coordinates...
            x, y = self.scannerDev.mapToScanner(xSaw, yScan, self.laserDev)
            xSaw = []
            yScan = []
            print 'Old code: x,y min max: ', np.min(x), np.min(y), ' max: ', np.max(x), np.max(y)
            print 'x, y shape: ', x.shape, y.shape

        
        
        ###----------------------------------------------------------------
        ## generate scan array using potentially rotated rectangular ROI
        ## with extended overscan regions.
        
        else:
            ny = self.nPointsY # get number of rows
            nx = samplesPerRow # get number of points per row, including overscan        
            dx = (pts[1]-pts[0])/(self.nPointsX*self.downSample) # (nx-1)
            dy = (pts[2]-pts[0])/self.nPointsY # (ny-1)            
            prof()
            r = np.mgrid[0:ny, 0:nx]
            r = np.roll(r, nx*ny) # swapping order of first axis , also could be r = r[::-1]
            prof()
            if self.bidirectional:
                r[0, 1::2] = r[0, 1::2, ::-1]
            prof()
            # convert image coordinates to physical coordinates to pass to scanner.
            v = np.array([[dx[0], dy[0]], [dx[1], dy[1]]]).reshape(2,2,1,1) 
            prof()
            q = (v*r).sum(axis=1)
            prof()
            trueOrigin = pts[0]-dx*self.overScanPixels*self.downSample
            #print 'trueOrigin: ', trueOrigin
            #print 'pts[0]: ', pts[0]
            q += np.array(trueOrigin).reshape(2,1,1)
            prof()
            x, y = self.scannerDev.mapToScanner(q[0].flatten(), q[1].flatten(), self.laserDev)
            prof()
        #----------------------------------------------------
        prof()
        return (x, y)
    
    def getPixelsPerRow(self):
        return self.pixelsPerRow
    
    def getnPointsY(self):
        return self.nPointsY

    def getOverScanPixels(self):
        print 'getOverScan Pixels has: ', self.overScanPixels
        return self.overScanPixels

    def getSamples(self):
        return self.samples
    
    def getScanXYSize(self):
        # return the size of the data array that the scan will fill
        # as a tuple
        return (self.pixelsPerRow, self.nPointsY)

    def adjustBidirectional(self, imgData, decombAutoFlag, decombShift):
        """
        If the data is from a bidirectional scan, do the decombing with the 
        fixed shift value.
        Optionally, compute the auto decomb value needed to optimize the image.
        Units of the shift coming in here are in seconds (not pixels)
        """
        print 'bidirectional: ', self.bidirectional
        if self.bidirectional:
            for y in range(1, self.nPointsY, 2): # reverse direction for alternate rows
                imgData[:,y] = imgData[::-1,y]
            print 'decomb auto: ', decombAutoFlag
            print 'self samplerate: ', self.sampleRate
            if decombAutoFlag:
                imgData, shift = self.decomb(imgData, minShift=0., maxShift=400e-6*self.sampleRate)  ## correct for mirror lag up to 200us
                decombShift = shift * self.sampleRate
            else:
                print 'shift, samplerate: ', decombShift, self.sampleRate
                imgData, shift = self.decomb(imgData, auto=False, shift=decombShift*self.sampleRate)
            print 'decombshift (microseconds): ', shift / self.sampleRate
        return imgData, shift / self.sampleRate
        

    def makeOverscanBlanking(self, imgData):
        """
        return an array of 1's and 0's where
        the data is 0 in the overscan space, and 1 in the 
        image space
        """
        blankData = np.zeros(imgData.shape)
        osp = self.getOverScanPixels()
        if osp > 0:
            blankData[:,osp:-osp] = 1
        else:
            blankData[:] = 1
        return blankData
    
    def removeOverscan(self, imgData, overscan = None):
        """
        Trim the overscan from the image array
        """
        print 'removeOverscan: '
        if overscan is not None:
            osp = overscan
        else:
            osp = self.getOverScanPixels()
        if osp > 0:
            imgData = imgData[osp:-osp]
        return imgData
    
    def decomb(self, img, minShift=0., maxShift=100., auto=True, shift=0):
        ## split image into fields
        # units of the shift coming in here are in pixels (integer)

        nr = 2 * (img.shape[1] // 2)
        f1 = img[:,0:nr:2]
        f2 = img[:,1:nr+1:2]
        
        ## find optimal shift
        if auto:
            bestShift = None
            bestError = None
            #errs = []
            for shift in range(int(minShift), int(maxShift)):
                f2s = f2[:-shift] if shift > 0 else f2
                err1 = np.abs((f1[shift:, 1:]-f2s[:, 1:])**2).sum()
                err2 = np.abs((f1[shift:, 1:]-f2s[:, :-1])**2).sum()
                totErr = (err1+err2) / float(f1.shape[0]-shift)
                #errs.append(totErr)
                if totErr < bestError or bestError is None:
                    bestError = totErr
                    bestShift = shift
            #pg.plot(errs)
            print 'decomb: auto is true, bestshift = ', bestShift
        else:
            bestShift = shift
        if bestShift is None: # nothing...
            return img, 0.
        ## reconstruct from shifted fields
        leftShift = bestShift // 2
        rightShift = int(leftShift + (bestShift % 2))
        print '360: left, right: ', leftShift, rightShift
        if rightShift < 1:
            return img, 0
        decombed = np.zeros(img.shape, img.dtype)
        if leftShift > 0:
            decombed[:-leftShift, ::2] = img[leftShift:, ::2]
        else:
            decombed[:, ::2] = img[:, ::2]
        print '368: left, right: ', leftShift, rightShift
        decombed[rightShift:, 1::2] = img[:-rightShift, 1::2]
        return decombed, bestShift
    

