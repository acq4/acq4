from ..Qt import QtGui, QtCore
from .PathButton import PathButton

class GroupBox(QtGui.QGroupBox):
    """Subclass of QGroupBox that implements collapse handle.
    """
    sigCollapseChanged = QtCore.Signal(object)
    
    def __init__(self, *args):
        QtGui.QGroupBox.__init__(self, *args)
        
        self._collapsed = False
        
        self.closePath = QtGui.QPainterPath()
        self.closePath.moveTo(0, -1)
        self.closePath.lineTo(0, 1)
        self.closePath.lineTo(1, 0)
        self.closePath.lineTo(0, -1)
            
        self.openPath = QtGui.QPainterPath()
        self.openPath.moveTo(-1, 0)
        self.openPath.lineTo(1, 0)
        self.openPath.lineTo(0, 1)
        self.openPath.lineTo(-1, 0)
        
        self.collapseBtn = PathButton(path=self.openPath)
        self.collapseBtn.setPen('k')
        self.collapseBtn.setBrush('w')
        self.collapseBtn.setParent(self)
        self.collapseBtn.move(3, 3)
        self.collapseBtn.resize(12, 12)
        self.collapseBtn.setFlat(True)
        
        self.collapseBtn.clicked.connect(self.toggleCollapsed)
        
    def toggleCollapsed(self):
        self.setCollapsed(not self._collapsed)

    def collapsed(self):
        return self._collapsed
    
    def setCollapsed(self, c):
        if c == self._collapsed:
            return
        
        if c is True:
            self.collapseBtn.setPath(self.closePath)
        elif c is False:
            self.collapseBtn.setPath(self.openPath)
        else:
            raise TypeError("Invalid argument %r; must be bool." % c)
        
        for ch in self.children():
            if isinstance(ch, QtGui.QWidget) and ch is not self.collapseBtn:
                ch.setVisible(not c)
        
        self._collapsed = c
        self.sigCollapseChanged.emit(c)
        
    def widgetGroupInterface(self):
        return (self.sigCollapseChanged, 
                GroupBox.collapsed, 
                GroupBox.setCollapsed, 
                True)
