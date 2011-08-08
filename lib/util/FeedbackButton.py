# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
class FeedbackButton(QtGui.QPushButton):
    
    ### For thread-safetyness
    sigCallSuccess = QtCore.Signal(object, object)
    sigCallFailure = QtCore.Signal(object, object)
    sigCallProcess = QtCore.Signal(object, object, object)
    
    def __init__(self, *args):
        QtGui.QPushButton.__init__(self, *args)
        self.origStyle = None
        self.origText = self.text()
        self.origStyle = self.styleSheet()
        self.origTip = self.toolTip()
        
        #self.textTimer = QtCore.QTimer()
        #self.tipTimer = QtCore.QTimer()
        #self.textTimer.timeout.connect(self.setText)
        #self.tipTimer.timeout.connect(self.setToolTip)
        
        self.sigCallSuccess.connect(self.success)
        self.sigCallFailure.connect(self.failure)
        self.sigCallProcess.connect(self.processing)
        

    def feedback(self, success, message=None, tip=""):
        """Calls success() or failure(). Threadsafe."""
        if success:
            self.success(message, tip)
        else:
            self.failure(message, tip)
    
    def success(self, message=None, tip=""):
        """Displays specified message on button and flashes button green to let user know action was successful. Threadsafe. """
        isGuiThread = QtCore.QThread.currentThread() == QtCore.QCoreApplication.instance().thread()
        if isGuiThread:
            self.setEnabled(True)
            #print "success"
            self.startBlink("#0F0", message, tip)
        else:
            self.sigCallSuccess.emit(message, tip)
            
    def failure(self, message=None, tip=""):
        """Displays specified message on button and flashes button red to let user know there was an error. Threadsafe. """
        isGuiThread = QtCore.QThread.currentThread() == QtCore.QCoreApplication.instance().thread()
        if isGuiThread:
            self.setEnabled(True)
            #print "fail"
            self.startBlink("#F00", message, tip)
        else:
            self.sigCallFailure.emit(message, tip)

    def processing(self, message="Processing..", tip="", processEvents=True):
        """Displays specified message on button to let user know the action is in progress. Threadsafe. """
        isGuiThread = QtCore.QThread.currentThread() == QtCore.QCoreApplication.instance().thread()
        if isGuiThread:
            self.setEnabled(False)
            self.setText(message, temporary=True)
            self.setToolTip(tip, temporary=True)
            if processEvents:
                QtGui.QApplication.processEvents()
        else:
            self.sigCallProcess.emit(message, tip, processEvents)
        
    def startBlink(self, color, message=None, tip=""):
        #if self.origStyle is None:
            #self.origStyle = self.styleSheet()
            #self.origText = self.text()
        if message is not None:
            self.setText(message, temporary=True)
        self.setToolTip(tip, temporary=True)
        self.count = 0
        #self.indStyle = "QPushButton {border: 2px solid %s; border-radius: 5px}" % color
        self.indStyle = "QPushButton {background-color: %s}" % color
        self.borderOn()
        QtCore.QTimer.singleShot(2000, self.setText)
        QtCore.QTimer.singleShot(10000, self.setToolTip)

    def borderOn(self):
        self.setStyleSheet(self.indStyle, temporary=True)
        QtCore.QTimer.singleShot(100, self.borderOff)
        
    def borderOff(self):
        self.setStyleSheet()
        self.count += 1
        if self.count >= 2:
            return
        QtCore.QTimer.singleShot(30, self.borderOn)
    
    def setText(self, text=None, temporary=False):
        if text is None:
            text = self.origText
        #print text
        QtGui.QPushButton.setText(self, text)
        if not temporary:
            self.origText = text

    def setToolTip(self, text=None, temporary=False):
        if text is None:
            text = self.origTip
        QtGui.QPushButton.setToolTip(self, text)
        if not temporary:
            self.origTip = text

    def setStyleSheet(self, style=None, temporary=False):
        if style is None:
            style = self.origStyle
        QtGui.QPushButton.setStyleSheet(self, style)
        if not temporary:
            self.origStyle = style


if __name__ == '__main__':
    import time
    app = QtGui.QApplication([])
    win = QtGui.QMainWindow()
    btn = FeedbackButton("Button")
    fail = True
    def click():
        btn.processing("Hold on..")
        time.sleep(2.0)
        
        global fail
        fail = not fail
        if fail:
            btn.failure(message="FAIL.", tip="There was a failure. Get over it.")
        else:
            btn.success(message="Bueno!")
    btn.clicked.connect(click)
    win.setCentralWidget(btn)
    win.show()