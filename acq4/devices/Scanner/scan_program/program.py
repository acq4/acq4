# -*- coding: utf-8 -*-
import numpy as np
from collections import OrderedDict
import importlib

import acq4.pyqtgraph as pg
from acq4.util.HelpfulException import HelpfulException
import acq4.pyqtgraph.parametertree.parameterTypes as pTypes
from acq4.pyqtgraph.parametertree import Parameter, ParameterTree, ParameterItem, registerParameterType
from acq4.pyqtgraph import QtGui, QtCore


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
        
        self.sampleRate = None
        self.numSamples = None
        self.downsample = None
        
        self.ctrlGroup = ScanProgramCtrlGroup()  # used to display GUI for components
        self.ctrlGroup.sigAddNewRequested.connect(self.paramRequestedNewComponent)
        self.ctrlGroup.sigChildRemoved.connect(self.paramRequestedRemove)

        self.previewItems = []  # graphics items used to preview the program
        self.previewTimer = QtCore.QTimer()
        self.previewTimer.timeout.connect(self.previewStep)
        self.previewData = {}

        self._visible = True  # whether graphics items should be displayed
        
    def addComponent(self, component):
        """Add a new component to this program. May specify either a 
        ScanProgramComponent instance or a string indicating the type of a new
        component to create.
        
        For supported component types, see the COMPONENTS global variable. This
        may also be used to install new component types at runtime.
        """
        ## called when "Add Control.." combo is changed
        if isinstance(component, basestring):
            component = COMPONENTS[component](self)
        
        self.ctrlGroup.addChild(component.ctrlParameter(), autoIncrementName=True)
        if self.canvas is not None:
            for item in component.graphicsItems():
                self.canvas.addItem(item, None, [1, 1], 1000)
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
        self.clearPreview()
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
        lastPos = None
        if _voltage:
            lastValue = np.array(self.scanner.getVoltage())
        else:
            lastValue = np.array([np.nan, np.nan])
        lastStopInd = 0
        
        for component in self.components:
            if not component.isActive():
                continue
            
            if _voltage:
                startInd, stopInd = component.generateVoltageArray(arr)
            else:
                startInd, stopInd = component.generatePositionArray(arr)

            # fill unused space in the array from the last component to this one
            arr[lastStopInd:startInd] = lastValue[np.newaxis, :]
            
            lastValue = arr[stopInd-1]
            lastStopInd = stopInd
            
        return arr
    
    def close(self):
        self.clearGraphicsItems()

    def paramRequestedNewComponent(self, param, itemType):
        self.addComponent(itemType)

    def paramRequestedRemove(self, parent, param):
        self.removeComponent(param.component())

    def plotTimeline(self, plot):
        """Create a timeline showing scan mirror usage by each program 
        component.
        """
        
        time = np.linspace(0, (self.numSamples-1) / self.sampleRate, self.numSamples)
        for i, component in enumerate(self.components):
            scanMask = component.scanMask()
            laserMask = component.laserMask()
            color = pg.mkColor((i, len(self.components)*1.3))
            fill = pg.mkColor(color)
            fill.setAlpha(50)
            plot.addLegend(offset=(-10, 10))
            item = plot.plot(time, scanMask, pen=color, fillLevel=0, fillBrush=fill, name=component.name)
            item.setZValue(i)
            fill.setAlpha(100)
            item = plot.plot(time, laserMask, pen=None, fillLevel=0, fillBrush=fill)
            item.setZValue(i+0.5)
            legend = pg.LegendItem()

    def clearPreview(self):
        for item in self.previewItems:
            scene = item.scene()
            if scene is not None:
                scene.removeItem(item)
        self.previewItems = []
        self.previewTimer.stop()

    def preview(self, view, rate=0.1):
        """Add graphics items to *view* showing the path of the scanner.
        """
        self.clearPreview()
        path = pg.PlotCurveItem()
        self.previewData = {
            'path': path,
            'data': self.generatePositionArray(),
            'lastTime': pg.ptime.time(),
            'rate': rate,
            'index': 0,
            'sampleRate': self.sampleRate,
        }
        self.previewItems.append(path)
        view.addItem(path)
        self.previewTimer.start(16)

    def setPreviewRate(self, rate):
        self.previewData['rate'] = rate

    def previewStep(self):
        # decide how much to advance preview
        data = self.previewData
        now = pg.ptime.time()
        dt = (now - data['lastTime']) * data['rate']
        index = data['index'] + dt * data['sampleRate']
        npts = data['data'].shape[0]
        end = min(index, npts)
        va = data['data'][:end]

        data['index'] = index
        data['lastTime'] = now

        # draw path
        path = data['path']
        path.setData(va[:,0], va[:,1])

        # Stop preview and delete path data if we reached the end
        if end >= npts-1:
            self.previewTimer.stop()
            data['data'] = None

    def setVisible(self, v):
        """Sets whether component controls are visible in the camera module.
        """
        self._visible = v
        for c in self.components:
            c.updateVisibility()

    def isVisible(self):
        return self._visible


class ScanProgramCtrlGroup(pTypes.GroupParameter):
    """
    Parameter tree used for generating ScanProgram
    
    """
    sigAddNewRequested = QtCore.Signal(object, object)
    
    def __init__(self):
        opts = {
            'name': 'Program Controls',
            'type': 'group',
            'addText': "Add Control..",
            'addList': COMPONENTS.keys(),
            'autoIncrementName': True,
        }
        pTypes.GroupParameter.__init__(self, **opts)
    
    def addNew(self, typ):
        self.sigAddNewRequested.emit(self, typ)


