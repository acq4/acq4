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
    COMPONENTS[component.name] = component

for cType in ['step', 'line', 'rect', 'loop', 'ellipse', 'spiral']:
    mod = importlib.import_module('.' + cType, 'acq4.devices.Scanner.scan_program')
    clsName = cType.capitalize() + "ScanComponent"
    registerScanComponent(getattr(mod, clsName))



class ScanProgram:
    """
    ScanProgram encapsulates one or more laser scanning operations that are
    executed in sequence. 
    
    It provides the following services:
    
    * GUI for generating task commands and interactive representation of 
      command in camera module
    * Convert task command to mirror voltage command
    * Save / restore functionality
    * Masking arrays for controlling laser power
    * Extraction and analysis of imaging data generated during a scan
    
    Note that most of the functionality of ScanProgram is provided through 
    subclasses of ScanProgramComponent.
    """
    def __init__(self, dev):
        self.dev = dev
        self.components = []
        self.canvas = None
        self.sampleRate = None
        self.ctrlGroup = ScanProgramCtrlGroup()
        self.ctrlGroup.sigAddNewRequested.connect(self.paramRequestedNewComponent)
        self.ctrlGroup.sigChildRemoved.connect(self.paramRequestedRemove)
        
    def addComponent(self, component):
        """
        Add a new component to this program. May specify either a 
        ScanProgramComponent instance or a string indicating the type of a new
        component to create.
        """
        ## called when "Add Control.." combo is changed
        if isinstance(component, basestring):
            component = COMPONENTS[component](self)
        
        self.components.append(component)
        if self.sampleRate is not None:
            component.setSampleRate(*self.sampleRate)
        self.ctrlGroup.addChild(component.ctrlParameter(), autoIncrementName=True)
        if self.canvas is not None:
            for item in component.graphicsItems():
                self.canvas.addItem(item, None, [1, 1], 1000)

    def removeComponent(self, component):
        """
        Remove a component from this program.
        """
        self.components.remove(component)
        self.clearGraphicsItems(component)
        
    def ctrlParameter(self):
        """
        Return the control Parameter for this scan program. 
        This object may be displayed on a ParameterTree to provide the user
        control over the design of the program.
        """
        return self.ctrlGroup


    def setCanvas(self, canvas):
        """
        Set the canvas into which this scan program should add information
        about the layout of its components. The canvas must be any object
        with an `addItem(QGraphicsItem)` method, such as pyqtgraph.ViewBox.
        """
        self.canvas = canvas
        if canvas is None:
            self.clearGraphicsItems()
        else:
            for c in self.components:
                for i in c.graphicsItems():
                    c.addItem(i)

    def generateTask(self):
        """
        Return the list of component task commands. This is intended to be used
        as the value to the 'program' key in a Scanner task command. 
        """
        task = []
        for component in self.components:
            if component.isActive():
                task.append(component.generateTask())
        return task

    def clearGraphicsItems(self, component=None):
        if component is None:
            comps = self.components
        else:
            comps = [component]
        for c in comps:
            for i in c.graphicsItems():
                if i.scene() is not None:
                    i.scene().removeItem(i)

    def setSampleRate(self, rate, downsample):
        print "set sample rate:", rate, downsample
        self.sampleRate = (rate, downsample)
        for c in self.components:
            c.setSampleRate(rate, downsample)

    def mapToScanner(self, x, y):
        return self.dev.mapToScanner(x, y, self.cmd['laser'])
    
    @classmethod
    def generateVoltageArray(cls, dev, command):
        """LASER LOGO
        Turn a list of movement commands into arrays of x and y values.
        prg looks like:
        { 
            numPts: 10000,
            duration: 1.0,
            commands: [
               {'type': 'step', 'time': 0.0, 'pos': None),           ## start with step to "off" position 
               ('type': 'step', 'time': 0.2, 'pos': (1.3e-6, 4e-6)), ## step to the given location after 200ms
               ('type': 'line', 'time': (0.2, 0.205), 'pos': (1.3e-6, 4e-6))  ## 5ms sweep to the new position 
               ('type': 'step', 'time': 0.205, 'pos': None),           ## finish step to "off" position at 205ms
           ]
        }
        
        Commands we might add in the future:
          - circle
          - spiral
        # """
        # dt = command['duration'] / command['numPts']
        arr = np.zeros((2, command['numPts']))
        cmds = command['program']
        lastPos = None     
        lastValue = np.array(dev.getVoltage())
        lastStopInd = 0
        for i in range(len(cmds)):
            cmd = cmds[i]
            if cmd['active'] is False:
                continue
            
            # startInd = int(cmd['startTime'] / dt)
            # stopInd = int(cmd['endTime'] / dt)
            # if stopInd >= arr.shape[1]:
            #     raise HelpfulException('Scan Program duration is longer than protocol duration') 
            # arr[:,lastStopInd:startInd] = lastValue[:,np.newaxis]
            # cmd['startStopIndices'] = (startInd, stopInd)
            
            if cmd['type'] not in COMPONENTS:
                raise Exception('No registered scan component class named "%s".' % cmd['type'])
            
            component = COMPONENTS[cmd['type']]
            cmd['laser'] = command['laser']  # todo: should be handled individually by components
                                             # (because each component may be used with a different laser)
            startInd, stopInd = component.generateVoltageArray(arr, dev, cmd) #, startInd, stopInd)

            # fill unused space in the array from the last component to this one
            arr[:,lastStopInd:startInd] = lastValue[:,np.newaxis]
            # assert compStopInd <= stopInd
            # stopInd = compStopInd
            
            lastValue = arr[:,stopInd-1]
            lastStopInd = stopInd
            
            
        # arr[:,lastStopInd:] = lastValue[:,np.newaxis]
        
        return arr
    
    def preview(self, task):
        va = self.generateVoltageArray(self.dev, task)
        plt = getattr(self, 'previewPlot', pg.plot())
        plt.clear()
        plt.plot(va[0], va[1])

    def close(self):
        self.clearGraphicsItems()

    def paramRequestedNewComponent(self, param, itemType):
        self.addComponent(itemType)

    def paramRequestedRemove(self, parent, param):
        self.removeComponent(param.component())



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


