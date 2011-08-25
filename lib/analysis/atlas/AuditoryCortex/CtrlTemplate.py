# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './lib/analysis/atlas/AuditoryCortex/CtrlTemplate.ui'
#
# Created: Wed Aug 17 13:49:51 2011
#      by: pyside-uic 0.2.11 running on PySide 1.0.5
#
# WARNING! All changes made in this file will be lost!

from PySide import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(280, 147)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setObjectName("gridLayout")
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 0, 0, 1, 1)
        self.slicePlaneCombo = QtGui.QComboBox(Form)
        self.slicePlaneCombo.setObjectName("slicePlaneCombo")
        self.slicePlaneCombo.addItem("")
        self.slicePlaneCombo.addItem("")
        self.slicePlaneCombo.addItem("")
        self.slicePlaneCombo.addItem("")
        self.gridLayout.addWidget(self.slicePlaneCombo, 0, 1, 1, 1)
        self.horizontalLayout_3 = QtGui.QHBoxLayout()
        self.horizontalLayout_3.setSpacing(0)
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.label_2 = QtGui.QLabel(Form)
        self.label_2.setObjectName("label_2")
        self.horizontalLayout_3.addWidget(self.label_2)
        self.hemisphereCombo = QtGui.QComboBox(Form)
        self.hemisphereCombo.setObjectName("hemisphereCombo")
        self.hemisphereCombo.addItem("")
        self.hemisphereCombo.addItem("")
        self.horizontalLayout_3.addWidget(self.hemisphereCombo)
        self.gridLayout.addLayout(self.horizontalLayout_3, 1, 0, 1, 2)
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setSpacing(0)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.photoCheck = QtGui.QCheckBox(Form)
        self.photoCheck.setObjectName("photoCheck")
        self.horizontalLayout.addWidget(self.photoCheck)
        self.drawingCheck = QtGui.QCheckBox(Form)
        self.drawingCheck.setChecked(True)
        self.drawingCheck.setObjectName("drawingCheck")
        self.horizontalLayout.addWidget(self.drawingCheck)
        self.flipCheck = QtGui.QCheckBox(Form)
        self.flipCheck.setObjectName("flipCheck")
        self.horizontalLayout.addWidget(self.flipCheck)
        self.gridLayout.addLayout(self.horizontalLayout, 2, 0, 1, 2)
        self.horizontalLayout_2 = QtGui.QHBoxLayout()
        self.horizontalLayout_2.setSpacing(0)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.label_3 = QtGui.QLabel(Form)
        self.label_3.setObjectName("label_3")
        self.horizontalLayout_2.addWidget(self.label_3)
        self.thicknessSpin = SpinBox(Form)
        self.thicknessSpin.setObjectName("thicknessSpin")
        self.horizontalLayout_2.addWidget(self.thicknessSpin)
        self.gridLayout.addLayout(self.horizontalLayout_2, 3, 0, 1, 2)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Slice Plane", None, QtGui.QApplication.UnicodeUTF8))
        self.slicePlaneCombo.setItemText(0, QtGui.QApplication.translate("Form", "Parasaggital", None, QtGui.QApplication.UnicodeUTF8))
        self.slicePlaneCombo.setItemText(1, QtGui.QApplication.translate("Form", "Coronal (AVCN-DCN)", None, QtGui.QApplication.UnicodeUTF8))
        self.slicePlaneCombo.setItemText(2, QtGui.QApplication.translate("Form", "Coronal (PVCN-DCN)", None, QtGui.QApplication.UnicodeUTF8))
        self.slicePlaneCombo.setItemText(3, QtGui.QApplication.translate("Form", "Horizontal (VCN)", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("Form", "Hemisphere", None, QtGui.QApplication.UnicodeUTF8))
        self.hemisphereCombo.setItemText(0, QtGui.QApplication.translate("Form", "Left", None, QtGui.QApplication.UnicodeUTF8))
        self.hemisphereCombo.setItemText(1, QtGui.QApplication.translate("Form", "Right", None, QtGui.QApplication.UnicodeUTF8))
        self.photoCheck.setText(QtGui.QApplication.translate("Form", "Photo", None, QtGui.QApplication.UnicodeUTF8))
        self.drawingCheck.setText(QtGui.QApplication.translate("Form", "Drawing", None, QtGui.QApplication.UnicodeUTF8))
        self.flipCheck.setText(QtGui.QApplication.translate("Form", "Flip", None, QtGui.QApplication.UnicodeUTF8))
        self.label_3.setText(QtGui.QApplication.translate("Form", "Thickness", None, QtGui.QApplication.UnicodeUTF8))

from SpinBox import SpinBox
