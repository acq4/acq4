# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/analysis/modules/AtlasBuilder/ctrlTemplate.ui'
#
# Created by: PyQt5 UI code generator 5.8.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(170, 179)
        self.gridLayout = QtWidgets.QGridLayout(Form)
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName("gridLayout")
        self.groupBox = QtWidgets.QGroupBox(Form)
        self.groupBox.setObjectName("groupBox")
        self.gridLayout_2 = QtWidgets.QGridLayout(self.groupBox)
        self.gridLayout_2.setContentsMargins(0, 0, 0, 0)
        self.gridLayout_2.setSpacing(0)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.label = QtWidgets.QLabel(self.groupBox)
        self.label.setObjectName("label")
        self.gridLayout_2.addWidget(self.label, 0, 0, 1, 1)
        self.valueSpin = QtWidgets.QSpinBox(self.groupBox)
        self.valueSpin.setMaximum(255)
        self.valueSpin.setObjectName("valueSpin")
        self.gridLayout_2.addWidget(self.valueSpin, 0, 1, 1, 1)
        self.label_2 = QtWidgets.QLabel(self.groupBox)
        self.label_2.setObjectName("label_2")
        self.gridLayout_2.addWidget(self.label_2, 1, 0, 1, 1)
        self.labelText = QtWidgets.QLineEdit(self.groupBox)
        self.labelText.setObjectName("labelText")
        self.gridLayout_2.addWidget(self.labelText, 1, 1, 1, 1)
        self.label_3 = QtWidgets.QLabel(self.groupBox)
        self.label_3.setObjectName("label_3")
        self.gridLayout_2.addWidget(self.label_3, 2, 0, 1, 1)
        self.colorBtn = ColorButton(self.groupBox)
        self.colorBtn.setText("")
        self.colorBtn.setObjectName("colorBtn")
        self.gridLayout_2.addWidget(self.colorBtn, 2, 1, 1, 1)
        self.gridLayout.addWidget(self.groupBox, 0, 0, 1, 2)
        self.label_4 = QtWidgets.QLabel(Form)
        self.label_4.setObjectName("label_4")
        self.gridLayout.addWidget(self.label_4, 1, 0, 1, 1)
        self.penSizeSpin = QtWidgets.QSpinBox(Form)
        self.penSizeSpin.setMinimum(1)
        self.penSizeSpin.setProperty("value", 1)
        self.penSizeSpin.setObjectName("penSizeSpin")
        self.gridLayout.addWidget(self.penSizeSpin, 1, 1, 1, 1)
        spacerItem = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem, 2, 0, 1, 1)

        self.retranslateUi(Form)
        Qt.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        _translate = Qt.QCoreApplication.translate
        Form.setWindowTitle(_translate("Form", "Form"))
        self.groupBox.setTitle(_translate("Form", "Labels"))
        self.label.setText(_translate("Form", "Value"))
        self.label_2.setText(_translate("Form", "Label"))
        self.label_3.setText(_translate("Form", "Color"))
        self.label_4.setText(_translate("Form", "Pen Size"))

from acq4.pyqtgraph.ColorButton import ColorButton
