# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/analysis/atlas/AuditoryCortex/CtrlTemplate.ui'
#
# Created by: PyQt5 UI code generator 5.8.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(280, 147)
        self.gridLayout = QtWidgets.QGridLayout(Form)
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
        self.horizontalLayout_3 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_3.setSpacing(0)
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.label_2 = QtWidgets.QLabel(Form)
        self.label_2.setObjectName("label_2")
        self.horizontalLayout_3.addWidget(self.label_2)
        self.hemisphereCombo = QtWidgets.QComboBox(Form)
        self.hemisphereCombo.setObjectName("hemisphereCombo")
        self.hemisphereCombo.addItem("")
        self.hemisphereCombo.addItem("")
        self.horizontalLayout_3.addWidget(self.hemisphereCombo)
        self.gridLayout.addLayout(self.horizontalLayout_3, 1, 0, 1, 2)
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setSpacing(0)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.photoCheck = QtWidgets.QCheckBox(Form)
        self.photoCheck.setObjectName("photoCheck")
        self.horizontalLayout.addWidget(self.photoCheck)
        self.drawingCheck = QtWidgets.QCheckBox(Form)
        self.drawingCheck.setChecked(True)
        self.drawingCheck.setObjectName("drawingCheck")
        self.horizontalLayout.addWidget(self.drawingCheck)
        self.flipCheck = QtWidgets.QCheckBox(Form)
        self.flipCheck.setObjectName("flipCheck")
        self.horizontalLayout.addWidget(self.flipCheck)
        self.gridLayout.addLayout(self.horizontalLayout, 2, 0, 1, 2)
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_2.setSpacing(0)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.label_3 = QtWidgets.QLabel(Form)
        self.label_3.setObjectName("label_3")
        self.horizontalLayout_2.addWidget(self.label_3)
        self.thicknessSpin = SpinBox(Form)
        self.thicknessSpin.setObjectName("thicknessSpin")
        self.horizontalLayout_2.addWidget(self.thicknessSpin)
        self.gridLayout.addLayout(self.horizontalLayout_2, 3, 0, 1, 2)

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
        self.photoCheck.setText(_translate("Form", "Photo"))
        self.drawingCheck.setText(_translate("Form", "Drawing"))
        self.flipCheck.setText(_translate("Form", "Flip"))
        self.label_3.setText(_translate("Form", "Thickness"))

from acq4.pyqtgraph import SpinBox
