from PyQt4 import QtCore, QtGui


class Container:
    def __init__(self, area):
        self.area = area
        self._container = None
        
    def container(self):
        return self._container
        
    def containerChanged(self, c):
        self._container = c


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
            n.containerChanged(self)
            
    def apoptose(self, propagate=True):
        ##if there is only one (or zero) item in this container, disappear.
        cont = self._container
        c = self.count()
        if c > 1:
            return
        if self.count() == 1:  ## if there is one item, give it to the parent container (unless this is the top)
            if self is self.area.topContainer:
                return
            self.container().insert(self.widget(0), 'before', self)
        #print "apoptose:", self
        self.close()
        if propagate and cont is not None:
            cont.apoptose()
        
    def close(self):
        self.area = None
        self._container = None
        self.setParent(None)
        



class SplitContainer(Container, QtGui.QSplitter):
    def __init__(self, area, orientation):
        QtGui.QSplitter.__init__(self)
        self.setOrientation(orientation)
        Container.__init__(self, area)
        
    def _insertItem(self, item, index):
        self.insertWidget(index, item)
        
    def saveState(self):
        sizes = self.sizes()
        if all([x == 0 for x in sizes]):
            sizes = [10] * len(sizes)
        return {'sizes': sizes}
        #s = str(QtGui.QSplitter.saveState(self).toPercentEncoding())
        #return {'state': s}
        
    def restoreState(self, state):
        #self.setSizes(state['sizes'])
        #QtGui.QSplitter.restoreState(self, QtCore.QByteArray.fromPercentEncoding(state['state']))
        #if self.count() > 0:   ## make sure at least one item is not collapsed
            #for i in self.sizes():
                #if i > 0:
                    #return
            #w.setSizes([50] * self.count())
        sizes = state['sizes']
        #self.setSizes([10] * len(sizes))
        self.setSizes(sizes)
        for i in range(len(sizes)):
            self.setStretchFactor(i, sizes[i])

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

class TContainer(Container, QtGui.QWidget):
    def __init__(self, area):
        QtGui.QWidget.__init__(self)
        Container.__init__(self, area)
        self.layout = QtGui.QGridLayout()
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0,0,0,0)
        self.setLayout(self.layout)
        
        self.hTabLayout = QtGui.QHBoxLayout()
        self.hTabBox = QtGui.QWidget()
        self.hTabBox.setLayout(self.hTabLayout)
        self.hTabLayout.setSpacing(2)
        self.hTabLayout.setContentsMargins(0,0,0,0)
        self.layout.addWidget(self.hTabBox, 0, 1)

        self.stack = QtGui.QStackedWidget()
        self.layout.addWidget(self.stack, 1, 1)

        self.setLayout(self.layout)
        for n in ['count', 'widget', 'indexOf']:
            setattr(self, n, getattr(self.stack, n))


    def _insertItem(self, item, index):
        self.stack.insertWidget(index, item)
        #print "take lebel"
        self.hTabLayout.insertWidget(index, item.label)
        QtCore.QObject.connect(item.label, QtCore.SIGNAL('clicked'), self.tabClicked)
        self.tabClicked(item.label)
        
    def tabClicked(self, tab, ev=None):
        if ev is None or ev.button() == QtCore.Qt.LeftButton:
            for i in range(self.count()):
                w = self.widget(i)
                if w is tab.dock:
                    w.label.setDim(False)
                    self.stack.setCurrentIndex(i)
                else:
                    w.label.setDim(True)
        
    def type(self):
        return 'tab'

    def saveState(self):
        return {'index': self.stack.currentIndex()}
        
    def restoreState(self, state):
        self.stack.setCurrentIndex(state['index'])
        
        