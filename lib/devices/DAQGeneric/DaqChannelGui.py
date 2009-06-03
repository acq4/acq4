# -*- coding: utf-8 -*-

import AOChannelTemplate, DOChannelTemplate, InputChannelTemplate

class DaqChannelGui(QtGui.QWidget):
    def __init__(self, parent, config, plot):
        QtGui.QWidget.__init__(self, parent)
        self.config = config
        self.plot = plot
        p.setCanvasBackground(QtGui.QColor(0,0,0))
        p.replot()
        
        self.stateGroup = WidgetGroup([])
        self.addStateChildren(self):
            
    def addStateChildren(obj):
        """Find all widgets which can be added to the state group and add them."""
        for c in obj.children():
            if self.stateGroup.acceptsType(c):
                self.stateGroup.addWidget(c, c.objectName())
            self.addStateChildren(c)
        
    def saveState(self):
        return self.stateGroup.state()
    
    def restoreState(self, state):
        return self.stateGroup.restoreState()

class OutputChannelGui(DaqChannelGui):
    def __init__(self, *args):
        DaqChannelGui.__init__(self, *args)
        
        daqDev = self.dev.getDAQName()
        daqUI = self.prot.getDevice(daqDev)
        
        if config['type'] == 'ao':
            self.ui = ProtocolAOTemplate.Ui_Form()
        elif config['type'] == 'do':
            self.ui = ProtocolDOTemplate.Ui_Form()
        else:
            raise Exception("Unrecognized channel type '%s'" % config['type'])
            
        self.ui.setupUi(self)
        
        
    
    def daqChanged(self, state):
        self.rate = state['rate']
        self.numPts = state['numPts']
        self.timeVals = numpy.linspace(0, float(self.numPts)/self.rate, self.numPts)
        self.updateWaves()

class InputChannelGui(DaqChannelGui):
    def __init__(self, *args):
        DaqChannelGui.__init__(self, *args)
        self.ui = ProtocolInputTemplate.Ui_Form()
        self.ui.setupUi(self)

