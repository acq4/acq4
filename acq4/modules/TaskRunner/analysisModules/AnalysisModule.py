# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.util import Qt
from pyqtgraph.WidgetGroup import WidgetGroup

class AnalysisModule(Qt.QWidget):
    def __init__(self, taskRunner):
        Qt.QWidget.__init__(self)
        self.pr = taskRunner
        self.pr.sigNewFrame.connect(self.newFrame)
        self.pr.sigPartialFrame.connect(self.newPartialFrame)
        self.pr.sigTaskSequenceStarted.connect(self.taskSequenceStarted)
        self.pr.sigTaskStarted.connect(self.taskStarted)
        self.pr.sigTaskFinished.connect(self.taskFinished)

    def postGuiInit(self):
        self.stateGroup = WidgetGroup(self)

    def newFrame(self, *args):
        pass
        #print "NEW FRAME!"
        #print args

    def newPartialFrame(self, frame):
        """Handle a partial frame while a task runs. Default: no-op.

        *frame* is {'params', 'cmd', 'result'} like newFrame's, but each device result is the live
        object the final frame will carry; read only its settled part (see its settlement()).
        """
        pass

    def taskStarted(self, *args):
        pass
        #print "taskStarted!"
        
    def taskFinished(self):
        pass
    
    def taskSequenceStarted(self, *args):
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
            self.pr.sigPartialFrame.disconnect(self.newPartialFrame)
        except TypeError:
            pass
        try:
            self.pr.sigTaskSequenceStarted.disconnect(self.taskSequenceStarted)
        except TypeError:
            pass
        try:
            self.pr.sigTaskStarted.disconnect(self.taskStarted)
        except TypeError:
            pass
        try:
            self.pr.sigTaskFinished.disconnect(self.taskFinished)
        except TypeError:
            pass
        
