# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'SpatialCorrelatorCtrlTemplate.ui'
#
# Created: Wed Sep 19 16:08:42 2012
#      by: PyQt4 UI code generator 4.9
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
        Form.resize(273, 234)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setMargin(3)
        self.gridLayout.setSpacing(3)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setSpacing(1)
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName(_fromUtf8("label"))
        self.horizontalLayout.addWidget(self.label)
        self.spontSpin = SpinBox(Form)
        self.spontSpin.setSuffix(_fromUtf8(""))
        self.spontSpin.setObjectName(_fromUtf8("spontSpin"))
        self.horizontalLayout.addWidget(self.spontSpin)
        self.gridLayout.addLayout(self.horizontalLayout, 1, 0, 1, 2)
        self.horizontalLayout_2 = QtGui.QHBoxLayout()
        self.horizontalLayout_2.setSpacing(1)
        self.horizontalLayout_2.setObjectName(_fromUtf8("horizontalLayout_2"))
        self.label_2 = QtGui.QLabel(Form)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.horizontalLayout_2.addWidget(self.label_2)
        self.deltaTSpin = SpinBox(Form)
        self.deltaTSpin.setObjectName(_fromUtf8("deltaTSpin"))
        self.horizontalLayout_2.addWidget(self.deltaTSpin)
        self.gridLayout.addLayout(self.horizontalLayout_2, 2, 0, 1, 2)
        self.horizontalLayout_3 = QtGui.QHBoxLayout()
        self.horizontalLayout_3.setSpacing(1)
        self.horizontalLayout_3.setObjectName(_fromUtf8("horizontalLayout_3"))
        self.label_3 = QtGui.QLabel(Form)
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.horizontalLayout_3.addWidget(self.label_3)
        self.radiusSpin = SpinBox(Form)
        self.radiusSpin.setObjectName(_fromUtf8("radiusSpin"))
        self.horizontalLayout_3.addWidget(self.radiusSpin)
        self.gridLayout.addLayout(self.horizontalLayout_3, 3, 0, 1, 2)
        self.disableChk = QtGui.QCheckBox(Form)
        self.disableChk.setObjectName(_fromUtf8("disableChk"))
        self.gridLayout.addWidget(self.disableChk, 6, 0, 1, 1)
        self.processBtn = QtGui.QPushButton(Form)
        self.processBtn.setObjectName(_fromUtf8("processBtn"))
        self.gridLayout.addWidget(self.processBtn, 6, 1, 1, 1)
        self.groupBox = QtGui.QGroupBox(Form)
        self.groupBox.setObjectName(_fromUtf8("groupBox"))
        self.gridLayout_2 = QtGui.QGridLayout(self.groupBox)
        self.gridLayout_2.setMargin(3)
        self.gridLayout_2.setSpacing(3)
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
        self.probabilityRadio = QtGui.QRadioButton(self.groupBox)
        self.probabilityRadio.setChecked(True)
        self.probabilityRadio.setObjectName(_fromUtf8("probabilityRadio"))
        self.gridLayout_2.addWidget(self.probabilityRadio, 0, 0, 1, 2)
        self.thresholdSpin = SpinBox(self.groupBox)
        self.thresholdSpin.setEnabled(True)
        self.thresholdSpin.setObjectName(_fromUtf8("thresholdSpin"))
        self.gridLayout_2.addWidget(self.thresholdSpin, 2, 1, 1, 1)
        self.label_4 = QtGui.QLabel(self.groupBox)
        self.label_4.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.label_4.setObjectName(_fromUtf8("label_4"))
        self.gridLayout_2.addWidget(self.label_4, 2, 0, 1, 1)
        self.thresholdRadio = QtGui.QRadioButton(self.groupBox)
        self.thresholdRadio.setObjectName(_fromUtf8("thresholdRadio"))
        self.gridLayout_2.addWidget(self.thresholdRadio, 1, 0, 1, 2)
        self.gridLayout.addWidget(self.groupBox, 5, 0, 1, 2)
        self.eventCombo = ComboBox(Form)
        self.eventCombo.setObjectName(_fromUtf8("eventCombo"))
        self.gridLayout.addWidget(self.eventCombo, 0, 1, 1, 1)
        self.label_5 = QtGui.QLabel(Form)
        self.label_5.setObjectName(_fromUtf8("label_5"))
        self.gridLayout.addWidget(self.label_5, 0, 0, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Spontaneous Event Rate:", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("Form", "Post-stimulus time window:", None, QtGui.QApplication.UnicodeUTF8))
        self.label_3.setText(QtGui.QApplication.translate("Form", "Correlation Radius:", None, QtGui.QApplication.UnicodeUTF8))
        self.disableChk.setText(QtGui.QApplication.translate("Form", "Disable", None, QtGui.QApplication.UnicodeUTF8))
        self.processBtn.setText(QtGui.QApplication.translate("Form", "re-Process", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox.setTitle(QtGui.QApplication.translate("Form", "Output data:", None, QtGui.QApplication.UnicodeUTF8))
        self.probabilityRadio.setText(QtGui.QApplication.translate("Form", "Probability values (float)", None, QtGui.QApplication.UnicodeUTF8))
        self.label_4.setText(QtGui.QApplication.translate("Form", "Threshold:", None, QtGui.QApplication.UnicodeUTF8))
        self.thresholdRadio.setText(QtGui.QApplication.translate("Form", "Spots that cross threshold (boolean)", None, QtGui.QApplication.UnicodeUTF8))
        self.label_5.setText(QtGui.QApplication.translate("Form", "Event Parameter to use:", None, QtGui.QApplication.UnicodeUTF8))

from pyqtgraph.widgets.ComboBox import ComboBox
from pyqtgraph.widgets.SpinBox import SpinBox
