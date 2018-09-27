from __future__ import print_function


from acq4.util import Qt
from acq4.LogWindow import LogButton



class StatusBar(Qt.QStatusBar):
    
    def __init__(self, parent=None):
        Qt.QStatusBar.__init__(self, parent)
        
        btn = LogButton("Log")
        btn.setFixedHeight(21)
        btn.setFixedWidth(70)
        
        self.addPermanentWidget(btn)
        self.setFixedHeight(btn.height())
        self.layout().setSpacing(0)

    