# -*- coding: utf8 -*-
from __future__ import print_function

from __future__ import division
import weakref
import numpy as np
from collections import OrderedDict

import acq4.pyqtgraph as pg
from acq4.util import Qt
import acq4.pyqtgraph.parametertree.parameterTypes as pTypes
from acq4.pyqtgraph.parametertree import Parameter, ParameterTree, ParameterItem, registerParameterType, ParameterSystem, SystemSolver
from .component import ScanProgramComponent


class RectScanComponent(ScanProgramComponent):
    """
    Does a raster scan of a rectangular area.
    """
    type = 'rect'
    
    def __init__(self, scanProgram=None):
        ScanProgramComponent.__init__(self, scanProgram)
        self.ctrl = RectScanControl(self)
        
    def samplingChanged(self):
        self.ctrl.update()

    def ctrlParameter(self):
        """
        The Parameter set (see acq4.pyqtgraph.parametertree) that allows the 
        user to configure this component.
        """
        return self.ctrl.parameters()
    
    def graphicsItems(self):
        """
        A list of GraphicsItems to be displayed in a camera module or image
        analysis module. These show the location and shape of the scan 
        component, and optionally offer user interactivity to define the shape.
        """
        return self.ctrl.getGraphicsItems()

    def generateVoltageArray(self, array):
        rs = self.ctrl.params.system
        rs.writeArray(array, self.mapToScanner)
        return rs.scanOffset, rs.scanOffset + rs.scanStride[0]

    def generatePositionArray(self, array):
        rs = self.ctrl.params.system
        rs.writeArray(array)
        return rs.scanOffset, rs.scanOffset + rs.scanStride[0]
        
    def scanMask(self):
        mask = np.zeros(self.program().numSamples, dtype=bool)
        rs = self.ctrl.params.system
        rs.writeScanMask(mask)
        return mask
        
    def laserMask(self):
        mask = np.zeros(self.program().numSamples, dtype=bool)
        rs = self.ctrl.params.system
        rs.writeLaserMask(mask)
        return mask

    def saveState(self):
        state = ScanProgramComponent.saveState(self)
        state.update(self.ctrl.saveState())
        return state
    
    def restoreState(self, state):
        self.ctrl.restoreState(state)
        

class RectScanROI(pg.ROI):
    def __init__(self, size, pos):
        pg.ROI.__init__(self, size=size, pos=pos)
        # ROI is designed to be used on image data with the +y-axis pointing downward.
        # In the camera module, +y points upward.
        self.addScaleHandle([1,0], [0.5, 0.5])
        self.addRotateHandle([0,1], [0.5, 0.5])
        self.overScan = 0.  # distance 

    def setOverScan(self, os):
        self.overScan = os
        self.prepareGeometryChange()
        self.update()

    def boundingRect(self):
        br = pg.ROI.boundingRect(self)
        os = self.overScan
        return br.adjusted(-os, 0, os, 0)

    def paint(self, p, *args):
        p.setPen(pg.mkPen(0.3))

        #p.drawRect(self.boundingRect())  # causes artifacts at large scale
        br = self.boundingRect()
        # p.drawPolygon(Qt.QPolygonF([br.topLeft(), br.topRight(), br.bottomRight(), br.bottomLeft()]))
        p.drawLine(br.topLeft(), br.topRight())
        p.drawLine(br.bottomLeft(), br.bottomRight())
        p.drawLine(br.topLeft(), br.bottomLeft())
        p.drawLine(br.bottomRight(), br.topRight())

        pg.ROI.paint(self, p, *args)


class RectScanControl(Qt.QObject):
    
    sigStateChanged = Qt.Signal(object)
    
    def __init__(self, component):
        Qt.QObject.__init__(self)
        ### These need to be initialized before the ROI is initialized because they are included in stateCopy(), which is called by ROI initialization.
        self.blockUpdate = False
        self.component = weakref.ref(component)

        self.params = RectScanParameter()

        self.params.component = self.component
        
        self.roi = RectScanROI(size=[self.params['width'], self.params['height']], pos=[0.0, 0.0])

        self.params.sigTreeStateChanged.connect(self.paramsChanged)
        self.roi.sigRegionChangeFinished.connect(self.roiChanged)
        self.paramsChanged()
        
    def getGraphicsItems(self):
        return [self.roi]

    def isActive(self):
        return self.params.value()
 
    # def setVisible(self, vis):
    #     if vis:
    #         self.roi.setOpacity(1.0)  ## have to hide this way since we still want the children to be visible
    #         for h in self.roi.handles:
    #             h['item'].setOpacity(1.0)
    #     else:
    #         self.roi.setOpacity(0.0)
    #         for h in self.roi.handles:
    #             h['item'].setOpacity(0.0)
    def updateVisibility(self):
        v = self.params.value() and self.component().program().isVisible()
        self.roi.setVisible(v)
                
    def parameters(self):
        return self.params

    def paramsChanged(self, param=None, changes=None):
        self.update()
        
    def update(self):
        try:
            self.params.sigTreeStateChanged.disconnect(self.paramsChanged)
            reconnect = True
        except TypeError:
            reconnect = False
        try:
            self.params.system.sampleRate = self.component().program().sampleRate
            self.params.system.downsample = self.component().program().downsample
            self.params.updateSystem()
            try:
                oswidth = np.linalg.norm(self.params.system.osVector)
                self.roi.setOverScan(oswidth)
            except RuntimeError:
                self.roi.setOverScan(0)
                
            self.updateVisibility()
        
        finally:
            if reconnect:
                self.params.sigTreeStateChanged.connect(self.paramsChanged)
    
    def roiChanged(self):
        """ read the ROI rectangle width and height and repost
        in the parameter tree """
        state = self.roi.getState()
        w, h = state['size']
        # Remember: ROI origin is in bottom-left because camera module has +y pointing upward.
        self.params.system.p0 = pg.Point(self.roi.mapToView(pg.Point(0,h)))  # top-left
        self.params.system.p1 = pg.Point(self.roi.mapToView(pg.Point(w,h)))  # rop-right
        self.params.system.p2 = pg.Point(self.roi.mapToView(pg.Point(0,0)))  # bottom-left
        self.params.updateSystem()
        
    def saveState(self):
        task = {'name': self.params.name(), 
                'active': self.isActive(), 
                'roi': self.roi.saveState(),
                'scanInfo': self.params.saveState(),
                }
        return task
    
    def restoreState(self, state):
        state = state.copy()
        try:
            self.params.sigTreeStateChanged.disconnect(self.paramsChanged)            
            self.params.setName(state['name'])
            self.params.setValue(state['active'])
            self.params.restoreState(state['scanInfo'])
        finally:
            self.params.sigTreeStateChanged.connect(self.paramsChanged)

        self.roi.setState(state['roi'])


arr = np.ndarray # just to clean up defaultState below..
class RectScan(SystemSolver):
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
        * There are 5 degrees of freedom that determine the placement of the 
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
    defaultState = OrderedDict([
            # Variables needed to completely specify a single frame:
            ('p0', [None, arr, None, 'f']),  # 3 corners of the rectangle
            ('p1', [None, arr, None, 'nf']),
            ('p2', [None, arr, None, 'nf']),
            ('width', [None, float, None, 'nf']),  # width of requested scan area, excluding overscan
            ('height', [None, float, None, 'nf']),
            ('angle', [None, float, None, 'nf']),
            ('minOverscan', [None, float, None, 'f']),  # minimum overscan duration (sec)
            ('overscanDuration', [None, float, None, 'n']),  # actual overscan duration (sec)
            ('osP0', [None, arr, None, 'n']),
            ('osP1', [None, arr, None, 'n']),
            ('osP2', [None, arr, None, 'n']),
            ('osVector', [None, arr, None, 'n']),  # vector from p1 -> osP1
            ('osLen', [None, int, None, 'n']),     # number of samples in overscan region (single row, one side)
            ('fullWidth', [None, float, None, 'n']), # full width of the scan area, including overscan
            ('pixelWidth', [None, float, None, 'nfr']),
            ('pixelHeight', [None, float, None, 'nfr']),
            ('pixelAspectRatio', [None, float, None, 'nf']),
            ('bidirectional', [None, bool, None, 'f']),
            ('sampleRate', [None, float, None, 'f']),  # Sample rate of DAQ used to drive scan mirrors and record from PMT
            ('downsample', [None, int, None, 'f']),    # Downsampling used by DAQ (recorded data is downsampled by this factor)
            ('frameDuration', [None, float, None, 'nfr']),
            ('scanOffset', [None, int, None, 'n']),  # Offset, shape, and stride describe
            ('scanShape', [None, tuple, None, 'n']),   # the full scan area including overscan
            ('scanStride', [None, tuple, None, 'n']),  # and ignoring downsampling (index in samples)
            ('numRows', [None, int, None, 'n']),     # Same as scanShape[0] 
            ('numCols', [None, int, None, 'n']),     # Same as scanShape[1] 
            ('activeCols', [None, int, None, 'n']),  # Same as activeShape[1] 
            ('frameLen', [None, int, None, 'n']),
            ('frameExposure', [None, float, None, 'n']),  # scanner dwell time per square um
            ('scanSpeed', [None, float, None, 'n']),
            ('activeOffset', [None, int, None, 'n']),  # Offset, shape, and stride describe
            ('activeShape', [None, tuple, None, 'n']),   # the 'active' scan area excluding overscan
            ('activeStride', [None, tuple, None, 'n']),  # and ignoring downsampling (index in samples)
            ('imageOffset', [None, int, None, 'n']),  # Offset, shape, and stride describe 
            ('imageShape', [None, tuple, None, 'n']),   # the 'active' image area excluding overscan
            ('imageStride', [None, tuple, None, 'n']),  # and accounting for downsampling (index in pixels)
            ('imageRows', [None, int, None, 'nf']),   # alias for numRows
            ('imageCols', [None, int, None, 'nf']),   # alias for activeCols

            # variables needed to reconstruct exact image location
            ('rowVector', [None, arr, None, 'n']),    # vector pointing from one row to the next
            ('colVector', [None, arr, None, 'n']),    # vector pointing from one column (non-downsampled) to the next
            ('scanOrigin', [None, arr, None, 'n']),   # global coordinate origin of scan area  (note this is not necessarily the same as osP0)
            ('activeOrigin', [None, arr, None, 'n']), # global coordinate origin of active area  (note this is not necessarily the same as p0)

            # Variables needed to specify a sequence of frames:
            ('startTime', [None, float, None, 'f']),
            ('interFrameDuration', [None, float, None, 'f']),
            ('interFrameLen', [None, int, None, 'n']),
            ('numFrames', [None, int, None, 'f']),
            ('totalExposure', [None, float, None, 'n']),  # total scanner dwell time per square um (multiplied across all frames)
            ('totalDuration', [None, float, None, 'n']),
            ])


    ### Array handling functions:

    def writeArray(self, array, mapping=None):
        """
        Given a (N,2) array, write the rectangle scan into the 
        array regions defined by scanOffset, scanShape, and scanStride.
        
        The optional *mapping* argument provides a callable that maps from 
        global position to another coordinate system (eg. mirror voltage).
        It must accept two arrays as arguments: (x, y)
        """
        offset = self.scanOffset
        shape = self.scanShape
        nf, ny, nx = shape
        stride = self.scanStride
        
        dx = self.colVector
        dy = self.rowVector

        # Make grid of indexes
        r = np.mgrid[0:ny, 0:nx]
        if self.bidirectional:
            r[:, 1::2] = r[:, 1::2, ::-1]
            
        # Convert indexes to global coordinates.
        v = np.array([dy, dx]).reshape(2,1,1,2) 
        r = r[...,np.newaxis]
        q = (v*r).sum(axis=0)  # order is now (row, column, xy)
        q += self.scanOrigin.reshape(1,1,2)
        
        # Convert via mapping (usually to mirror voltages)
        # xy = q.reshape(q.shape[0]*q.shape[1], 2)
        # pg.plot(xy[:,0], xy[:,1])
        if mapping is None:
            qm = q
        else:
            x,y = mapping(q[...,0], q[...,1])
            qm = np.empty(q.shape, x.dtype)
            qm[...,0] = x
            qm[...,1] = y
            
        ### select target array based on offset, shape, and stride. 
        # first check that this array is long enough
        if array.shape[0] < offset + shape[0] * stride[0]:
            print(self)
            raise Exception("Array is too small to contain the specified rectangle scan. Available: %d Required: %d" % (array.shape[0], shape[0] * stride[0]))
        
        # select the target sub-array
        target = pg.subArray(array, offset, shape, stride)
        
        # copy data into array (one copy per frame)
        target[:] = qm[np.newaxis, ...]
        
    def writeLaserMask(self, array):
        """
        Write 1s into the array in the active region of the scan.
        This is useful for ensuring that a laser is disabled during the overscan
        and inter-frame time periods. 
        """
        offset = self.activeOffset
        shape = self.activeShape
        stride = self.activeStride
        
        target = pg.subArray(array, offset, shape, stride)
        target[:] = 1
        
    def writeScanMask(self, array):
        """
        Write 1s into the array in the active region of the scan.
        This is useful for ensuring that a laser is disabled during the overscan
        and inter-frame time periods. 
        """
        offset = self.scanOffset
        shape = self.scanShape
        stride = self.scanStride
        
        target = pg.subArray(array, offset, shape, stride)
        target[:] = 1
        
    def extractImage(self, data, offset=0.0, subpixel=False):
        """Extract image data from a photodetector recording.

        This method returns an array of shape (frames, height, width) giving
        the image data collected during a scan. The redurned data excludes
        overscan regions, corrects for mirror lag, and reverses the
        even-numbered rows if the scan is bidirectional.

        Offset is a time in seconds to offset the data before unpacking
        the image array (this allows to correct for mirror lag). If subpixel 
        is True, then the offset may shift the image by a fraction of a pixel 
        using linear interpolation.
        """
        offset = self.imageOffset + offset * self.sampleRate / self.downsample
        intOffset = np.floor(offset)
        fracOffset = offset - intOffset

        shape = self.imageShape
        stride = self.imageStride

        if subpixel and fracOffset != 0:
            print(fracOffset)
            interp = data[:-1] * (1.0 - fracOffset) + data[1:] * fracOffset
            image = pg.subArray(interp, intOffset, shape, stride)            
        else:
            image = pg.subArray(data, intOffset, shape, stride)

        if self.bidirectional:
            image = image.copy()
            image[:, 1::2] = image[:, 1::2, ::-1]

        return image

    def measureMirrorLag(self, data, subpixel=False, minOffset=0., maxOffset=500e-6):
        """Estimate the mirror lag in a bidirectional raster scan.

        The *data* argument is a photodetector recording array.
        The return value can be used as the *offset* argument to extractImage().
        """
        if not self.bidirectional:
            raise Exception("Mirror lag can only be measured for bidirectional scans.")

        # decide how far to search
        rowTime = self.activeShape[2] / self.sampleRate
        pxTime = self.downsample / self.sampleRate
        maxOffset = min(maxOffset, rowTime * 0.6)

        # see whether we need to pad the data
        stride = self.imageStride
        shape = self.imageShape
        offset = self.imageOffset + maxOffset * self.sampleRate / self.downsample
        minSize = stride[0] * shape[0] + offset
        if data.shape[0] < minSize:
            appendShape = list(data.shape)
            appendShape[0] = 1 + minSize - data.shape[0]
            data = np.concatenate([data, np.zeros(appendShape, dtype=data.dtype)], axis=0)

        # find optimal shift by pixel
        offsets = np.arange(minOffset, maxOffset, pxTime)
        bestOffset = self._findBestOffset(data, offsets, subpixel=False)

        # Refine optimal shift by subpixel
        if subpixel:
            # Refine the estimate in two stages
            for i in range(2):
                w = offsets[1] - offsets[0]
                minOffset = bestOffset - (w/2)
                maxOffset = bestOffset + (w/2)
                offsets = np.linspace(minOffset, maxOffset, 5)
                bestOffset = self._findBestOffset(data, offsets, subpixel=True)

        return bestOffset

    def _findBestOffset(self, data, offsets, subpixel):
        # Try generating image using each item from a list of offsets. 
        # Return the offset that produced the least error between fields.
        bestOffset = None
        bestError = None
        errs = []
        for offset in offsets:
            # get base image averaged over frames
            img = self.extractImage(data, offset=offset, subpixel=subpixel).mean(axis=0)

            # split image into fields
            nr = 2 * (img.shape[0] // 2)
            f1 = img[0:nr:2]
            f2 = img[1:nr+1:2]

            err1 = np.abs((f1[:-1]-f2[:-1])**2).sum() / f1.size
            err2 = np.abs((f1[1:] -f2[:-1])**2).sum() / f1.size
            totErr = err1 + err2
            errs.append(totErr)
            if bestError is None or totErr < bestError:
                bestError = totErr
                bestOffset = offset
        # pg.plot(errs)
        return bestOffset

    def imageTransform(self):
        """
        Return the transform that maps from image pixel coordinates to global coordinates.
        """
        ims = self.imageShape
        acs = self.activeShape
        dx = self.colVector
        dy = self.rowVector

        p0 = self.activeOrigin
        p1 = p0 + acs[2] * dx
        p2 = p0 + acs[1] * dy

        # print p0, p1, p2
        # print acs, dx, dy

        localPts = list(map(pg.Vector, [[0,0], [ims[2],0], [0,ims[1]], [0,0,1]])) # w and h of data of image in pixels.
        globalPts = list(map(pg.Vector, [p0, p1, p2, [0,0,1]]))
        m = pg.solve3DTransform(localPts, globalPts)
        m[:,2] = m[:,3]
        m[2] = m[3]
        m[2,2] = 1
        tr = Qt.QTransform(*m[:3,:3].transpose().reshape(9))
        return tr

    def frameTimes(self):
        """
        Return an array of the start time for each image frame.
        """
        sr = self.sampleRate
        offset = self.activeOffset
        stride = self.activeStride
        nf = self.numFrames
        t = np.arange(nf) * (stride[0] / sr) + (offset / sr)
        return t

    ### Functions defining the relationships between variables:
    
    def _width(self):
        return np.linalg.norm(self.p1 - self.p0)
            
    def _height(self):
        try:
            return np.linalg.norm(self.p2 - self.p0)
        except RuntimeError:
            pass

        ar = self.pixelAspectRatio  # w/h
        return self.width * (self.numRows / ((self.activeCols // self.downsample) * ar))

    def _angle(self):
        dp = self.p1 - self.p0
        return np.arctan2(*dp[::-1])

    def _p1(self):
        p0 = self.p0
        width = self.width
        angle = self.angle
        return p0 + width * np.array([np.cos(angle), np.sin(angle)])

    def _p2(self):
        p0 = self.p0
        height = self.height
        angle = self.angle
        return p0 + height * np.array([np.sin(angle), -np.cos(angle)])

    def _osVector(self):
        # This vector is p1 -> osP1
        # Compute from p0, overscan, and scanSpeed
        osDist = (self.osLen // self.downsample) * self.pixelWidth

        #speed = self.scanSpeed
        #os = self.overscanDuration
        #osDist = speed * os
        
        p0 = self.p0
        p1 = self.p1
        dx = p1 - p0
        dx *= osDist / np.linalg.norm(dx)
        
        return dx

    def _osLen(self):
        """Length of overscan (non-downsampled)"""
        return int(np.ceil(self.minOverscan * self.sampleRate / self.downsample) * self.downsample)

        #osv = self.osVector
        #return np.ceil(np.linalg.norm(osv) / self.pixelWidth)

    def _overscanDuration(self):
        """
        The actual duration of the overscan on a single row, single side.
        """
        return self.osLen / self.sampleRate

    def _osP0(self):
        return self.p0 - self.osVector
    
    def _osP1(self):
        return self.p1 + self.osVector
    
    def _osP2(self):
        return self.p2 - self.osVector
    
    def _fullWidth(self):
        p0 = self.osP0
        p1 = self.osP1
        return np.linalg.norm(p1 - p0)
    
    def _pixelWidth(self):
        try:
            return self.pixelHeight * self.pixelAspectRatio
        except RuntimeError:
            pass

        try:
            return self.scanSpeed / self.sampleRate
        except RuntimeError:
            pass

        return self.width / (self.activeCols / self.downsample)
        
    def _pixelHeight(self):
        try:
            return self.pixelWidth / self.pixelAspectRatio        
        except RuntimeError:
            pass

        return self.height / (self.numRows - 1)

        # need to think this through.. it creates some weird situations.
        # try:
        #     samplesPerUm2 = self.frameExposure * self.sampleRate
        #     pxArea = 1e-12 * self.downsample / samplesPerUm2
        #     return pxArea / self.pixelWidth
        # except RuntimeError:
        #     pass

    
    def _pixelAspectRatio(self):
        return self.pixelWidth / self.pixelHeight
    
    def _frameDuration(self):
        # Note: duration calculation cannot depend on osp0, osp1, oswidth.
        # must be calculated from scan region excluding overscan.
        # (and then we can directly add 2*overscan*nlines)
        activeShape = self.activeShape
        os = self.overscanDuration
        sr = self.sampleRate
        
        osTime = activeShape[1] * 2 * os
        imageSamples = activeShape[2] * activeShape[1]
        imageTime = imageSamples / sr
        #print osTime, imageSamples, imageTime, sr, self.downsample
        return imageTime + osTime
    
    def _scanSpeed(self):
        try:
            # calculate from pixel size first
            pw = self.pixelWidth
            sr = self.sampleRate
            ds = self.downsample
            return (pw / ds) * sr
            
        except RuntimeError:
            # then from duration
            d = self.frameDuration
            nRows = self.numRows
            os = self.overscanDuration
            osDuration = nRows * 2 * os
            d -= osDuration
            rowTime = d / nRows
            w = self.width
            return w / rowTime

    def _scanOffset(self):
        return self.startTime * self.sampleRate
    
    def _scanShape(self):
        try:
            h = self.numRows
            w = self.numCols
            f = self.numFrames
            return (f, h, w)
        except RuntimeError:
            # duration, sample rate, size, and pixel aspect ratio
            f = self.numFrames
            w = self.width
            h = self.height
            sr = self.sampleRate
            dur = self.frameDuration
            pxar = self.pixelAspectRatio
            osLen = self.osLen
            ds = self.downsample

            maxSamples = int(dur * sr)

            # given we may use maxPixels, what is the best way to fill 
            # the scan area with pixels of the desired pixel aspect ratio?
            shapeRatio = ds * (w / h) / pxar  # this is numPixelCols / numPixelRows

            # Some maths:
            # dur == 2 * os * numRows + numRows * numActiveCols / sampleRate
            # (numActiveCols / ds) / numRows == shapeRatio
            # shapeRatio * dur == numActiveCols * 2 * os + numActiveCols**2 / sampleRate
            # solve quadratic:
            a = 1. / sr
            b = 2. * self.overscanDuration
            c = - shapeRatio * dur
            numActiveCols = np.round((-b + (b**2 - 4*a*c) ** 0.5) / (2*a))
            numCols = numActiveCols + osLen * 2
            # make sure numCols is a multiple of ds
            numCols = int(numCols / ds) * ds
            numRows = int(maxSamples / numCols)
            return (f, numRows, numCols)


    
    def _scanStride(self):
        return (self.frameLen + self.interFrameLen, self.numCols, 1)

    def _activeOffset(self):
        return self.imageOffset * self.downsample

    def _activeShape(self):
        return (self.numFrames, self.numRows, self.activeCols)
    
    def _activeStride(self):
        return self.scanStride

    def _imageShape(self):
        return self.numFrames, self.imageRows, self.imageCols

    def _imageOffset(self):
        return (self.scanOffset + self.osLen) // self.downsample
    
    def _imageStride(self):
        ds = self.downsample
        ss = self.scanStride
        return (ss[0] // ds, ss[1] // ds, 1)

    def _numRows(self):
        try:
            return self.scanShape[1]
        except RuntimeError:
            pass

        try:
            return self.imageRows
        except RuntimeError:
            pass

        h = self.height
        pxh = self.pixelHeight
        
        ny = int(h / pxh) + 1
        return ny



        # This can cause some weird comflicts.
        # distance = self.frameDuration * self.scanSpeed
        # return np.floor(distance / self.fullWidth)

    def _activeCols(self):
        try:
            return self.imageCols * self.downsample
        except RuntimeError:
            pass

        try:
            sw = self.scanShape[2]
            osl = self.osLen
            return sw - osl*2
        except RuntimeError:
            pass

        try:
            w = self.width
            pxw = self.pixelWidth
            nx = int(w / pxw) + 1
            return nx * self.downsample
        except RuntimeError:
            pass

    def _imageRows(self):
        return self.numRows  # just an alias

    def _imageCols(self):
        return self.activeCols // self.downsample

    def _numCols(self):
        try:
            return self.scanShape[2]
        except RuntimeError:
            pass

        return self.activeCols + (2 * self.osLen)


    def _frameExposure(self):
        pxArea = (self.pixelWidth * self.pixelHeight)
        samplesPerUm2 = 1e-12 * self.downsample / pxArea
        return samplesPerUm2 / self.sampleRate

    def _totalExposure(self):
        return self.numFrames * self.frameExposure

    def _interFrameLen(self):
        """Number of samples (not downsampled) between the end of one frame and the start of the next."""
        return np.ceil((self.interFrameDuration * self.sampleRate) / self.downsample) * self.downsample

    def _frameLen(self):
        """Number of samples (not downsampled) from the beggining to end of a single frame."""
        return self.numCols * self.numRows

    def _totalDuration(self):
        return (self.frameLen + self.interFrameLen) * self.numFrames / self.sampleRate

    def _rowVector(self):
        nf, ny, nx = self.scanShape
        return (self.osP2-self.osP0) / ny

    def _colVector(self):
        nf, ny, nx = self.scanShape
        return (self.osP1-self.osP0) / nx

    def _scanOrigin(self):
        # shift scan origin 1/2 row downward to scan through the center of the pixel.
        yv = self.rowVector * 0.5
        return self.osP0 + yv

    def _activeOrigin(self):
        return self.osP0 + self.colVector * self.osLen


class RectScanParameter(pTypes.SimpleParameter):
    """
    Parameter used to control rect scanning settings.
    """
    def __init__(self):
        fixed = [{'name': 'fixed', 'type': 'bool', 'value': True}] # child of parameters that may be determined by the user
        params = [
            dict(name='startTime', type='float', value=0, suffix='s', siPrefix=True, bounds=[0., None], step=1e-2),
            dict(name='numFrames', type='int', value=1, bounds=[1, None]),
            dict(name='frameDuration', type='float', value=50e-3, suffix='s', siPrefix=True, bounds=[0., None], step=1e-2),
            dict(name='interFrameDuration', type='float', value=0, suffix='s', siPrefix=True, bounds=[0., None], step=1e-2),
            dict(name='totalDuration', type='float', value=5e-1, suffix='s', siPrefix=True, bounds=[0., None], step=1e-2),
            dict(name='width', readonly=True, type='float', value=2e-5, suffix='m', siPrefix=True, bounds=[1e-6, None], step=1e-6),
            dict(name='height', readonly=True, type='float', value=1e-5, suffix='m', siPrefix=True, bounds=[1e-6, None], step=1e-6),
            dict(name='imageRows', type='int', value=500, limits=[1, None]),
            dict(name='imageCols', type='int', value=500, limits=[1, None]),
            dict(name='minOverscan', type='float', value=30.e-6, suffix='s', siPrefix=True, bounds=[0., 1.], step=0.1, dec=True, minStep=1e-7),
            dict(name='bidirectional', type='bool', value=True),
            dict(name='pixelWidth', type='float', value=4e-7, suffix='m', siPrefix=True, bounds=[1e-9, None], step=0.05, dec=True),
            dict(name='pixelHeight', type='float', value=4e-7, suffix='m', siPrefix=True, bounds=[1e-9, None], step=0.05, dec=True),
            dict(name='pixelAspectRatio', type='float', value=1, bounds=[1e-3, 1e3], step=0.5, dec=True),
            dict(name='scanOffset', type='int', readonly=True),
            dict(name='scanShape', type='str', readonly=True),
            dict(name='scanStride', type='str', readonly=True),
            dict(name='imageShape', type='str', readonly=True),
            dict(name='scanSpeed', type='float', readonly=True, suffix='m/s', siPrefix=True, bounds=[1e-9, None]), 
            dict(name='frameExposure', title=u'frame exposure/μm²', type='float', readonly=True, suffix='s', siPrefix=True, bounds=[1e-9, None]), 
            dict(name='totalExposure', title=u'total exposure/μm²', type='float', readonly=True, suffix='s', siPrefix=True, bounds=[1e-9, None]),
        ]
        self.system = RectScan()
        pTypes.SimpleParameter.__init__(self, name='rect_scan', type='bool', value=True, removable=True, renamable=True, children=params)

        # add 'fixed' parameters
        for param in self:
            cons = self.system._vars[param.name()][3]
            if 'f' in cons:
                if 'n' in cons:
                    param.addChild(dict(name='fixed', type='bool', value=False))
                else:
                    param.addChild(dict(name='fixed', type='bool', value=True, readonly=True))
            else:
                param.setReadonly(True)

        self.sigTreeStateChanged.connect(self.updateSystem)
        self.updateSystem()
        
    def updateSystem(self, param=None, changes=None):
        """
        Set all system variables to match the fixed values in the parameter tree.
        """
        #self.system.reset()
        for param in self:
            if 'f' in self.system._vars[param.name()][3]:
                if param['fixed']:
                    setattr(self.system, param.name(), param.value())
                else:
                    setattr(self.system, param.name(), None)
        self.updateAllParams()
    
    def updateAllParams(self):
        """
        Update the parameter tree to show all auto-generated values in the system.
        """
        try:
            self.sigTreeStateChanged.disconnect(self.updateSystem)
            reconnect = True
        except TypeError:
            reconnect = False
        try:
            with self.treeChangeBlocker():
                for param in self:
                    constraints = self.system._vars[param.name()][3]
                    if 'f' in constraints:
                        fixed = param['fixed']
                    else:
                        fixed = None


                    if fixed is True:
                        self.updateParam(param, 'fixed')
                    else:
                        try: # value is auto-generated
                            val = getattr(self.system, param.name())
                            if param.type() == 'str':
                                param.setValue(repr(val))
                            else:
                                param.setValue(val)
                            param.setReadonly(True)
                            if fixed is False:
                                self.updateParam(param, 'autoFixable')
                            else:
                                self.updateParam(param, 'auto')

                        except RuntimeError:  
                            if fixed is not None:  # no value, fixable
                                self.updateParam(param, 'incomplete')
                            else:
                                self.updateParam(param, 'unconstrained')

        finally:
            if reconnect:
                self.sigTreeStateChanged.connect(self.updateSystem)
    
    def updateParam(self, param, mode):
        param.blockSignals(True)  # Never trigger callbacks because of color changes
        try:
            if mode == 'fixed':
                param.setReadonly(False)
                bg = (200, 200, 255)
            elif mode == 'autoFixable':
                param.child('fixed').setValue(False)
                param.child('fixed').setReadonly(True)
                bg = (200, 230, 230)
            elif mode == 'incomplete':
                param.setReadonly(True)
                param.child('fixed').setReadonly(False)
                bg = (255, 255, 200)
            elif mode == 'unconstrained':
                bg = (255, 200, 200)
            elif mode == 'auto':
                bg = (200, 255, 200)

            for item in param.items:
                item.setBackground(0, pg.mkColor(bg))
        finally:
            param.blockSignals(False)

    def saveState(self):
        return self.system.saveState()
    
    def restoreState(self, state):
        self.system.restoreState(state)

        try:
            self.sigTreeStateChanged.disconnect(self.updateSystem)
            for k, v in state.items():
                if v[1] == 'fixed':
                    try:
                        param = self.child(k)
                    except KeyError:
                        continue
                    param.setValue(v[0])
                    param['fixed'] = True
        finally:
            self.sigTreeStateChanged.connect(self.updateSystem)

        self.updateAllParams()

