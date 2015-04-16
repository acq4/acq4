# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'sequencerTemplate.ui'
#
# Created: Thu Apr 16 21:34:11 2015
#      by: PyQt4 UI code generator 4.10.4
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
        Form.resize(400, 106)
        self.gridLayout_3 = QtGui.QGridLayout(Form)
        self.gridLayout_3.setMargin(0)
        self.gridLayout_3.setSpacing(3)
        self.gridLayout_3.setObjectName(_fromUtf8("gridLayout_3"))
        self.timelapseGroup = QtGui.QGroupBox(Form)
        self.timelapseGroup.setCheckable(True)
        self.timelapseGroup.setChecked(False)
        self.timelapseGroup.setObjectName(_fromUtf8("timelapseGroup"))
        self.gridLayout_2 = QtGui.QGridLayout(self.timelapseGroup)
        self.gridLayout_2.setMargin(3)
        self.gridLayout_2.setSpacing(3)
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
        self.intervalSpin = SpinBox(self.timelapseGroup)
        self.intervalSpin.setMinimumSize(QtCore.QSize(75, 0))
        self.intervalSpin.setObjectName(_fromUtf8("intervalSpin"))
        self.gridLayout_2.addWidget(self.intervalSpin, 0, 1, 1, 1)
        self.label_4 = QtGui.QLabel(self.timelapseGroup)
        self.label_4.setObjectName(_fromUtf8("label_4"))
        self.gridLayout_2.addWidget(self.label_4, 0, 0, 1, 1)
        self.label_5 = QtGui.QLabel(self.timelapseGroup)
        self.label_5.setObjectName(_fromUtf8("label_5"))
        self.gridLayout_2.addWidget(self.label_5, 1, 0, 1, 1)
        self.iterationsSpin = QtGui.QSpinBox(self.timelapseGroup)
        self.iterationsSpin.setObjectName(_fromUtf8("iterationsSpin"))
        self.gridLayout_2.addWidget(self.iterationsSpin, 1, 1, 1, 1)
        spacerItem = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout_2.addItem(spacerItem, 2, 0, 1, 1)
        self.gridLayout_3.addWidget(self.timelapseGroup, 0, 2, 3, 1)
        self.zStackGroup = QtGui.QGroupBox(Form)
        self.zStackGroup.setCheckable(True)
        self.zStackGroup.setChecked(False)
        self.zStackGroup.setObjectName(_fromUtf8("zStackGroup"))
        self.gridLayout = QtGui.QGridLayout(self.zStackGroup)
        self.gridLayout.setMargin(3)
        self.gridLayout.setSpacing(3)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.label_2 = QtGui.QLabel(self.zStackGroup)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout.addWidget(self.label_2, 0, 0, 2, 1)
        self.zStartSpin = SpinBox(self.zStackGroup)
        self.zStartSpin.setMinimumSize(QtCore.QSize(75, 0))
        self.zStartSpin.setObjectName(_fromUtf8("zStartSpin"))
        self.gridLayout.addWidget(self.zStartSpin, 0, 1, 1, 1)
        self.zEndSpin = SpinBox(self.zStackGroup)
        self.zEndSpin.setObjectName(_fromUtf8("zEndSpin"))
        self.gridLayout.addWidget(self.zEndSpin, 1, 1, 2, 1)
        self.label_3 = QtGui.QLabel(self.zStackGroup)
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.gridLayout.addWidget(self.label_3, 2, 0, 1, 1)
        self.label = QtGui.QLabel(self.zStackGroup)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 3, 0, 1, 1)
        self.zSpacingSpin = SpinBox(self.zStackGroup)
        self.zSpacingSpin.setObjectName(_fromUtf8("zSpacingSpin"))
        self.gridLayout.addWidget(self.zSpacingSpin, 3, 1, 1, 1)
        self.gridLayout_3.addWidget(self.zStackGroup, 0, 1, 3, 1)
        self.pauseBtn = QtGui.QPushButton(Form)
        self.pauseBtn.setCheckable(True)
        self.pauseBtn.setObjectName(_fromUtf8("pauseBtn"))
        self.gridLayout_3.addWidget(self.pauseBtn, 1, 0, 1, 1)
        self.startBtn = QtGui.QPushButton(Form)
        self.startBtn.setCheckable(True)
        self.startBtn.setObjectName(_fromUtf8("startBtn"))
        self.gridLayout_3.addWidget(self.startBtn, 0, 0, 1, 1)
        self.deviceCombo = ComboBox(Form)
        self.deviceCombo.setObjectName(_fromUtf8("deviceCombo"))
        self.gridLayout_3.addWidget(self.deviceCombo, 2, 0, 1, 1)
        spacerItem1 = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout_3.addItem(spacerItem1, 4, 1, 1, 1)
        self.statusLabel = QtGui.QLabel(Form)
        self.statusLabel.setText(_fromUtf8(""))
        self.statusLabel.setObjectName(_fromUtf8("statusLabel"))
        self.gridLayout_3.addWidget(self.statusLabel, 3, 0, 1, 3)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.timelapseGroup.setTitle(_translate("Form", "Timelapse", None))
        self.label_4.setText(_translate("Form", "Interval", None))
        self.label_5.setText(_translate("Form", "Iterations", None))
        self.iterationsSpin.setSpecialValueText(_translate("Form", "inf", None))
        self.zStackGroup.setTitle(_translate("Form", "Z Stack", None))
        self.label_2.setText(_translate("Form", "Start", None))
        self.label_3.setText(_translate("Form", "End", None))
        self.label.setText(_translate("Form", "Spacing", None))
        self.pauseBtn.setText(_translate("Form", "Pause", None))
        self.startBtn.setText(_translate("Form", "Start", None))

from acq4.pyqtgraph import ComboBox, SpinBox
