# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from pyqtgraph.WidgetGroup import WidgetGroup

class AnalysisModule(QtGui.QWidget):
    def __init__(self, protoRunner):
        QtGui.QWidget.__init__(self)
        self.pr = protoRunner
        #QtCore.QObject.connect(self.pr, QtCore.SIGNAL('newFrame'), self.newFrame)
        self.pr.sigNewFrame.connect(self.newFrame)
        #QtCore.QObject.connect(self.pr, QtCore.SIGNAL('protocolStarted'), self.protocolStarted)
        self.pr.sigProtocolStarted.connect(self.protocolStarted)
        #QtCore.QObject.connect(self.pr, QtCore.SIGNAL('taskStarted'), self.taskStarted)
        self.pr.sigTaskStarted.connect(self.taskStarted)
        #QtCore.QObject.connect(self.pr, QtCore.SIGNAL('protocolFinished'), self.protocolFinished)
        self.pr.sigProtocolFinished.connect(self.protocolFinished)

    def postGuiInit(self):
        self.stateGroup = WidgetGroup(self)

    def newFrame(self, *args):
        pass
        #print "NEW FRAME!"
        #print args

    def protocolStarted(self, *args):
        pass
        #print "protocolStarted!"
        
    def protocolFinished(self):
        pass
    
    def taskStarted(self, *args):
        pass
        #print "taskStarted!"
    
    def saveState(self):
        return self.stateGroup.state()
        
    def restoreState(self, state):
        self.stateGroup.setState(state)
        
    def quit(self):
        try:
            self.pr.sigNewFrame.disconnect(self.newFrame)
        except TypeError:
            pass
        try:
            self.pr.sigProtocolStarted.disconnect(self.protocolStarted)
        except TypeError:
            pass
        try:
            self.pr.sigTaskStarted.disconnect(self.taskStarted)
        except TypeError:
            pass
        try:
            self.pr.sigProtocolFinished.disconnect(self.protocolFinished)
        except TypeError:
            pass
        
