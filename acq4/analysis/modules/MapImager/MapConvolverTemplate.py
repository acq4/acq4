# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'MapConvolverTemplate.ui'
#
# Created: Wed Mar 21 12:21:40 2012
#      by: PyQt4 UI code generator 4.9
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
    _fromUtf8 = lambda s: s

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName(_fromUtf8("Form"))
        Form.resize(504, 237)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setMargin(3)
        self.gridLayout.setSpacing(3)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setSpacing(1)
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.label = QtGui.QLabel(Form)
        self.label.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.label.setObjectName(_fromUtf8("label"))
        self.horizontalLayout.addWidget(self.label)
        self.spacingSpin = SpinBox(Form)
        self.spacingSpin.setObjectName(_fromUtf8("spacingSpin"))
        self.horizontalLayout.addWidget(self.spacingSpin)
        spacerItem = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.horizontalLayout.addItem(spacerItem)
        self.gridLayout.addLayout(self.horizontalLayout, 0, 0, 1, 1)
        self.processBtn = QtGui.QPushButton(Form)
        self.processBtn.setObjectName(_fromUtf8("processBtn"))
        self.gridLayout.addWidget(self.processBtn, 3, 0, 1, 1)
        self.tree = TreeWidget(Form)
        self.tree.setObjectName(_fromUtf8("tree"))
        self.tree.header().setDefaultSectionSize(120)
        self.tree.header().setStretchLastSection(True)
        self.gridLayout.addWidget(self.tree, 2, 0, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Spacing:", None, QtGui.QApplication.UnicodeUTF8))
        self.spacingSpin.setToolTip(QtGui.QApplication.translate("Form", "Spacing of the grid that the map will be projected onto.", None, QtGui.QApplication.UnicodeUTF8))
        self.processBtn.setText(QtGui.QApplication.translate("Form", "Process", None, QtGui.QApplication.UnicodeUTF8))
        self.tree.headerItem().setText(0, QtGui.QApplication.translate("Form", "Parameter", None, QtGui.QApplication.UnicodeUTF8))
        self.tree.headerItem().setText(1, QtGui.QApplication.translate("Form", "Method", None, QtGui.QApplication.UnicodeUTF8))
        self.tree.headerItem().setText(2, QtGui.QApplication.translate("Form", "Sigma", None, QtGui.QApplication.UnicodeUTF8))
        self.tree.headerItem().setText(3, QtGui.QApplication.translate("Form", "Interpolation type", None, QtGui.QApplication.UnicodeUTF8))
        self.tree.headerItem().setText(4, QtGui.QApplication.translate("Form", "Remove", None, QtGui.QApplication.UnicodeUTF8))

from pyqtgraph import TreeWidget
from pyqtgraph.widgets.SpinBox import SpinBox
