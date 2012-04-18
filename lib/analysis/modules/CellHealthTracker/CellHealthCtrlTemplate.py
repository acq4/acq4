# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './lib/analysis/modules/CellHealthTracker/CellHealthCtrlTemplate.ui'
#
# Created: Wed Apr 18 12:58:51 2012
#      by: PyQt4 UI code generator 4.8.3
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
    _fromUtf8 = lambda s: s

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
        widget.setWindowTitle(QtGui.QApplication.translate("widget", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label_4.setText(QtGui.QApplication.translate("widget", "Method:", None, QtGui.QApplication.UnicodeUTF8))
        self.methodCombo.setItemText(0, QtGui.QApplication.translate("widget", "Simple Ohm\'s law", None, QtGui.QApplication.UnicodeUTF8))
        self.methodCombo.setItemText(1, QtGui.QApplication.translate("widget", "Santos-Sacchi raw", None, QtGui.QApplication.UnicodeUTF8))
        self.methodCombo.setItemText(2, QtGui.QApplication.translate("widget", "Santos-Sacchi fit", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox_2.setTitle(QtGui.QApplication.translate("widget", "Measurement region:", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("widget", "Start:", None, QtGui.QApplication.UnicodeUTF8))
        self.label_3.setText(QtGui.QApplication.translate("widget", "Stop: ", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox.setTitle(QtGui.QApplication.translate("widget", "Parameters to measure:", None, QtGui.QApplication.UnicodeUTF8))
        self.RsCheck.setText(QtGui.QApplication.translate("widget", "Series Resistance", None, QtGui.QApplication.UnicodeUTF8))
        self.IhCheck.setText(QtGui.QApplication.translate("widget", "Holding Current", None, QtGui.QApplication.UnicodeUTF8))
        self.RmCheck.setText(QtGui.QApplication.translate("widget", "Membrane Resistance", None, QtGui.QApplication.UnicodeUTF8))
        self.processBtn.setToolTip(QtGui.QApplication.translate("widget", "Measure parameters for the currently selected file.", None, QtGui.QApplication.UnicodeUTF8))
        self.processBtn.setText(QtGui.QApplication.translate("widget", "Process", None, QtGui.QApplication.UnicodeUTF8))
        self.saveBtn.setToolTip(QtGui.QApplication.translate("widget", "Save the data currently displayed in the Ih, Rs, and Rm plots.", None, QtGui.QApplication.UnicodeUTF8))
        self.saveBtn.setText(QtGui.QApplication.translate("widget", "Save plots", None, QtGui.QApplication.UnicodeUTF8))

from pyqtgraph.widgets.SpinBox import SpinBox
