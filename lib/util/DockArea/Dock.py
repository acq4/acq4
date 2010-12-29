from PyQt4 import QtCore, QtGui

from DockDrop import *
from VerticalLabel import *

class Dock(QtGui.QWidget, DockDrop):
    def __init__(self, name, area=None):
        QtGui.QWidget.__init__(self)
        DockDrop.__init__(self)
        self.area = area
        self.label = DockLabel(name, self)
        #self.label.setAlignment(QtCore.Qt.AlignHCenter)
        self.topLayout = QtGui.QGridLayout()
        self.topLayout.setContentsMargins(0, 0, 0, 0)
        self.topLayout.setSpacing(0)
        self.setLayout(self.topLayout)
        self.topLayout.addWidget(self.label, 0, 1)
        self.widgetArea = QtGui.QWidget()
        self.topLayout.addWidget(self.widgetArea, 1, 1)
        self.layout = QtGui.QGridLayout()
        self.widgetArea.setLayout(self.layout)
        self.widgets = []
        self.currentRow = 0
        self.titlePos = 'top'
        self.raiseOverlay()
        self.hStyle = """
        QWidget { 
            border: 1px solid #000; 
            border-radius: 5px; 
            border-top-left-radius: 0px; 
            border-top-right-radius: 0px; 
            border-top-width: 0px;
        }"""
        self.vStyle = """
        QWidget { 
            border: 1px solid #000; 
            border-radius: 5px; 
            border-top-left-radius: 0px; 
            border-bottom-left-radius: 0px; 
            border-left-width: 0px;
        }"""
        
        self.widgetArea.setStyleSheet(self.hStyle)

    def hideTitleBar(self):
        self.label.hide()
        
    def showTitleBar(self):
        self.label.show()

    def resizeEvent(self, ev):
        if self.titlePos == 'top' and self.width() > self.height()*1.5:
            self.label.setOrientation('vertical')
            self.topLayout.addWidget(self.label, 1, 0)
            self.titlePos = 'left'
            self.widgetArea.setStyleSheet(self.vStyle)
        elif self.titlePos == 'left' and self.width() <= self.height()*1.5:
            self.label.setOrientation('horizontal')
            self.topLayout.addWidget(self.label, 0, 1)
            self.titlePos = 'top'
            self.widgetArea.setStyleSheet(self.hStyle)
        self.resizeOverlay(self.size())

    def name(self):
        return self.label.text()

    def container(self):
        return self._container

    def addWidget(self, widget, row=None, col=0, rowspan=1, colspan=1):
        if row is None:
            row = self.currentRow
        self.currentRow = max(row+1, self.currentRow)
        self.widgets.append(widget)
        self.layout.addWidget(widget, row, col, rowspan, colspan)
        self.raiseOverlay()
        
        
    def startDrag(self):
        self.drag = QtGui.QDrag(self)
        mime = QtCore.QMimeData()
        #mime.setPlainText("asd")
        self.drag.setMimeData(mime)
        action = self.drag.exec_()
        
    def float(self):
        self.area.floatDock(self)
            
            
            
            
class DockLabel(VerticalLabel):
    def __init__(self, text, dock):
        self.marginLeft = 0
        self.fixedWidth = False
        VerticalLabel.__init__(self, text, orientation='horizontal')
        self.setAlignment(QtCore.Qt.AlignTop|QtCore.Qt.AlignHCenter)
        self.dock = dock
        self.updateStyle()

    def setTabPos(self, pos=False):
        if pos is False:
            self.marginLeft = 0
            self.fixedWidth = False
        else:
            self.marginLeft = pos
            self.fixedWidth = True
        self.updateStyle()
        self.update()

    def updateStyle(self):
        r = '3px'
        fg = '#fff'
        bg = '#66c'
        border = '#55B'
        
        if self.orientation == 'vertical':
            if self.fixedWidth:
                self.setSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Fixed)
            else:
                self.setSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
            self.vStyle = """QLabel { 
                background-color : %s; 
                color : %s; 
                border-top-right-radius: 0px; 
                border-top-left-radius: %s; 
                border-bottom-right-radius: 0px; 
                border-bottom-left-radius: %s; 
                border-width: 0px; 
                border-right: 2px solid %s;
                margin-bottom: %dpx;
            }""" % (bg, fg, r, r, border, self.marginLeft)
            self.setStyleSheet(self.vStyle)
        else:
            if self.fixedWidth:
                self.setSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Preferred)
            else:
                self.setSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
            self.hStyle = """QLabel { 
                background-color : %s; 
                color : %s; 
                border-top-right-radius: %s; 
                border-top-left-radius: %s; 
                border-bottom-right-radius: 0px; 
                border-bottom-left-radius: 0px; 
                border-width: 0px; 
                border-bottom: 2px solid %s;
                margin-left: %dpx;
            }""" % (bg, fg, r, r, border, self.marginLeft)
            self.setStyleSheet(self.hStyle)

    def setOrientation(self, o):
        VerticalLabel.setOrientation(self, o)
        self.updateStyle()

    def mousePressEvent(self, ev):
        if ev.button() == QtCore.Qt.LeftButton:
            self.pressPos = ev.pos()
            self.startedDrag = False
            ev.accept()
        
    def mouseMoveEvent(self, ev):
        if not self.startedDrag and (ev.pos() - self.pressPos).manhattanLength() > QtGui.QApplication.startDragDistance():
            self.dock.startDrag()
        ev.accept()
        #print ev.pos()
            
    def mouseReleaseEvent(self, ev):
        ev.accept()
        
    def mouseDoubleClickEvent(self, ev):
        if ev.button() == QtCore.Qt.LeftButton:
            self.dock.float()
            
    #def paintEvent(self, ev):
        #p = QtGui.QPainter(self)
        #p.setBrush(QtGui.QBrush(QtGui.QColor(100, 100, 200)))
        #p.setPen(QtGui.QPen(QtGui.QColor(50, 50, 100)))
        #p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        
        #VerticalLabel.paintEvent(self, ev)
            
            
            
#class DockLabel(QtGui.QWidget):
    #def __init__(self, text, dock):
        #QtGui.QWidget.__init__(self)
        #self._text = text
        #self.dock = dock
        #self.orientation = None
        #self.setOrientation('horizontal')
        
    #def text(self):
        #return self._text
        
    #def mousePressEvent(self, ev):
        #if ev.button() == QtCore.Qt.LeftButton:
            #self.pressPos = ev.pos()
            #self.startedDrag = False
            #ev.accept()
        
    #def mouseMoveEvent(self, ev):
        #if not self.startedDrag and (ev.pos() - self.pressPos).manhattanLength() > QtGui.QApplication.startDragDistance():
            #self.dock.startDrag()
        #ev.accept()
        ##print ev.pos()
            
    #def mouseReleaseEvent(self, ev):
        #ev.accept()
        
    #def mouseDoubleClickEvent(self, ev):
        #if ev.button() == QtCore.Qt.LeftButton:
            #self.dock.float()
            
    #def setOrientation(self, o):
        #if self.orientation == o:
            #return
        #self.orientation = o
        #self.update()
        #self.updateGeometry()
        
    #def paintEvent(self, ev):
        #p = QtGui.QPainter(self)
        #p.setBrush(QtGui.QBrush(QtGui.QColor(100, 100, 200)))
        #p.setPen(QtGui.QPen(QtGui.QColor(50, 50, 100)))
        #p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        
        #p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255)))
        
        #if self.orientation == 'vertical':
            #p.rotate(-90)
            #rgn = QtCore.QRect(-self.height(), 0, self.height(), self.width())
        #else:
            #rgn = self.rect()
        #align  = QtCore.Qt.AlignTop|QtCore.Qt.AlignHCenter
            
        #self.hint = p.drawText(rgn, align, self.text())
        #p.end()
        
        #if self.orientation == 'vertical':
            #self.setMaximumWidth(self.hint.height())
            #self.setMaximumHeight(16777215)
        #else:
            #self.setMaximumHeight(self.hint.height())
            #self.setMaximumWidth(16777215)

    #def sizeHint(self):
        #if self.orientation == 'vertical':
            #if hasattr(self, 'hint'):
                #return QtCore.QSize(self.hint.height(), self.hint.width())
            #else:
                #return QtCore.QSize(19, 50)
        #else:
            #if hasattr(self, 'hint'):
                #return QtCore.QSize(self.hint.width(), self.hint.height())
            #else:
                #return QtCore.QSize(50, 19)
