from PyQt4 import QtCore, QtGui
from Container import *
from DockDrop import *

class DockArea(Container, QtGui.QWidget, DockDrop):
    def __init__(self, temporary=False):
        Container.__init__(self, self)
        QtGui.QWidget.__init__(self)
        DockDrop.__init__(self, allowedAreas=['left', 'right', 'top', 'bottom'])
        self.layout = QtGui.QVBoxLayout()
        self.setLayout(self.layout)
        self.docks = {}
        self.topContainer = None
        self.raiseOverlay()
        self.temporary = temporary
        self.tempAreas = []
        
    def type(self):
        return "top"
        
    def addDock(self, dock, position='bottom', relativeTo=None):
        """Adds a dock to this area.
        position may be: bottom, top, left, right, over, under
        If relativeTo specifies an existing dock, the new dock is added adjacent to it"""
        
        ## Determine the container to insert this dock into.
        ## If there is no neighbor, then the container is the top.
        if relativeTo is None or relativeTo is self:
            if self.topContainer is None:
                container = self
                neighbor = None
            else:
                container = self.topContainer
                neighbor = None
        else:
            container = self.getContainer(relativeTo)
            neighbor = relativeTo
        
        ## Decide if the container we have is suitable.
        ## If not, insert a new container inside.
        neededContainer = {
            'bottom': 'vertical',
            'top': 'vertical',
            'left': 'horizontal',
            'right': 'horizontal',
            'above': 'tab',
            'below': 'tab'
        }[position]
        
        if neededContainer != container.type():
            if neighbor is None:
                container = self.addContainer(neededContainer, self.topContainer)
            else:
                container = self.addContainer(neededContainer, neighbor)
            
        ## Insert the new dock before/after its neighbor
        insertPos = {
            'bottom': 'after',
            'top': 'before',
            'left': 'before',
            'right': 'after',
            'above': 'before',
            'below': 'after'
        }[position]
        #print "request insert", dock, insertPos, neighbor
        container.insert(dock, insertPos, neighbor)
        dock.area = self
        
    def getContainer(self, obj):
        if obj is None:
            return self
        return obj.container()
        
    def addContainer(self, typ, obj):
        """Add a new container around obj"""
        if typ == 'vertical':
            new = VContainer(self)
        elif typ == 'horizontal':
            new = HContainer(self)
        elif typ == 'tab':
            new = TContainer(self)
        
        container = self.getContainer(obj)
        container.insert(new, 'before', obj)
        #print "Add container:", new, " -> ", container
        if obj is not None:
            new.insert(obj)
        self.raiseOverlay()
        return new
    
    def insert(self, new, pos, neighbor):
        self.layout.addWidget(new)
        self.topContainer = new
        new._container = self
        self.raiseOverlay()
        #print "Insert top:", new
        
    def count(self):
        if self.topContainer is None:
            return 0
        return 1
        
    def moveDock(self, dock, position, neighbor):
        old = dock.container()
        self.addDock(dock, position, neighbor)
        old.apoptose()
        
    #def paintEvent(self, ev):
        #self.drawDockOverlay()
        
    def resizeEvent(self, ev):
        self.resizeOverlay(self.size())
        
    def floatDock(self, dock):
        area = DockArea(temporary=True)
        self.tempAreas.append(area)
        area.resize(self.size())
        area.show()
        area.moveDock(dock, 'top', None)
        
        
            


        