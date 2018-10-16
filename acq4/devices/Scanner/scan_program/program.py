# -*- coding: utf-8 -*-
from __future__ import print_function
import numpy as np
from collections import OrderedDict
import importlib
import six

import acq4.pyqtgraph as pg
from acq4.util.HelpfulException import HelpfulException
import acq4.pyqtgraph.parametertree.parameterTypes as pTypes
from acq4.pyqtgraph.parametertree import Parameter, ParameterTree, ParameterItem, registerParameterType
from acq4.util import Qt


# Keep track of all available scan program components
COMPONENTS = OrderedDict()

def registerScanComponent(component):
    COMPONENTS[component.type] = component

for cType in ['step', 'line', 'rect', 'loop', 'ellipse', 'spiral']:
    mod = importlib.import_module('.' + cType, 'acq4.devices.Scanner.scan_program')
    clsName = cType.capitalize() + "ScanComponent"
    if hasattr(mod, clsName):
        registerScanComponent(getattr(mod, clsName))



class ScanProgram:
    """
    ScanProgram encapsulates one or more laser scanning operations that are
    executed in sequence. 
    
    It provides the following services:
    
    * GUI for generating task commands and interactive representation of 
      command in camera module
    * Generate mirror voltage commands
    * Save / restore functionality
    * Masking arrays for controlling laser power
    * Extraction and analysis of imaging data generated during a scan
    
    Note that most of the functionality of ScanProgram is provided through 
    subclasses of ScanProgramComponent. The available components are listed in
    the COMPONENTS global variable, which may be used to install new component
    types at runtime.
    """
    def __init__(self):
        self.components = []
        
        self.canvas = None  # used to display graphical controls for components
        self.scanner = None
        self.laser = None  # may be overridden by each component
        
        self.sampleRate = 100e3
        self.numSamples = 10e3
        self.downsample = 1
        
        self.ctrlGroup = ScanProgramCtrlGroup()  # used to display GUI for components
        self.ctrlGroup.sigAddNewRequested.connect(self.paramRequestedNewComponent)
        self.ctrlGroup.sigChildRemoved.connect(self.paramRequestedRemove)

        self._visible = True  # whether graphics items should be displayed

        self.preview = ScanProgramPreview(self)
        
    def addComponent(self, component):
        """Add a new component to this program. May specify either a 
        ScanProgramComponent instance or a string indicating the type of a new
        component to create.
        
        For supported component types, see the COMPONENTS global variable. This
        may also be used to install new component types at runtime.
        """
        ## called when "Add Control.." combo is changed
        if isinstance(component, six.string_types):
            component = COMPONENTS[component](self)
        
        self.ctrlGroup.addChild(component.ctrlParameter(), autoIncrementName=True)
        if self.canvas is not None:
            for item in component.graphicsItems():
                self.canvas.addItem(item, None, [1, 1], 10000)
        self.components.append(component)
        return component

    def removeComponent(self, component):
        """Remove a component from this program.
        """
        self.components.remove(component)
        self.clearGraphicsItems(component)
        
    def ctrlParameter(self):
        """Return the control Parameter for this scan program. 
        
        This object may be displayed on a ParameterTree to provide the user
        control over the design of the program.
        """
        return self.ctrlGroup

    def setCanvas(self, canvas):
        """Set the canvas into which this scan program should add information
        about the layout of its components. 
        
        The canvas must be any object with an `addItem(QGraphicsItem)` method,
        such as pyqtgraph.ViewBox.
        """
        self.canvas = canvas
        if canvas is None:
            self.clearGraphicsItems()
        else:
            for c in self.components:
                for i in c.graphicsItems():
                    c.addItem(i)

    def setDevices(self, scanner=None, laser=None):
        """Set the scanner and default laser devices to use with this scan
        program.
        
        Note that the laser device is only a default and may be overridden by
        each component individually.
        """
        if scanner is not None:
            self.scanner = scanner
        if laser is not None:
            self.laser = laser
        
    def setSampling(self, rate, samples, downsample):
        """Set the sampling properties used by all components in the program:
        sample rate, number of samples, and downsampling factor.
        """
        if self.sampleRate or samples != self.numSamples or downsample != self.downsample:
            self.sampleRate = rate
            self.numSamples = samples
            self.downsample = downsample
            for component in self.components:
                component.samplingChanged()

    def saveState(self):
        """Return a serializable data structure representing the state of the 
        scan program.
        """
        task = []
        for component in self.components:
            if component.isActive():
                task.append(component.saveState())
        return task

    def restoreState(self, state):
        """Restore the state of this program from the result of a previous call
        to saveState(). 
        """
        for compState in state:
            comp = self.addComponent(compState['type'])
            comp.restoreState(compState)
        
    def clearGraphicsItems(self, component=None):
        """Remove all graphics items for this program from the attached canvas.
        """
        self.preview.clear()
        if component is None:
            comps = self.components
        else:
            comps = [component]
        for c in comps:
            for i in c.graphicsItems():
                if i.scene() is not None:
                    i.scene().removeItem(i)

    def generateVoltageArray(self):
        """Generate an array of x,y voltage commands needed to drive the scanner
        for this program.
        """
        return self.generatePositionArray(_voltage=True)

    def generatePositionArray(self, _voltage=False):
        """Generate an array of x,y position values for this scan program.
        """
        arr = np.zeros((self.numSamples, 2))

        # Generate command for each component
        for component in self.components:
            if not component.isActive():
                continue
            
            if _voltage:
                component.generateVoltageArray(arr)
            else:
                component.generatePositionArray(arr)

        # Fill in gaps
        mask = self.generateLaserMask().astype(np.byte)
        dif = mask[1:] - mask[:-1]
        on = list(np.argwhere(dif == 1)[:,0]+1)
        off = list(np.argwhere(dif == -1)[:,0]+1)
        if mask[-1] == 0:
            on.append(len(mask))

        if _voltage:
            lastValue = np.array(self.scanner.getVoltage())
        else:
            lastValue = np.array([np.nan, np.nan])
        lastOff = 0

        while len(on) > 0 or len(off) > 0:
            nextOn  = on[0]  if len(on)  > 0 else np.inf
            nextOff = off[0] if len(off) > 0 else np.inf

            if nextOn < nextOff:
                on.pop(0)
                arr[lastOff:nextOn] = lastValue
            else:
                off.pop(0)
                lastOff = nextOff
                lastValue = arr[nextOff-1]
            
        return arr
    
    def generateLaserMask(self):
        mask = np.zeros(self.numSamples, dtype=bool)
        for component in self.components:
            if not component.isActive():
                continue
            mask |= component.scanMask()

        return mask

    def close(self):
        self.clearGraphicsItems()

    def paramRequestedNewComponent(self, param, itemType):
        self.addComponent(itemType)

    def paramRequestedRemove(self, parent, param):
        self.removeComponent(param.component())

    def setVisible(self, v):
        """Sets whether component controls are visible in the camera module.
        """
        self._visible = v
        for c in self.components:
            c.updateVisibility()

    def isVisible(self):
        return self._visible


class ScanProgramPreview(object):
    """Displays and animates the path of the scanner and timing of components.
    """
    def __init__(self, program):
        self.program = program
        self.canvas = None     # for displaying scan path
        self.timeplot = None   # plotwidget to display timeline

        self.path = None
        self.timeline = None
        self.spot = None
        self.masks = []

        self.rate = 0.1
        self.timer = Qt.QTimer()
        self.timer.timeout.connect(self.step)

        self.lastTime = None

    def clear(self):
        self.stop()
        self.clearTimeline()

    def stop(self):
        self.timer.stop()
        for item in self.path, self.spot:
            if item is not None and item.scene() is not None:
                item.scene().removeItem(item)

        if self.timeline is not None and self.timeline.scene() is not None:
            self.plot.removeItem(self.timeline)

        self.path = None
        self.timeline = None
        self.spot = None
        self.data = None
        self.laserMask = None

    def start(self, canvas, plot):
        """Add graphics items to *view* showing the path of the scanner.
        """
        self.clear()

        self.path = pg.PlotCurveItem()
        self.spot = Qt.QGraphicsEllipseItem(Qt.QRectF(-1, -1, 2, 2))
        self.spot.scale(1e-6, 1e-6)
        self.spot.setPen(pg.mkPen('y'))

        self.data = self.program.generatePositionArray()
        self.laserMask = self.program.generateLaserMask()
        self.lastTime = pg.ptime.time()
        self.index = 0
        self.sampleRate = self.program.sampleRate

        self.timeline = pg.InfiniteLine(angle=90)
        self.timeline.setZValue(100)

        if canvas is not None:
            canvas.addItem(self.path)
            canvas.addItem(self.spot)
        if plot is not None:
            self.plot = plot
            self.plotTimeline(plot)
            plot.addItem(self.timeline)

        self.timer.start(16)

    def setRate(self, rate):
        self.rate = rate

    def step(self):
        # decide how much to advance preview
        data = self.data
        now = pg.ptime.time()
        dt = (now - self.lastTime) * self.rate
        index = self.index + dt * self.sampleRate
        npts = data.shape[0]
        end = min(index, npts-1)
        va = data[:int(end)]

        self.index = index
        self.lastTime = now

        # draw path
        self.path.setData(va[:,0], va[:,1])
        self.timeline.setValue(end / self.sampleRate)
        self.spot.setPos(va[-1,0], va[-1,1])
        if self.laserMask[int(end)]:
            self.spot.setBrush(pg.mkBrush('y'))
        else:
            self.spot.setBrush(pg.mkBrush('k'))

        # Stop preview and delete path data if we reached the end
        if end >= npts-1:
            self.timer.stop()
            self.data = None
            self.laserMask = None

    def clearTimeline(self):
        for item in self.masks:
            scene = item.scene()
            if scene is not None:
                self.plot.removeItem(item)
        self.masks = []

    def plotTimeline(self, plot):
        """Create a timeline showing scan mirror usage by each program 
        component.
        """
        self.clearTimeline()
        numSamples = self.program.numSamples
        sampleRate = self.program.sampleRate
        components = self.program.components

        time = np.linspace(0, (numSamples-1) / sampleRate, numSamples)
        for i, component in enumerate(components):
            scanMask = component.scanMask()
            laserMask = component.laserMask()
            color = pg.mkColor((i, len(components)*1.3))
            fill = pg.mkColor(color)
            fill.setAlpha(50)
            plot.addLegend(offset=(-10, 10))
            item = plot.plot(time, scanMask, pen=color, fillLevel=0, fillBrush=fill, name=component.name)
            item.setZValue(i)
            self.masks.append(item)

            fill.setAlpha(100)
            item = plot.plot(time, laserMask, pen=None, fillLevel=0, fillBrush=fill)
            item.setZValue(i+0.5)
            self.masks.append(item)



class ScanProgramCtrlGroup(pTypes.GroupParameter):
    """
    Parameter tree used for generating ScanProgram
    
    """
    sigAddNewRequested = Qt.Signal(object, object)
    
    def __init__(self):
        opts = {
            'name': 'Program Controls',
            'type': 'group',
            'addText': "Add Control..",
            'addList': list(COMPONENTS.keys()),
            'autoIncrementName': True,
        }
        pTypes.GroupParameter.__init__(self, **opts)
    
    def addNew(self, typ):
        self.sigAddNewRequested.emit(self, typ)


