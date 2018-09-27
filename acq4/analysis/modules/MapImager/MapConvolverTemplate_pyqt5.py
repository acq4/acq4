# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/analysis/modules/MapImager/MapConvolverTemplate.ui'
#
# Created by: PyQt5 UI code generator 5.8.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(504, 237)
        self.gridLayout = QtWidgets.QGridLayout(Form)
        self.gridLayout.setContentsMargins(3, 3, 3, 3)
        self.gridLayout.setSpacing(3)
        self.gridLayout.setObjectName("gridLayout")
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setSpacing(1)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.label = QtWidgets.QLabel(Form)
        self.label.setAlignment(Qt.Qt.AlignRight|Qt.Qt.AlignTrailing|Qt.Qt.AlignVCenter)
        self.label.setObjectName("label")
        self.horizontalLayout.addWidget(self.label)
        self.spacingSpin = SpinBox(Form)
        self.spacingSpin.setObjectName("spacingSpin")
        self.horizontalLayout.addWidget(self.spacingSpin)
        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.horizontalLayout.addItem(spacerItem)
        self.gridLayout.addLayout(self.horizontalLayout, 0, 0, 1, 1)
        self.processBtn = QtWidgets.QPushButton(Form)
        self.processBtn.setObjectName("processBtn")
        self.gridLayout.addWidget(self.processBtn, 3, 0, 1, 1)
        self.tree = TreeWidget(Form)
        self.tree.setObjectName("tree")
        self.tree.header().setDefaultSectionSize(120)
        self.tree.header().setStretchLastSection(True)
        self.gridLayout.addWidget(self.tree, 2, 0, 1, 1)

        self.retranslateUi(Form)
        Qt.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        _translate = Qt.QCoreApplication.translate
        Form.setWindowTitle(_translate("Form", "Form"))
        self.label.setText(_translate("Form", "Spacing:"))
        self.spacingSpin.setToolTip(_translate("Form", "Spacing of the grid that the map will be projected onto."))
        self.processBtn.setText(_translate("Form", "Process"))
        self.tree.headerItem().setText(0, _translate("Form", "Parameter"))
        self.tree.headerItem().setText(1, _translate("Form", "Method"))
        self.tree.headerItem().setText(2, _translate("Form", "Sigma"))
        self.tree.headerItem().setText(3, _translate("Form", "Interpolation type"))
        self.tree.headerItem().setText(4, _translate("Form", "Remove"))

from acq4.pyqtgraph.widgets.SpinBox import SpinBox
from pyqtgraph import TreeWidget
