import weakref
import numpy as np
import acq4.pyqtgraph as pg
from acq4.pyqtgraph import QtGui, QtCore
import acq4.pyqtgraph.parametertree.parameterTypes as pTypes
from acq4.pyqtgraph.parametertree import Parameter, ParameterTree, ParameterItem, registerParameterType
from .component import ScanProgramComponent


class LineScanComponent(ScanProgramComponent):
    """
    Scans the laser over a path composed of multiple line segments.
    """
    name = 'line'
    
    def __init__(self, cmd=None, scanProgram=None):
        ScanProgramComponent.__init__(self, cmd, scanProgram)
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

    
    @classmethod
    def generateVoltageArray(cls, arr, dt, dev, cmd, startInd, stopInd):
        """
        Use a polyline to make a scan that covers multiple regions in an
        interleaved fashion. Alternate line segments of the polyline
        are either the "scan" or the "interscan", allowing rapid movement
        between successive points. 
        Interscan intervals are green on the line, scan intervals are white
        """
        pts = map(pg.Point, cmd['points'])
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
        for k in xrange(len(pts)): # loop through the list of points
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

    #elif cmd['type'] == 'line':
        #if lastPos is None:
            #raise Exception("'line' command with no defined starting position")
        #pos = cmd['pos']
        
        #xPos = linspace(lastPos[0], pos[0], stopInd-startInd)
        #yPos = linspace(lastPos[1], pos[1], stopInd-startInd)
        #x, y = self.mapToScanner(xPos, yPos)
        #arr[0, startInd:stopInd] = x
        #arr[1, startInd:stopInd] = y
        #lastPos = pos
        
    #elif cmd['type'] == 'lineScan':
        #startPos = cmd['points'][0]                
        #stopPos = cmd['points'][1]               
        #scanLength = (stopInd - startInd)/cmd['nScans'] # in point indices, not time.
        #retraceLength = cmd['retraceDuration']/dt
        #scanLength = scanLength - retraceLength # adjust for retrace
        #scanPause = np.ones(int(retraceLength))
        #scanPointList = []
        #cmd['samplesPerScan'] = scanLength
        #cmd['samplesPerPause'] = scanPause.shape[0]
        #xPos = np.linspace(startPos.x(), stopPos.x(), scanLength)
        #xPos = np.append(xPos, startPos.x()*scanPause)
        #scanPointList.append(int(scanLength/dt))
        #cmd['scanPointList'] = scanPointList
        #yPos = np.linspace(startPos.y(), stopPos.y(), scanLength)
        #yPos = np.append(yPos, startPos.x()*scanPause)
        #x, y = self.mapToScanner(xPos, yPos)
        #x = np.tile(x, cmd['nScans'])
        #y = np.tile(y, cmd['nScans'])
        #arr[0, startInd:startInd + len(x)] = x
        #arr[1, startInd:startInd + len(y)] = y
        #arr[0, startInd + len(x):stopInd] = arr[0, startInd + len(x)-1] # fill in any unused sample on this scan section
        #arr[1, startInd + len(y):stopInd] = arr[1, startInd + len(y)-1]
        #lastPos = (x[-1], y[-1])

    
#class ProgramLineScan(QtCore.QObject):
    
    #sigStateChanged = QtCore.Signal(object)
    
    #def __init__(self):
        #QtCore.QObject.__init__(self)
        #self.name = 'lineScan'
        #### These need to be initialized before the ROI is initialized because they are included in stateCopy(), which is called by ROI initialization.
        
        #self.params = pTypes.SimpleParameter(name=self.name, autoIncrementName = True, type='bool', value=True, removable=True, renamable=True, children=[
            #dict(name='length', type='float', value=1e-5, suffix='m', siPrefix=True, bounds=[1e-6, None], step=1e-6),
            #dict(name='startTime', type='float', value=5e-2, suffix='s', siPrefix=True, bounds=[0., None], step=1e-2),
            #dict(name='sweepDuration', type='float', value=4e-3, suffix='s', siPrefix=True, bounds=[0., None], step=1e-2),
            #dict(name='retraceDuration', type='float', value=1e-3, suffix='s', siPrefix=True, bounds=[0., None], step=1e-3),
            #dict(name='nScans', type='int', value=100, bounds=[1, None]),
            #dict(name='endTime', type='float', value=5.5e-1, suffix='s', siPrefix=True, bounds=[0., None], step=1e-2, readonly=True),
        #])
        #self.params.ctrl = self        
        #self.roi = pg.LineSegmentROI([[0.0, 0.0], [self.params['length'], self.params['length']]])
 ##       print dir(self.roi)
        #self.params.sigTreeStateChanged.connect(self.update)
        #self.roi.sigRegionChangeFinished.connect(self.updateFromROI)
        
    #def getGraphicsItems(self):
        #return [self.roi]

    #def isActive(self):
        #return self.params.value()

    #def setVisible(self, vis):
        #if vis:
            #self.roi.setOpacity(1.0)  ## have to hide this way since we still want the children to be visible
            #for h in self.roi.handles:
                #h['item'].setOpacity(1.0)
        #else:
            #self.roi.setOpacity(0.0)
            #for h in self.roi.handles:
                #h['item'].setOpacity(0.0)
        
    #def parameters(self):
        #return self.params
    
    #def update(self):
        #self.params['endTime'] = self.params['startTime']+self.params['nScans']*(self.params['sweepDuration'] + self.params['retraceDuration'])
        #self.setVisible(self.params.value())
            
    #def updateFromROI(self):
        #p =self.roi.listPoints()
        #dist = (pg.Point(p[0])-pg.Point(p[1])).length()
        #self.params['length'] = dist
        
    #def generateTask(self):
        #points = self.roi.listPoints() # in local coordinates local to roi.
        #points = [self.roi.mapToView(p) for p in points] # convert to view points (as needed for scanner)
        #return {'type': 'lineScan', 'active': self.isActive(), 'points': points, 'startTime': self.params['startTime'], 'sweepDuration': self.params['sweepDuration'], 
                #'endTime': self.params['endTime'], 'retraceDuration': self.params['retraceDuration'], 'nScans': self.params['nScans']}


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


class LineScanControl(QtCore.QObject):
    
    sigStateChanged = QtCore.Signal(object)
    
    def __init__(self, component):
        QtCore.QObject.__init__(self)
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
        for k in xrange(len(pts)): # loop through the list of points
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
    #p =self.roi.listPoints()
        #dist = (pg.Point(p[0])-pg.Point(p[1])).length()
        #self.params['length'] = dist
        
    def generateTask(self):
        points=self.roi.listPoints() # in local coordinates local to roi.
        points = [self.roi.mapToView(p) for p in points] # convert to view points (as needed for scanner)
        points = [(p.x(), p.y()) for p in points]   ## make sure we can write this data to HDF5 eventually..
        return {'type': self.name, 'active': self.isActive(), 'points': points, 'startTime': self.params['startTime'], 'sweepSpeed': self.params['sweepSpeed'], 
                'endTime': self.params['endTime'], 'interSweepSpeed': self.params['interSweepSpeed'], 'nScans': self.params['nScans']}
                
