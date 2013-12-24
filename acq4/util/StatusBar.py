

from PyQt4 import QtGui
from acq4.LogWindow import LogButton



class StatusBar(QtGui.QStatusBar):
    
    def __init__(self, parent=None):
        QtGui.QStatusBar.__init__(self, parent)
        
        btn = LogButton("Log")
        btn.setFixedHeight(21)
        btn.setFixedWidth(70)
        
        self.addPermanentWidget(btn)
        self.setFixedHeight(btn.height())
        self.layout().setSpacing(0)

    