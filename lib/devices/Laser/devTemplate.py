# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'devTemplate.ui'
#
# Created: Mon Sep 26 13:45:42 2011
#      by: PyQt4 UI code generator 4.8.4
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
        Form.resize(486, 300)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setMargin(3)
        self.gridLayout.setSpacing(3)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.calibrationList = QtGui.QTreeWidget(Form)
        self.calibrationList.setRootIsDecorated(False)
        self.calibrationList.setItemsExpandable(False)
        self.calibrationList.setObjectName(_fromUtf8("calibrationList"))
        self.calibrationList.header().setStretchLastSection(True)
        self.gridLayout.addWidget(self.calibrationList, 0, 0, 1, 2)
        self.calibrateBtn = QtGui.QPushButton(Form)
        self.calibrateBtn.setObjectName(_fromUtf8("calibrateBtn"))
        self.gridLayout.addWidget(self.calibrateBtn, 1, 0, 1, 1)
        self.deleteBtn = QtGui.QPushButton(Form)
        self.deleteBtn.setObjectName(_fromUtf8("deleteBtn"))
        self.gridLayout.addWidget(self.deleteBtn, 1, 1, 1, 1)
        self.groupBox = QtGui.QGroupBox(Form)
        self.groupBox.setAlignment(QtCore.Qt.AlignCenter)
        self.groupBox.setObjectName(_fromUtf8("groupBox"))
        self.gridLayout_3 = QtGui.QGridLayout(self.groupBox)
        self.gridLayout_3.setMargin(0)
        self.gridLayout_3.setSpacing(0)
        self.gridLayout_3.setObjectName(_fromUtf8("gridLayout_3"))
        self.gridLayout_2 = QtGui.QGridLayout()
        self.gridLayout_2.setVerticalSpacing(0)
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
        self.scanDurationSpin = SpinBox(self.groupBox)
        self.scanDurationSpin.setMinimum(0.0)
        self.scanDurationSpin.setMaximum(100.0)
        self.scanDurationSpin.setProperty(_fromUtf8("value"), 1.0)
        self.scanDurationSpin.setObjectName(_fromUtf8("scanDurationSpin"))
        self.gridLayout_2.addWidget(self.scanDurationSpin, 2, 3, 1, 1)
        self.scanLabel = QtGui.QLabel(self.groupBox)
        self.scanLabel.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.scanLabel.setObjectName(_fromUtf8("scanLabel"))
        self.gridLayout_2.addWidget(self.scanLabel, 2, 2, 1, 1)
        self.label_2 = QtGui.QLabel(self.groupBox)
        self.label_2.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout_2.addWidget(self.label_2, 1, 0, 1, 1)
        self.microscopeCombo = QtGui.QComboBox(self.groupBox)
        self.microscopeCombo.setObjectName(_fromUtf8("microscopeCombo"))
        self.gridLayout_2.addWidget(self.microscopeCombo, 1, 1, 1, 1)
        self.label_3 = QtGui.QLabel(self.groupBox)
        self.label_3.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.gridLayout_2.addWidget(self.label_3, 2, 0, 1, 1)
        self.laserCombo = QtGui.QComboBox(self.groupBox)
        self.laserCombo.setObjectName(_fromUtf8("laserCombo"))
        self.gridLayout_2.addWidget(self.laserCombo, 2, 1, 1, 1)
        self.gridLayout_3.addLayout(self.gridLayout_2, 0, 0, 1, 1)
        self.gridLayout.addWidget(self.groupBox, 2, 0, 1, 2)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.calibrationList.headerItem().setText(0, QtGui.QApplication.translate("Form", "Objective", None, QtGui.QApplication.UnicodeUTF8))
        self.calibrationList.headerItem().setText(1, QtGui.QApplication.translate("Form", "Max. Power", None, QtGui.QApplication.UnicodeUTF8))
        self.calibrationList.headerItem().setText(2, QtGui.QApplication.translate("Form", "Min. Power", None, QtGui.QApplication.UnicodeUTF8))
        self.calibrationList.headerItem().setText(3, QtGui.QApplication.translate("Form", "Date", None, QtGui.QApplication.UnicodeUTF8))
        self.calibrateBtn.setText(QtGui.QApplication.translate("Form", "Calibrate", None, QtGui.QApplication.UnicodeUTF8))
        self.deleteBtn.setText(QtGui.QApplication.translate("Form", "Delete", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox.setTitle(QtGui.QApplication.translate("Form", "Calibration Parameters", None, QtGui.QApplication.UnicodeUTF8))
        self.scanDurationSpin.setSuffix(QtGui.QApplication.translate("Form", " s", None, QtGui.QApplication.UnicodeUTF8))
        self.scanLabel.setText(QtGui.QApplication.translate("Form", "Duration:", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("Form", "Microscope:", None, QtGui.QApplication.UnicodeUTF8))
        self.label_3.setText(QtGui.QApplication.translate("Form", "Power Meter:", None, QtGui.QApplication.UnicodeUTF8))

from SpinBox import SpinBox
