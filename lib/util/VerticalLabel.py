# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui

class VerticalLabel(QtGui.QLabel):
    def paintEvent(self, ev):
        p = QtGui.QPainter(self)
        p.rotate(-90)
        self.hint = p.drawText(QtCore.QRect(-self.height(), 0, self.height(), self.width()), QtCore.Qt.AlignLeft|QtCore.Qt.AlignVCenter, self.text())
        p.end()
        self.setMinimumWidth(self.hint.height())
        self.setMinimumHeight(self.hint.width())

    def sizeHint(self):
        if hasattr(self, 'hint'):
            return QtCore.QSize(self.hint.height(), self.hint.width())
        else:
            return QtCore.QSize(16, 50)


if __name__ == '__main__':
    app = QtGui.QApplication([])
    win = QtGui.QMainWindow()
    w = QtGui.QWidget()
    l = QtGui.QGridLayout()
    w.setLayout(l)
    
    l1 = VerticalLabel("text 1")
    l2 = VerticalLabel("text 2")
    l3 = VerticalLabel("text 3")
    l4 = VerticalLabel("text 4")
    l.addWidget(l1, 0, 0)
    l.addWidget(l2, 1, 1)
    l.addWidget(l3, 2, 2)
    l.addWidget(l4, 3, 3)
    win.setCentralWidget(w)
    win.show()