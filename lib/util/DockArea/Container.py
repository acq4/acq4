from PyQt4 import QtCore, QtGui


class Container:
    def __init__(self, area):
        self.area = area
        self._container = None
        
    def container(self):
        return self._container
        
    def type(self):
        return None

    def insert(self, new, pos=None, neighbor=None):
        if not isinstance(new, list):
            new = [new]
        if neighbor is None:
            if pos == 'before':
                index = 0
            else:
                index = self.count()
        else:
            index = self.indexOf(neighbor)
            if index == -1:
                index = 0
            if pos == 'after':
                index += 1
                
        for n in new:
            #print "insert", n, " -> ", self, index
            self._insertItem(n, index)
            index += 1
            n._container = self
            
    def apoptose(self):
        ##if there is only one item in this container, disappear.
        if self.count() == 0:
            self.setParent(None)
            #print "Removing container", self
        if self.count() == 1:
            self.container().insert(self.widget(0), 'before', self)
            self.setParent(None)
            #print "Removing container", self


class SplitContainer(Container, QtGui.QSplitter):
    def __init__(self, area, orientation):
        QtGui.QSplitter.__init__(self)
        self.setOrientation(orientation)
        Container.__init__(self, area)
        
    def _insertItem(self, item, index):
        self.insertWidget(index, item)
        item.allowedAreas = ['center', 'right', 'left', 'top', 'bottom']
        

class HContainer(SplitContainer):
    def __init__(self, area):
        SplitContainer.__init__(self, area, QtCore.Qt.Horizontal)
        
    def type(self):
        return 'horizontal'

class VContainer(SplitContainer):
    def __init__(self, area):
        SplitContainer.__init__(self, area, QtCore.Qt.Vertical)
        
    def type(self):
        return 'vertical'

class TContainer(Container, QtGui.QTabWidget):
    def __init__(self, area):
        QtGui.QTabWidget.__init__(self)
        Container.__init__(self, area)

    def _insertItem(self, item, index):
        self.insertTab(index, item, item.name())
        item.allowedAreas = ['center']
        
        
    def type(self):
        return 'tab'
