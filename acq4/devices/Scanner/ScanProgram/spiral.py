import weakref
import numpy as np
from PyQt4 import QtCore, QtGui

import acq4.pyqtgraph as pg
import acq4.pyqtgraph.parametertree.parameterTypes as pTypes
from acq4.pyqtgraph.parametertree import Parameter, ParameterTree, ParameterItem, registerParameterType
from .component import ScanProgramComponent



class SpiralScanComponent(ScanProgramComponent):
    """
    Scans the laser in the shape of an elliptical spiral.    
    """    
    name = 'spiral'
    def __init__(self, cmd=None, scanProgram=None):
        ScanProgramComponent.__init__(self, cmd, scanProgram)
        self.ctrl = SpiralScanControl(self)

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

    def generateTask(self):
        """
        Generate the task structure that fully describes the behavior of this 
        component.
        """
        return self.ctrl.generateTask()
        
    @classmethod
    def generateVoltageArray(cls, array, dev, cmd):
        """
        Generate mirror voltages for this scan component and store inside
        *array*. Returns the start and stop indexes used by this component.
        """
        raise NotImplementedError()
        
    def generatePosCmd(self, array):
        """
        Generate the position commands for this scan component and store
        inside *array*.
        
        """
        raise NotImplementedError()


#class SpiralScanROI(pg.ROI):
    #def __init__(self, pos=None, radius=None, **args):
        #pg.ROI.__init__(self, pos, size=(radius, radius), **args)
        ##self.translateSnap = False
        #self.addFreeHandle([0.25,0], name='a')
        #self.addRotateFreeHandle([1,0], [0,0], name='r')
        
    #def getRadius(self):
        #radius = pg.Point(self.handles[1]['item'].pos()).length()
        #return radius
    
    #def boundingRect(self):
        #r = self.getRadius()
        #return QtCore.QRectF(-r*1.1, -r*1.1, 2.2*r, 2.2*r)
            
    #def stateChanged(self, finish=True):
        #pg.ROI.stateChanged(self, finish=finish)
        #if len(self.handles) > 1:
            #self.path = QtGui.QPainterPath()
            #h0 = pg.Point(self.handles[0]['item'].pos()).length()
            #a = h0/(2.0*np.pi)
            #theta = 30.0*(2.0*np.pi)/360.0
            #self.path.moveTo(QtCore.QPointF(a*theta*np.cos(theta), a*theta*np.sin(theta)))
            #x0 = a*theta*np.cos(theta)
            #y0 = a*theta*np.sin(theta)
            #radius = self.getRadius()
            #theta += 20.0*(2.0*np.pi)/360.0
            #i = 0
            #while pg.Point(x0, y0).length() < radius and i < 1000:
                #x1 = a*theta*np.cos(theta)
                #y1 = a*theta*np.sin(theta)
                #self.path.lineTo(QtCore.QPointF(x1,y1))
                #theta += 20.0*(2.0*np.pi)/360.0
                #x0 = x1
                #y0 = y1
                #i += 1
            #return self.path
        
    #def shape(self):
        #p = QtGui.QPainterPath()
        #p.addEllipse(self.boundingRect())
        #return p
    
    #def paint(self, p, *args):
        #p.setRenderHint(QtGui.QPainter.Antialiasing)
        #p.setPen(self.currentPen)
        #p.drawPath(self.path)
        #p.setPen(QtGui.QPen(QtGui.QColor(255,0,0)))
        #p.drawPath(self.shape())
        #p.setPen(QtGui.QPen(QtGui.QColor(0,0,255)))
        #p.drawRect(self.boundingRect())

class SpiralScanROI(pg.CircleROI):
    def __init__(self, pos, radius):
        pg.CircleROI.__init__(self, pos, (radius, radius))


class SpiralScanControl(QtCore.QObject):
    
    sigStateChanged = QtCore.Signal(object)
    
    def __init__(self, component):
        QtCore.QObject.__init__(self)
        ### These need to be initialized before the ROI is initialized because they are included in stateCopy(), which is called by ROI initialization.
        self.name = component.name
        self.component = weakref.ref(component)

        self.params = SpiralScanParameter()

        self.params.component = self.component
        
        self.roi = SpiralScanROI(pos=[0.0, 0.0], radius=self.params['outer radius'])

        self.params.sigTreeStateChanged.connect(self.paramsChanged)
        self.roi.sigRegionChangeFinished.connect(self.roiChanged)
        self.paramsChanged()
        
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

    def paramsChanged(self, param=None, changes=None):
        self.update()
        
    def update(self):
        pass
    
    def roiChanged(self):
        """ read the ROI rectangle width and height and repost
        in the parameter tree """
        #state = self.roi.getState()
        #w, h = state['size']
        #self.params.system.p0 = pg.Point(self.roi.mapToView(pg.Point(0,0)))
        #self.params.system.p1 = pg.Point(self.roi.mapToView(pg.Point(w,0)))
        #self.params.system.p2 = pg.Point(self.roi.mapToView(pg.Point(0,h)))
        
    def generateTask(self):
        #state = self.roi.getState()
        #w, h = state['size']
        #p0 = pg.Point(0,0)
        #p1 = pg.Point(w,0)
        #p2 = pg.Point(0, h)
        #points = [p0, p1, p2]
        #points = [pg.Point(self.roi.mapToView(p)) for p in points] # convert to view points (as needed for scanner)
        task = {'type': self.name, 'active': self.isActive(), 'scanInfo': {'pos': (0,0)}}
        return task


class SpiralScanParameter(pTypes.SimpleParameter):
    """
    Parameter used to control spiral scanning settings.
    """
    def __init__(self):
        fixed = [{'name': 'fixed', 'type': 'bool', 'value': True}] # child of parameters that may be determined by the user
        params = [
            dict(name='outer radius', readonly=True, type='float', value=2e-5, suffix='m', siPrefix=True, bounds=[1e-6, None], step=1e-6),
            dict(name='inner radius', readonly=True, type='float', value=1e-5, suffix='m', siPrefix=True, bounds=[1e-6, None], step=1e-6),
            dict(name='turns', type='float', value=10, step=1, bounds=[0, None]),
            dict(name='duration', type='float', value=0.002, suffix='s', bounds=[1e-6, None], siPrefix=True, step=1e-3),
        ]
        pTypes.SimpleParameter.__init__(self, name='rect_scan', type='bool', value=True, removable=True, renamable=True, children=params)

        #self.sigTreeStateChanged.connect(self.updateSystem)
