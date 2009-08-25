from PyQt4 import QtCore, QtGui

class AnalysisModule:
    def __init__(self, protoRunner):
        self.pr = protoRunner
        QtCore.QObject.connect(self.pr, QtCore.SIGNAL('newFrame'), self.newFrame)
        QtCore.QObject.connect(self.pr, QtCore.SIGNAL('protocolStarted'), self.protocolStarted)
        QtCore.QObject.connect(self.pr.taskThread, QtCore.SIGNAL('taskStarted'), self.taskStarted)
        
    def gui(self):
        return QtGui.QWidget()
        
    def newFrame(self, *args):
        print "NEW FRAME!"
        print args

    def protocolStarted(self, *args):
        print "protocolStarted!"
        
    def taskStarted(self, *args):
        print "protocolStarted!"
    
        