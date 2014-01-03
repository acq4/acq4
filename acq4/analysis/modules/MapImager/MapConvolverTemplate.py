# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './acq4/analysis/modules/MapImager/MapConvolverTemplate.ui'
#
# Created: Tue Dec 24 01:49:13 2013
#      by: PyQt4 UI code generator 4.10
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
    def _fromUtf8(s):
        return s

try:
    _encoding = QtGui.QApplication.UnicodeUTF8
    def _translate(context, text, disambig):
        return QtGui.QApplication.translate(context, text, disambig, _encoding)
except AttributeError:
    def _translate(context, text, disambig):
        return QtGui.QApplication.translate(context, text, disambig)

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
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.label.setText(_translate("Form", "Spacing:", None))
        self.spacingSpin.setToolTip(_translate("Form", "Spacing of the grid that the map will be projected onto.", None))
        self.processBtn.setText(_translate("Form", "Process", None))
        self.tree.headerItem().setText(0, _translate("Form", "Parameter", None))
        self.tree.headerItem().setText(1, _translate("Form", "Method", None))
        self.tree.headerItem().setText(2, _translate("Form", "Sigma", None))
        self.tree.headerItem().setText(3, _translate("Form", "Interpolation type", None))
        self.tree.headerItem().setText(4, _translate("Form", "Remove", None))

from acq4.pyqtgraph.widgets.SpinBox import SpinBox
from pyqtgraph import TreeWidget
