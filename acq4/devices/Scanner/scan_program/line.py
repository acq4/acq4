from __future__ import print_function
from six.moves import range
import weakref
import numpy as np
import acq4.pyqtgraph as pg
from acq4.util import Qt
import acq4.pyqtgraph.parametertree.parameterTypes as pTypes
from acq4.pyqtgraph.parametertree import Parameter, ParameterTree, ParameterItem, registerParameterType
from .component import ScanProgramComponent


class LineScanComponent(ScanProgramComponent):
    """
    Scans the laser over a path composed of multiple line segments.
    """
    type = 'line'
    
    def __init__(self, scanProgram):
        ScanProgramComponent.__init__(self, scanProgram)
        self.ctrl = LineScanControl(self)

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

    def generateVoltageArray(self, arr):
        """
        Use a polyline to make a scan that covers multiple regions in an
        interleaved fashion. Alternate line segments of the polyline
        are either the "scan" or the "interscan", allowing rapid movement
        between successive points. 
        Interscan intervals are green on the line, scan intervals are white
        """
        pts = list(map(pg.Point, cmd['points']))
        startPos = pts[0]                
        stopPos = pts[-1]
        
        #scanPoints = cmd['sweepDuration']/dt # in point indices, not time.
        #interTracePoints = cmd['intertraceDuration']/dt
        #scanPause = np.ones(int(interTracePoints))
        #cmd['samplesPerScan'] = scanPoints
        #cmd['samplesPerPause'] = interTracePoints
        sweepSpeed = 1000 * cmd['sweepSpeed'] # in m/msec
        interSweepSpeed = 1000 * cmd['interSweepSpeed']
        ScanFlag = False
        xp = np.array([])
        yp = np.array([])
        pockels = np.array([])
        nSegmentScans = 0
        nIntersegmentScans = 0
        scanPointList = []
        interScanFlag = False
        for k in range(len(pts)): # loop through the list of points
            k2 = k + 1
            if k2 > len(pts)-1:
                k2 = 0
            dist = (pg.Point(pts[k]-pts[k2])).length()
            if interScanFlag is False:
                scanPoints = int((dist/sweepSpeed)/dt)
                xPos = np.linspace(pts[k].x(), pts[k2].x(), scanPoints)
                yPos = np.linspace(pts[k].y(), pts[k2].y(), scanPoints)
                pockels = np.append(pockels, np.ones(scanPoints))
                nSegmentScans += 1
                scanPointList.append(scanPoints)
            else:
                interSweepPoints = int((dist/interSweepSpeed)/dt)
                xPos = np.linspace(pts[k].x(), pts[k2].x(), interSweepPoints)
                yPos = np.linspace(pts[k].y(), pts[k2].y(), interSweepPoints)
                pockels = np.append(pockels, np.zeros(interSweepPoints))
                nIntersegmentScans += 1
                scanPointList.append(interSweepPoints)
            x, y = dev.mapToScanner(xPos, yPos, cmd['laser'])
            xp = np.append(xp, x)
            yp = np.append(yp, y)
            interScanFlag = not interScanFlag
            
        cmd['nSegmentScans'] = nSegmentScans
        cmd['nIntersegmentScans'] = nIntersegmentScans
        cmd['scanPointList'] = scanPointList
        x = np.tile(xp, cmd['nScans'])
        y = np.tile(yp, cmd['nScans'])
        arr[0, startInd:startInd + len(x)] = x
        arr[1, startInd:startInd + len(y)] = y
        arr[0, startInd + len(x):stopInd] = arr[0, startInd + len(x)-1] # fill in any unused sample on this scan section
        arr[1, startInd + len(y):stopInd] = arr[1, startInd + len(y)-1]
        lastPos = (x[-1], y[-1])
        
        return stopInd


class MultiLineScanROI(pg.PolyLineROI):
    """ custom class over ROI polyline to allow alternate coloring of different segments
    """
    def addSegment(self, *args, **kwds):
        pg.PolyLineROI.addSegment(self, *args, **kwds)
        self.recolor()
    
    def removeSegment(self, *args, **kwds):
        pg.PolyLineROI.removeSegment(self, *args, **kwds)
        self.recolor()
    
    def recolor(self):
        for i, s in enumerate(self.segments):
            if i % 2 == 0:
                s.setPen(self.pen)
            else:
                s.setPen(pg.mkPen([75, 200, 75]))


class LineScanControl(Qt.QObject):
    
    sigStateChanged = Qt.Signal(object)
    
    def __init__(self, component):
        Qt.QObject.__init__(self)
        self.name = component.name
        ### These need to be initialized before the ROI is initialized because they are included in stateCopy(), which is called by ROI initialization.
        
        self.params = pTypes.SimpleParameter(name=self.name, type='bool', value=True, removable=True, renamable=True, children=[
            dict(name='Length', type='float', value=1e-5, suffix='m', siPrefix=True, bounds=[1e-6, None], step=1e-6),
            dict(name='startTime', type='float', value=5e-2, suffix='s', siPrefix=True, bounds=[0., None], step=1e-2),
            dict(name='sweepSpeed', type='float', value=1e-6, suffix='m/ms', siPrefix=True, bounds=[1e-8, None], minStep=5e-7, step=0.5, dec=True),
            dict(name='interSweepSpeed', type='float', value=5e-6, suffix='m/ms', siPrefix=True, bounds=[1e-8, None], minStep=5e-7, step=0.5, dec=True),
            dict(name='nScans', type='int', value=100, bounds=[1, None]),
            dict(name='endTime', type='float', value=5.5e-1, suffix='s', siPrefix=True, bounds=[0., None], step=1e-2, readonly=True),
        ])
        self.params.component = weakref.ref(component)
        self.roi = MultiLineScanROI([[0.0, 0.0], [self.params['Length'], self.params['Length']]])
        self.roi.sigRegionChangeFinished.connect(self.updateFromROI)
        self.params.sigTreeStateChanged.connect(self.update)
        
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
    
    def update(self):
        pts = self.roi.listPoints()
        scanTime = 0.
        interScanFlag = False
        for k in range(len(pts)): # loop through the list of points
            k2 = k + 1
            if k2 > len(pts)-1:
                k2 = 0
            dist = (pts[k]-pts[k2]).length()
            if interScanFlag is False:
                scanTime += dist/(self.params['sweepSpeed']*1000.)
            else:
                scanTime += dist/(self.params['interSweepSpeed']*1000.)
            interScanFlag = not interScanFlag
        self.params['endTime'] = self.params['startTime']+(self.params['nScans']*scanTime)
        self.setVisible(self.params.value())
    
    def updateFromROI(self):
        self.update()
        
    def generateTask(self):
        points=self.roi.listPoints() # in local coordinates local to roi.
        points = [self.roi.mapToView(p) for p in points] # convert to view points (as needed for scanner)
        points = [(p.x(), p.y()) for p in points]   ## make sure we can write this data to HDF5 eventually..
        return {'type': self.name, 'active': self.isActive(), 'points': points, 'startTime': self.params['startTime'], 'sweepSpeed': self.params['sweepSpeed'], 
                'endTime': self.params['endTime'], 'interSweepSpeed': self.params['interSweepSpeed'], 'nScans': self.params['nScans']}
                
