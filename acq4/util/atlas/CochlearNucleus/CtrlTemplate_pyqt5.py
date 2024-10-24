# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/analysis/atlas/CochlearNucleus/CtrlTemplate.ui'
#
# Created by: PyQt5 UI code generator 5.8.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(228, 75)
        self.gridLayout = QtWidgets.QGridLayout(Form)
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.gridLayout.setVerticalSpacing(0)
        self.gridLayout.setObjectName("gridLayout")
        self.label = QtWidgets.QLabel(Form)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 0, 0, 1, 1)
        self.slicePlaneCombo = QtWidgets.QComboBox(Form)
        self.slicePlaneCombo.setObjectName("slicePlaneCombo")
        self.slicePlaneCombo.addItem("")
        self.slicePlaneCombo.addItem("")
        self.slicePlaneCombo.addItem("")
        self.slicePlaneCombo.addItem("")
        self.gridLayout.addWidget(self.slicePlaneCombo, 0, 1, 1, 1)
        self.label_2 = QtWidgets.QLabel(Form)
        self.label_2.setObjectName("label_2")
        self.gridLayout.addWidget(self.label_2, 1, 0, 1, 1)
        self.hemisphereCombo = QtWidgets.QComboBox(Form)
        self.hemisphereCombo.setObjectName("hemisphereCombo")
        self.hemisphereCombo.addItem("")
        self.hemisphereCombo.addItem("")
        self.gridLayout.addWidget(self.hemisphereCombo, 1, 1, 1, 1)
        self.label_3 = QtWidgets.QLabel(Form)
        self.label_3.setObjectName("label_3")
        self.gridLayout.addWidget(self.label_3, 3, 0, 1, 1)
        self.thicknessSpin = SpinBox(Form)
        self.thicknessSpin.setObjectName("thicknessSpin")
        self.gridLayout.addWidget(self.thicknessSpin, 3, 1, 1, 1)
        self.photoCheck = QtWidgets.QCheckBox(Form)
        self.photoCheck.setObjectName("photoCheck")
        self.gridLayout.addWidget(self.photoCheck, 2, 0, 1, 1)
        self.drawingCheck = QtWidgets.QCheckBox(Form)
        self.drawingCheck.setChecked(True)
        self.drawingCheck.setObjectName("drawingCheck")
        self.gridLayout.addWidget(self.drawingCheck, 2, 1, 1, 1)

        self.retranslateUi(Form)
        Qt.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        _translate = Qt.QCoreApplication.translate
        Form.setWindowTitle(_translate("Form", "Form"))
        self.label.setText(_translate("Form", "Slice Plane"))
        self.slicePlaneCombo.setItemText(0, _translate("Form", "Parasaggital"))
        self.slicePlaneCombo.setItemText(1, _translate("Form", "Coronal (AVCN-DCN)"))
        self.slicePlaneCombo.setItemText(2, _translate("Form", "Coronal (PVCN-DCN)"))
        self.slicePlaneCombo.setItemText(3, _translate("Form", "Horizontal (VCN)"))
        self.label_2.setText(_translate("Form", "Hemisphere"))
        self.hemisphereCombo.setItemText(0, _translate("Form", "Left"))
        self.hemisphereCombo.setItemText(1, _translate("Form", "Right"))
        self.label_3.setText(_translate("Form", "Thickness"))
        self.photoCheck.setText(_translate("Form", "Photo"))
        self.drawingCheck.setText(_translate("Form", "Drawing"))

from pyqtgraph.SpinBox import SpinBox
