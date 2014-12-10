from __future__ import division
import weakref
import numpy as np
import scipy.interpolate
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
        # NOTE: point should have constant speed regardless of radius.
        raise NotImplementedError()
        
    def generatePosCmd(self, array):
        """
        Generate the position commands for this scan component and store
        inside *array*.
        
        """
        raise NotImplementedError()


class SpiralScanROI(pg.ROI):
    def __init__(self, pos=None, radius=None, **args):
        self.angles = [0, 8 * np.pi]
        self.radii = [radius * 0.75, radius]
        self._path = None
        size = (radius*2,) * 2
        pg.ROI.__init__(self, pos, size, **args)
        self.aspectLocked = True
        self.addScaleHandle([0.5*2.**-0.5 + 0.5, 0.5*2.**-0.5 + 0.5], 
                            [0.5, 0.5], name='outer')        
        
    def setAngles(self, start, stop):
        self.angles = [start, stop]
        self._path = None
        self.update()
        
    def setRadii(self, start, stop):
        self.radii = [start, stop]
        self.setSize([stop*2, stop*2])
        self._path = None
    
    def stateChanged(self, finish=True):
        self._path = None
        pg.ROI.stateChanged(self, finish=finish)
    
    def paint(self, p, *args):
        if self._path is None:
            ss = SpiralScan(self.radii, self.angles)
            npts = min(5000, int(30 * abs(self.angles[1] - self.angles[0]) / np.pi))
            pts = ss.path(npts)
            self._path = pg.arrayToQPath(pts[:,0], pts[:,1])
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(self.currentPen)
        p.drawPath(self._path)
        


class SpiralScanControl(QtCore.QObject):
    
    sigStateChanged = QtCore.Signal(object)
    
    def __init__(self, component):
        QtCore.QObject.__init__(self)
        ### These need to be initialized before the ROI is initialized because they are included in stateCopy(), which is called by ROI initialization.
        self.name = component.name
        self.component = weakref.ref(component)

        self.params = SpiralScanParameter()

        self.params.component = self.component
        
        self.roi = SpiralScanROI(pos=[0.0, 0.0], radius=self.params['radius'])

        self.params.sigTreeStateChanged.connect(self.paramsChanged)
        self.roi.sigRegionChanged.connect(self.roiChanged)
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
        outer = self.params['radius']
        inner = outer - (outer * self.params['thickness'] / 100.)
        self.roi.setRadii(inner, outer)
        
        spacing = self.params['spacing']
        turns = (outer - inner) / spacing
        a0 = 0
        a1 = 2 * np.pi * turns
        self.roi.setAngles(a0, a1)
        
        ss = SpiralScan((inner, outer), (a0, a1))
        
        self.params['speed'] = 1e-3 * ss.length() / self.params['duration']
        self.update()
        
    def update(self):
        pass
    
    def roiChanged(self):
        """ read the ROI size and repost in the parameter tree """
        state = self.roi.getState()
        w, h = state['size']
        self.params['radius'] = w / 2.
        
    def generateTask(self):
        task = {'type': self.name, 'active': self.isActive(), 'scanInfo': {'pos': (0,0)}}
        return task


class SpiralScan(object):
    """Class used for computing and storing information about spiral scan 
    geometry.
    
    Parameters
    ----------
    radii : tuple
        Inner and outer spiral radii (in m)
    angles : tuple
        Start and end angles (in radians) corresponding to inner and outer
        radii, respectively. An angle of 0 points along the x axis and positive
        angles turn counter-clockwise. The number of spiral turns is determined
        by the difference between the end and start angles.
    """
    def __init__(self, radii, angles):
        self.radii = radii
        self.angles = angles
        
    def length(self):
        """Return exact length of spiral.
        """
        u = self.pitch()
        #a0 = self.radii[0] / u
        #a1 = a0 + (self.angles[1] - self.angles[0])
        return self.spiralLength(self.radii[1], u) - self.spiralLength(self.radii[0], u)

    @staticmethod
    def spiralLength(r, u):
        """Length of spiral given radius and pitch. 
        """
        a = r / u
        return 0.5 * u * (a * (a**2 + 1)**0.5 + np.arcsinh(a))

    def pitch(self):
        """Return the difference in radius for one complete turn.
        """
        return (self.radii[1] - self.radii[0]) / (self.angles[1] - self.angles[0])

    def path(self, npts=None, uniform=True):
        """Generate *npts* x/y points along the path of the spiral.
        
        If *uniform* is True, then all returned points are equally spaced along
        the length of the spiral (this is used for generating scanner
        voltages).
        
        If *uniform* is False, then the returned path points have equal angular
        spacing (this is faster to compute; used only for generating spiral 
        graphics).
        """
        radii = self.radii
        angles = self.angles
        r = np.linspace(radii[0], radii[1], npts)
        theta = np.linspace(angles[0], angles[1], npts)
        pts = np.empty((npts, 2))
        pts[:, 0] = r * np.cos(theta) + radii[1]
        pts[:, 1] = r * np.sin(theta) + radii[1]
        
        if uniform:
            # Resample to have uniform length. 
            # An analytic solution would be preferred, but there might not be one..
            
            # First compute length at every sample on the spiral
            u = self.pitch()
            l1 = self.spiralLength(r, u) - self.spiralLength(radii[0], u)
            
            # Now resample points to have uniform spacing
            l2 = np.linspace(0, l1[-1], npts)
            pts = scipy.interpolate.griddata(l1, pts, l2, method='linear')
        
        return pts
        

class SpiralScanParameter(pTypes.SimpleParameter):
    """
    Parameter used to control spiral scanning settings.
    """
    def __init__(self):
        fixed = [{'name': 'fixed', 'type': 'bool', 'value': True}] # child of parameters that may be determined by the user
        params = [
            dict(name='radius', type='float', value=2e-5, suffix='m', siPrefix=True, bounds=[1e-6, None], step=1e-6),
            dict(name='thickness', type='float', value=25, suffix='%', bounds=[0, 100], step=1),
            dict(name='spacing', type='float', value=2e-6, suffix='m', siPrefix=True, step=0.5e-6, bounds=[1e-7, None]),
            dict(name='duration', type='float', value=0.002, suffix='s', bounds=[1e-6, None], siPrefix=True, step=1e-3),
            dict(name='speed', type='float', readonly=True, value=0, suffix='m/ms', siPrefix=True),
        ]
        pTypes.SimpleParameter.__init__(self, name='spiral_scan', type='bool', value=True, removable=True, renamable=True, children=params)

        #self.sigTreeStateChanged.connect(self.updateSystem)
