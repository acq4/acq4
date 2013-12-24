# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './acq4/devices/MockClamp/devTemplate.ui'
#
# Created: Tue Dec 24 01:49:06 2013
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

class Ui_MockClampDevGui(object):
    def setupUi(self, MockClampDevGui):
        MockClampDevGui.setObjectName(_fromUtf8("MockClampDevGui"))
        MockClampDevGui.resize(459, 229)
        self.gridLayout = QtGui.QGridLayout(MockClampDevGui)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.groupBox_2 = QtGui.QGroupBox(MockClampDevGui)
        self.groupBox_2.setObjectName(_fromUtf8("groupBox_2"))
        self.gridLayout_3 = QtGui.QGridLayout(self.groupBox_2)
        self.gridLayout_3.setObjectName(_fromUtf8("gridLayout_3"))
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.vcModeRadio = QtGui.QRadioButton(self.groupBox_2)
        self.vcModeRadio.setObjectName(_fromUtf8("vcModeRadio"))
        self.horizontalLayout.addWidget(self.vcModeRadio)
        self.i0ModeRadio = QtGui.QRadioButton(self.groupBox_2)
        self.i0ModeRadio.setObjectName(_fromUtf8("i0ModeRadio"))
        self.horizontalLayout.addWidget(self.i0ModeRadio)
        self.icModeRadio = QtGui.QRadioButton(self.groupBox_2)
        self.icModeRadio.setObjectName(_fromUtf8("icModeRadio"))
        self.horizontalLayout.addWidget(self.icModeRadio)
        self.gridLayout_3.addLayout(self.horizontalLayout, 0, 0, 1, 2)
        self.label_3 = QtGui.QLabel(self.groupBox_2)
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.gridLayout_3.addWidget(self.label_3, 1, 0, 1, 1)
        self.vcHoldingSpin = SpinBox(self.groupBox_2)
        self.vcHoldingSpin.setObjectName(_fromUtf8("vcHoldingSpin"))
        self.gridLayout_3.addWidget(self.vcHoldingSpin, 1, 1, 1, 1)
        self.label_4 = QtGui.QLabel(self.groupBox_2)
        self.label_4.setObjectName(_fromUtf8("label_4"))
        self.gridLayout_3.addWidget(self.label_4, 2, 0, 1, 1)
        self.icHoldingSpin = SpinBox(self.groupBox_2)
        self.icHoldingSpin.setObjectName(_fromUtf8("icHoldingSpin"))
        self.gridLayout_3.addWidget(self.icHoldingSpin, 2, 1, 1, 1)
        spacerItem = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout_3.addItem(spacerItem, 4, 0, 1, 1)
        self.label_6 = QtGui.QLabel(self.groupBox_2)
        self.label_6.setObjectName(_fromUtf8("label_6"))
        self.gridLayout_3.addWidget(self.label_6, 3, 0, 1, 1)
        self.pipOffsetSpin = SpinBox(self.groupBox_2)
        self.pipOffsetSpin.setObjectName(_fromUtf8("pipOffsetSpin"))
        self.gridLayout_3.addWidget(self.pipOffsetSpin, 3, 1, 1, 1)
        self.gridLayout.addWidget(self.groupBox_2, 0, 0, 1, 1)
        self.groupBox = QtGui.QGroupBox(MockClampDevGui)
        self.groupBox.setObjectName(_fromUtf8("groupBox"))
        self.gridLayout_2 = QtGui.QGridLayout(self.groupBox)
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
        self.label = QtGui.QLabel(self.groupBox)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout_2.addWidget(self.label, 0, 0, 1, 1)
        self.pipCapSpin = SpinBox(self.groupBox)
        self.pipCapSpin.setObjectName(_fromUtf8("pipCapSpin"))
        self.gridLayout_2.addWidget(self.pipCapSpin, 0, 1, 1, 2)
        self.label_2 = QtGui.QLabel(self.groupBox)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout_2.addWidget(self.label_2, 1, 0, 1, 1)
        self.pipResSpin = SpinBox(self.groupBox)
        self.pipResSpin.setObjectName(_fromUtf8("pipResSpin"))
        self.gridLayout_2.addWidget(self.pipResSpin, 1, 1, 1, 2)
        self.label_5 = QtGui.QLabel(self.groupBox)
        self.label_5.setObjectName(_fromUtf8("label_5"))
        self.gridLayout_2.addWidget(self.label_5, 2, 0, 1, 1)
        self.pipJunctPotSpin = SpinBox(self.groupBox)
        self.pipJunctPotSpin.setObjectName(_fromUtf8("pipJunctPotSpin"))
        self.gridLayout_2.addWidget(self.pipJunctPotSpin, 2, 1, 1, 2)
        self.pipBathRadio = QtGui.QRadioButton(self.groupBox)
        self.pipBathRadio.setObjectName(_fromUtf8("pipBathRadio"))
        self.gridLayout_2.addWidget(self.pipBathRadio, 3, 0, 1, 3)
        self.pipAttachRadio = QtGui.QRadioButton(self.groupBox)
        self.pipAttachRadio.setObjectName(_fromUtf8("pipAttachRadio"))
        self.gridLayout_2.addWidget(self.pipAttachRadio, 5, 0, 1, 2)
        self.pipWholeRadio = QtGui.QRadioButton(self.groupBox)
        self.pipWholeRadio.setObjectName(_fromUtf8("pipWholeRadio"))
        self.gridLayout_2.addWidget(self.pipWholeRadio, 5, 2, 1, 1)
        spacerItem1 = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout_2.addItem(spacerItem1, 6, 0, 1, 1)
        self.comboBox = QtGui.QComboBox(self.groupBox)
        self.comboBox.setObjectName(_fromUtf8("comboBox"))
        self.gridLayout_2.addWidget(self.comboBox, 4, 1, 1, 2)
        self.label_7 = QtGui.QLabel(self.groupBox)
        self.label_7.setObjectName(_fromUtf8("label_7"))
        self.gridLayout_2.addWidget(self.label_7, 4, 0, 1, 1)
        self.gridLayout.addWidget(self.groupBox, 0, 1, 1, 1)

        self.retranslateUi(MockClampDevGui)
        QtCore.QMetaObject.connectSlotsByName(MockClampDevGui)

    def retranslateUi(self, MockClampDevGui):
        MockClampDevGui.setWindowTitle(_translate("MockClampDevGui", "Form", None))
        self.groupBox_2.setTitle(_translate("MockClampDevGui", "Clamp", None))
        self.vcModeRadio.setText(_translate("MockClampDevGui", "VC", None))
        self.i0ModeRadio.setText(_translate("MockClampDevGui", "I=0", None))
        self.icModeRadio.setText(_translate("MockClampDevGui", "IC", None))
        self.label_3.setText(_translate("MockClampDevGui", "VC Holding", None))
        self.label_4.setText(_translate("MockClampDevGui", "IC Holding", None))
        self.label_6.setText(_translate("MockClampDevGui", "Pipette Offset", None))
        self.groupBox.setTitle(_translate("MockClampDevGui", "Pipette", None))
        self.label.setText(_translate("MockClampDevGui", "Capacitance", None))
        self.label_2.setText(_translate("MockClampDevGui", "Resistance", None))
        self.label_5.setText(_translate("MockClampDevGui", "Junct. Pot.", None))
        self.pipBathRadio.setText(_translate("MockClampDevGui", "Bath", None))
        self.pipAttachRadio.setText(_translate("MockClampDevGui", "On Cell", None))
        self.pipWholeRadio.setText(_translate("MockClampDevGui", "Whole Cell", None))
        self.label_7.setText(_translate("MockClampDevGui", "Cell", None))

from acq4.pyqtgraph import SpinBox
