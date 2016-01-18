# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'cameraModTemplate.ui'
#
# Created by: PyQt4 UI code generator 4.11.4
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
        Form.resize(209, 188)
        self.gridLayout_3 = QtGui.QGridLayout(Form)
        self.gridLayout_3.setMargin(0)
        self.gridLayout_3.setSpacing(0)
        self.gridLayout_3.setObjectName(_fromUtf8("gridLayout_3"))
        self.groupBox = QtGui.QGroupBox(Form)
        self.groupBox.setObjectName(_fromUtf8("groupBox"))
        self.gridLayout = QtGui.QGridLayout(self.groupBox)
        self.gridLayout.setMargin(3)
        self.gridLayout.setSpacing(3)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.setCenterBtn = QtGui.QPushButton(self.groupBox)
        self.setCenterBtn.setCheckable(True)
        self.setCenterBtn.setObjectName(_fromUtf8("setCenterBtn"))
        self.gridLayout.addWidget(self.setCenterBtn, 2, 0, 1, 1)
        self.autoCalibrateBtn = QtGui.QPushButton(self.groupBox)
        self.autoCalibrateBtn.setObjectName(_fromUtf8("autoCalibrateBtn"))
        self.gridLayout.addWidget(self.autoCalibrateBtn, 3, 0, 1, 1)
        self.getRefBtn = QtGui.QPushButton(self.groupBox)
        self.getRefBtn.setObjectName(_fromUtf8("getRefBtn"))
        self.gridLayout.addWidget(self.getRefBtn, 3, 1, 1, 1)
        self.setOrientationBtn = QtGui.QPushButton(self.groupBox)
        self.setOrientationBtn.setCheckable(True)
        self.setOrientationBtn.setObjectName(_fromUtf8("setOrientationBtn"))
        self.gridLayout.addWidget(self.setOrientationBtn, 2, 1, 1, 1)
        self.gridLayout_3.addWidget(self.groupBox, 1, 0, 1, 1)
        self.groupBox_2 = QtGui.QGroupBox(Form)
        self.groupBox_2.setObjectName(_fromUtf8("groupBox_2"))
        self.gridLayout_2 = QtGui.QGridLayout(self.groupBox_2)
        self.gridLayout_2.setMargin(3)
        self.gridLayout_2.setSpacing(3)
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
        self.homeBtn = QtGui.QPushButton(self.groupBox_2)
        self.homeBtn.setObjectName(_fromUtf8("homeBtn"))
        self.gridLayout_2.addWidget(self.homeBtn, 1, 0, 1, 1)
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.slowRadio = QtGui.QRadioButton(self.groupBox_2)
        self.slowRadio.setChecked(True)
        self.slowRadio.setObjectName(_fromUtf8("slowRadio"))
        self.horizontalLayout.addWidget(self.slowRadio)
        self.fastRadio = QtGui.QRadioButton(self.groupBox_2)
        self.fastRadio.setObjectName(_fromUtf8("fastRadio"))
        self.horizontalLayout.addWidget(self.fastRadio)
        self.gridLayout_2.addLayout(self.horizontalLayout, 0, 0, 1, 3)
        self.setTargetBtn = QtGui.QPushButton(self.groupBox_2)
        self.setTargetBtn.setCheckable(True)
        self.setTargetBtn.setObjectName(_fromUtf8("setTargetBtn"))
        self.gridLayout_2.addWidget(self.setTargetBtn, 6, 0, 1, 1)
        self.searchBtn = QtGui.QPushButton(self.groupBox_2)
        self.searchBtn.setMaximumSize(QtCore.QSize(70, 16777215))
        self.searchBtn.setObjectName(_fromUtf8("searchBtn"))
        self.gridLayout_2.addWidget(self.searchBtn, 1, 1, 1, 1)
        self.idleBtn = QtGui.QPushButton(self.groupBox_2)
        self.idleBtn.setMaximumSize(QtCore.QSize(50, 16777215))
        self.idleBtn.setObjectName(_fromUtf8("idleBtn"))
        self.gridLayout_2.addWidget(self.idleBtn, 1, 2, 1, 1)
        self.targetBtn = QtGui.QPushButton(self.groupBox_2)
        self.targetBtn.setEnabled(False)
        self.targetBtn.setMaximumSize(QtCore.QSize(50, 16777215))
        self.targetBtn.setObjectName(_fromUtf8("targetBtn"))
        self.gridLayout_2.addWidget(self.targetBtn, 7, 2, 1, 1)
        self.aboveTargetBtn = QtGui.QPushButton(self.groupBox_2)
        self.aboveTargetBtn.setObjectName(_fromUtf8("aboveTargetBtn"))
        self.gridLayout_2.addWidget(self.aboveTargetBtn, 6, 1, 1, 2)
        self.approachBtn = QtGui.QPushButton(self.groupBox_2)
        self.approachBtn.setEnabled(False)
        self.approachBtn.setMaximumSize(QtCore.QSize(70, 16777215))
        self.approachBtn.setObjectName(_fromUtf8("approachBtn"))
        self.gridLayout_2.addWidget(self.approachBtn, 7, 1, 1, 1)
        self.gridLayout_3.addWidget(self.groupBox_2, 0, 0, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.groupBox.setTitle(_translate("Form", "Calibration", None))
        self.setCenterBtn.setText(_translate("Form", "Set center", None))
        self.autoCalibrateBtn.setText(_translate("Form", "Auto calibrate", None))
        self.getRefBtn.setText(_translate("Form", "Get ref. frames", None))
        self.setOrientationBtn.setText(_translate("Form", "Set orientation", None))
        self.groupBox_2.setTitle(_translate("Form", "Set points", None))
        self.homeBtn.setText(_translate("Form", "Home", None))
        self.slowRadio.setText(_translate("Form", "slow", None))
        self.fastRadio.setText(_translate("Form", "fast", None))
        self.setTargetBtn.setText(_translate("Form", "Set Target", None))
        self.searchBtn.setText(_translate("Form", "Search", None))
        self.idleBtn.setText(_translate("Form", "Idle", None))
        self.targetBtn.setText(_translate("Form", "Target", None))
        self.aboveTargetBtn.setText(_translate("Form", "Above Target", None))
        self.approachBtn.setText(_translate("Form", "Approach", None))

