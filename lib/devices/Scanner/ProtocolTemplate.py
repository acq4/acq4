# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ProtocolTemplate.ui'
#
# Created: Sun Sep 13 10:22:21 2009
#      by: PyQt4 UI code generator 4.5.4
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(504, 227)
        self.gridLayout_2 = QtGui.QGridLayout(Form)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.moduleCombo = QtGui.QComboBox(Form)
        self.moduleCombo.setObjectName("moduleCombo")
        self.gridLayout_2.addWidget(self.moduleCombo, 0, 1, 1, 1)
        self.listWidget = QtGui.QListWidget(Form)
        self.listWidget.setObjectName("listWidget")
        self.gridLayout_2.addWidget(self.listWidget, 0, 2, 8, 1)
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName("label")
        self.gridLayout_2.addWidget(self.label, 0, 0, 1, 1)
        self.displayCheck = QtGui.QCheckBox(Form)
        self.displayCheck.setObjectName("displayCheck")
        self.gridLayout_2.addWidget(self.displayCheck, 1, 1, 1, 1)
        self.gridLayout = QtGui.QGridLayout()
        self.gridLayout.setObjectName("gridLayout")
        self.minTimeSpin = QtGui.QDoubleSpinBox(Form)
        self.minTimeSpin.setObjectName("minTimeSpin")
        self.gridLayout.addWidget(self.minTimeSpin, 0, 0, 1, 1)
        self.minDistSpin = QtGui.QDoubleSpinBox(Form)
        self.minDistSpin.setObjectName("minDistSpin")
        self.gridLayout.addWidget(self.minDistSpin, 1, 0, 1, 1)
        self.label_4 = QtGui.QLabel(Form)
        self.label_4.setObjectName("label_4")
        self.gridLayout.addWidget(self.label_4, 1, 1, 1, 1)
        self.label_3 = QtGui.QLabel(Form)
        self.label_3.setObjectName("label_3")
        self.gridLayout.addWidget(self.label_3, 0, 1, 1, 1)
        self.gridLayout_2.addLayout(self.gridLayout, 2, 0, 1, 2)
        self.addOcclusionBtn = QtGui.QPushButton(Form)
        self.addOcclusionBtn.setObjectName("addOcclusionBtn")
        self.gridLayout_2.addWidget(self.addOcclusionBtn, 3, 1, 1, 1)
        self.addPointBtn = QtGui.QPushButton(Form)
        self.addPointBtn.setObjectName("addPointBtn")
        self.gridLayout_2.addWidget(self.addPointBtn, 3, 0, 1, 1)
        self.addGridBtn = QtGui.QPushButton(Form)
        self.addGridBtn.setObjectName("addGridBtn")
        self.gridLayout_2.addWidget(self.addGridBtn, 4, 0, 1, 1)
        self.recomputeBtn = QtGui.QPushButton(Form)
        self.recomputeBtn.setObjectName("recomputeBtn")
        self.gridLayout_2.addWidget(self.recomputeBtn, 5, 0, 1, 1)
        self.timeLabel = QtGui.QLabel(Form)
        self.timeLabel.setObjectName("timeLabel")
        self.gridLayout_2.addWidget(self.timeLabel, 5, 1, 1, 1)
        self.deleteBtn = QtGui.QPushButton(Form)
        self.deleteBtn.setObjectName("deleteBtn")
        self.gridLayout_2.addWidget(self.deleteBtn, 4, 1, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Camera Module:", None, QtGui.QApplication.UnicodeUTF8))
        self.displayCheck.setText(QtGui.QApplication.translate("Form", "display", None, QtGui.QApplication.UnicodeUTF8))
        self.label_4.setText(QtGui.QApplication.translate("Form", "Minimum distance", None, QtGui.QApplication.UnicodeUTF8))
        self.label_3.setText(QtGui.QApplication.translate("Form", "Minimum time", None, QtGui.QApplication.UnicodeUTF8))
        self.addOcclusionBtn.setText(QtGui.QApplication.translate("Form", "Add Occlusion", None, QtGui.QApplication.UnicodeUTF8))
        self.addPointBtn.setText(QtGui.QApplication.translate("Form", "Add Point", None, QtGui.QApplication.UnicodeUTF8))
        self.addGridBtn.setText(QtGui.QApplication.translate("Form", "Add Grid", None, QtGui.QApplication.UnicodeUTF8))
        self.recomputeBtn.setText(QtGui.QApplication.translate("Form", "Recompute", None, QtGui.QApplication.UnicodeUTF8))
        self.timeLabel.setText(QtGui.QApplication.translate("Form", "Total Time:", None, QtGui.QApplication.UnicodeUTF8))
        self.deleteBtn.setText(QtGui.QApplication.translate("Form", "Delete", None, QtGui.QApplication.UnicodeUTF8))

