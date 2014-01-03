# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './acq4/analysis/modules/CellHealthTracker/CellHealthCtrlTemplate.ui'
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

class Ui_widget(object):
    def setupUi(self, widget):
        widget.setObjectName(_fromUtf8("widget"))
        widget.resize(232, 259)
        self.gridLayout = QtGui.QGridLayout(widget)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setSpacing(0)
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.label_4 = QtGui.QLabel(widget)
        self.label_4.setObjectName(_fromUtf8("label_4"))
        self.horizontalLayout.addWidget(self.label_4)
        self.methodCombo = QtGui.QComboBox(widget)
        self.methodCombo.setMinimumSize(QtCore.QSize(158, 0))
        self.methodCombo.setObjectName(_fromUtf8("methodCombo"))
        self.methodCombo.addItem(_fromUtf8(""))
        self.methodCombo.addItem(_fromUtf8(""))
        self.methodCombo.addItem(_fromUtf8(""))
        self.horizontalLayout.addWidget(self.methodCombo)
        self.horizontalLayout.setStretch(0, 1)
        self.horizontalLayout.setStretch(1, 4)
        self.gridLayout.addLayout(self.horizontalLayout, 0, 0, 1, 2)
        self.groupBox_2 = QtGui.QGroupBox(widget)
        self.groupBox_2.setObjectName(_fromUtf8("groupBox_2"))
        self.gridLayout_3 = QtGui.QGridLayout(self.groupBox_2)
        self.gridLayout_3.setMargin(3)
        self.gridLayout_3.setSpacing(3)
        self.gridLayout_3.setObjectName(_fromUtf8("gridLayout_3"))
        self.label_2 = QtGui.QLabel(self.groupBox_2)
        self.label_2.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout_3.addWidget(self.label_2, 1, 0, 1, 1)
        self.startSpin = SpinBox(self.groupBox_2)
        self.startSpin.setObjectName(_fromUtf8("startSpin"))
        self.gridLayout_3.addWidget(self.startSpin, 1, 1, 1, 1)
        self.label_3 = QtGui.QLabel(self.groupBox_2)
        self.label_3.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.gridLayout_3.addWidget(self.label_3, 2, 0, 1, 1)
        self.stopSpin = SpinBox(self.groupBox_2)
        self.stopSpin.setObjectName(_fromUtf8("stopSpin"))
        self.gridLayout_3.addWidget(self.stopSpin, 2, 1, 1, 1)
        self.gridLayout_3.setColumnStretch(0, 1)
        self.gridLayout_3.setColumnStretch(1, 5)
        self.gridLayout.addWidget(self.groupBox_2, 1, 0, 1, 2)
        self.groupBox = QtGui.QGroupBox(widget)
        self.groupBox.setObjectName(_fromUtf8("groupBox"))
        self.gridLayout_2 = QtGui.QGridLayout(self.groupBox)
        self.gridLayout_2.setMargin(3)
        self.gridLayout_2.setSpacing(3)
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
        self.RsCheck = QtGui.QCheckBox(self.groupBox)
        self.RsCheck.setObjectName(_fromUtf8("RsCheck"))
        self.gridLayout_2.addWidget(self.RsCheck, 2, 0, 1, 1)
        self.IhCheck = QtGui.QCheckBox(self.groupBox)
        self.IhCheck.setObjectName(_fromUtf8("IhCheck"))
        self.gridLayout_2.addWidget(self.IhCheck, 1, 0, 1, 1)
        self.RmCheck = QtGui.QCheckBox(self.groupBox)
        self.RmCheck.setObjectName(_fromUtf8("RmCheck"))
        self.gridLayout_2.addWidget(self.RmCheck, 3, 0, 1, 1)
        self.gridLayout.addWidget(self.groupBox, 2, 0, 1, 2)
        self.processBtn = QtGui.QPushButton(widget)
        self.processBtn.setObjectName(_fromUtf8("processBtn"))
        self.gridLayout.addWidget(self.processBtn, 3, 0, 1, 1)
        self.saveBtn = QtGui.QPushButton(widget)
        self.saveBtn.setObjectName(_fromUtf8("saveBtn"))
        self.gridLayout.addWidget(self.saveBtn, 3, 1, 1, 1)
        spacerItem = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem, 4, 0, 1, 2)

        self.retranslateUi(widget)
        QtCore.QMetaObject.connectSlotsByName(widget)

    def retranslateUi(self, widget):
        widget.setWindowTitle(_translate("widget", "Form", None))
        self.label_4.setText(_translate("widget", "Method:", None))
        self.methodCombo.setItemText(0, _translate("widget", "Simple Ohm\'s law", None))
        self.methodCombo.setItemText(1, _translate("widget", "Santos-Sacchi raw", None))
        self.methodCombo.setItemText(2, _translate("widget", "Santos-Sacchi fit", None))
        self.groupBox_2.setTitle(_translate("widget", "Measurement region:", None))
        self.label_2.setText(_translate("widget", "Start:", None))
        self.label_3.setText(_translate("widget", "Stop: ", None))
        self.groupBox.setTitle(_translate("widget", "Parameters to measure:", None))
        self.RsCheck.setText(_translate("widget", "Series Resistance", None))
        self.IhCheck.setText(_translate("widget", "Holding Current", None))
        self.RmCheck.setText(_translate("widget", "Membrane Resistance", None))
        self.processBtn.setToolTip(_translate("widget", "Measure parameters for the currently selected file.", None))
        self.processBtn.setText(_translate("widget", "Process", None))
        self.saveBtn.setToolTip(_translate("widget", "Save the data currently displayed in the Ih, Rs, and Rm plots.", None))
        self.saveBtn.setText(_translate("widget", "Save plots", None))

from acq4.pyqtgraph.widgets.SpinBox import SpinBox
