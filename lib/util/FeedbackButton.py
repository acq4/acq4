# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui

class FeedbackButton(QtGui.QPushButton):
    def __init__(self, *args):
        QtGui.QPushButton.__init__(self, *args)
        self.origStyle = None
        self.textTimer = QtCore.QTimer()
        self.textTimer.timeout.connect(self.restoreText)
    
    def feedback(self, success, message=None, tip=""):
        if success:
            self.success(message, tip)
        else:
            self.failure(message, tip)
    
    def success(self, message=None, tip=""):
        #print "success"
        self.startBlink("#0F0", message, tip)
        
    def failure(self, message=None, tip=""):
        #print "fail"
        self.startBlink("#F00", message, tip)

    def startBlink(self, color, message=None, tip=""):
        if self.origStyle is None:
            self.origStyle = self.styleSheet()
            self.origText = self.text()
        if message is not None:
            self.setText(message)
        self.setToolTip(tip)
        self.count = 0
        #self.indStyle = "QPushButton {border: 2px solid %s; border-radius: 5px}" % color
        self.indStyle = "QPushButton {background-color: %s}" % color
        self.borderOn()
        self.textTimer.start(2000)

    def borderOn(self):
        self.setStyleSheet(self.indStyle)
        QtCore.QTimer.singleShot(100, self.borderOff)
        
    def borderOff(self):
        self.setStyleSheet(self.origStyle)
        self.count += 1
        if self.count >= 2:
            return
        QtCore.QTimer.singleShot(30, self.borderOn)

    def restoreText(self):
        self.setText(self.origText)

if __name__ == '__main__':
    app = QtGui.QApplication([])
    win = QtGui.QMainWindow()
    btn = FeedbackButton("Button")
    fail = True
    def click():
        global fail
        fail = not fail
        if fail:
            btn.failure(message="FAIL.", tip="There was a failure. Get over it.")
        else:
            btn.success(message="Bueno!")
    btn.clicked.connect(click)
    win.setCentralWidget(btn)
    win.show()