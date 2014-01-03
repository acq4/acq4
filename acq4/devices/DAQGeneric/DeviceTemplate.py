# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'DeviceTemplate.ui'
#
# Created: Thu Jan 02 17:36:51 2014
#      by: PyQt4 UI code generator 4.9.1
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
        Form.resize(240, 194)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setMargin(0)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.holdingSpin = SpinBox(Form)
        self.holdingSpin.setObjectName(_fromUtf8("holdingSpin"))
        self.gridLayout.addWidget(self.holdingSpin, 2, 2, 1, 1)
        self.scaleSpin = SpinBox(Form)
        self.scaleSpin.setObjectName(_fromUtf8("scaleSpin"))
        self.gridLayout.addWidget(self.scaleSpin, 3, 2, 1, 1)
        self.horizontalLayout_2 = QtGui.QHBoxLayout()
        self.horizontalLayout_2.setObjectName(_fromUtf8("horizontalLayout_2"))
        self.inputRadio = QtGui.QRadioButton(Form)
        self.inputRadio.setObjectName(_fromUtf8("inputRadio"))
        self.horizontalLayout_2.addWidget(self.inputRadio)
        self.outputRadio = QtGui.QRadioButton(Form)
        self.outputRadio.setObjectName(_fromUtf8("outputRadio"))
        self.horizontalLayout_2.addWidget(self.outputRadio)
        spacerItem = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.horizontalLayout_2.addItem(spacerItem)
        self.gridLayout.addLayout(self.horizontalLayout_2, 1, 3, 1, 2)
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName(_fromUtf8("label"))
        self.horizontalLayout.addWidget(self.label)
        self.channelCombo = QtGui.QComboBox(Form)
        self.channelCombo.setObjectName(_fromUtf8("channelCombo"))
        self.horizontalLayout.addWidget(self.channelCombo)
        self.gridLayout.addLayout(self.horizontalLayout, 1, 0, 1, 3)
        self.scaleDefaultBtn = QtGui.QPushButton(Form)
        self.scaleDefaultBtn.setObjectName(_fromUtf8("scaleDefaultBtn"))
        self.gridLayout.addWidget(self.scaleDefaultBtn, 3, 3, 1, 1)
        self.offsetDefaultBtn = QtGui.QPushButton(Form)
        self.offsetDefaultBtn.setObjectName(_fromUtf8("offsetDefaultBtn"))
        self.gridLayout.addWidget(self.offsetDefaultBtn, 4, 3, 1, 1)
        self.invertCheck = QtGui.QCheckBox(Form)
        self.invertCheck.setObjectName(_fromUtf8("invertCheck"))
        self.gridLayout.addWidget(self.invertCheck, 2, 3, 1, 1)
        self.nameLabel = QtGui.QLabel(Form)
        font = QtGui.QFont()
        font.setPointSize(13)
        font.setBold(True)
        font.setWeight(75)
        self.nameLabel.setFont(font)
        self.nameLabel.setObjectName(_fromUtf8("nameLabel"))
        self.gridLayout.addWidget(self.nameLabel, 0, 0, 1, 3)
        spacerItem1 = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem1, 5, 3, 1, 1)
        self.offsetSpin = SpinBox(Form)
        self.offsetSpin.setObjectName(_fromUtf8("offsetSpin"))
        self.gridLayout.addWidget(self.offsetSpin, 4, 2, 1, 1)
        self.holdingLabel = QtGui.QLabel(Form)
        self.holdingLabel.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.holdingLabel.setObjectName(_fromUtf8("holdingLabel"))
        self.gridLayout.addWidget(self.holdingLabel, 2, 1, 1, 1)
        self.scaleLabel = QtGui.QLabel(Form)
        self.scaleLabel.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.scaleLabel.setObjectName(_fromUtf8("scaleLabel"))
        self.gridLayout.addWidget(self.scaleLabel, 3, 1, 1, 1)
        self.offsetLabel = QtGui.QLabel(Form)
        self.offsetLabel.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.offsetLabel.setObjectName(_fromUtf8("offsetLabel"))
        self.gridLayout.addWidget(self.offsetLabel, 4, 1, 1, 1)
        spacerItem2 = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridLayout.addItem(spacerItem2, 2, 0, 3, 1)
        spacerItem3 = QtGui.QSpacerItem(42, 1, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridLayout.addItem(spacerItem3, 2, 4, 3, 1)
        self.gridLayout.setColumnStretch(1, 1)
        self.gridLayout.setColumnStretch(2, 2)
        self.gridLayout.setColumnStretch(3, 2)
        self.gridLayout.setColumnStretch(4, 4)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.inputRadio.setText(QtGui.QApplication.translate("Form", "Input", None, QtGui.QApplication.UnicodeUTF8))
        self.outputRadio.setText(QtGui.QApplication.translate("Form", "Output", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Channel:", None, QtGui.QApplication.UnicodeUTF8))
        self.scaleDefaultBtn.setText(QtGui.QApplication.translate("Form", "Default", None, QtGui.QApplication.UnicodeUTF8))
        self.offsetDefaultBtn.setText(QtGui.QApplication.translate("Form", "Default", None, QtGui.QApplication.UnicodeUTF8))
        self.invertCheck.setText(QtGui.QApplication.translate("Form", "Invert", None, QtGui.QApplication.UnicodeUTF8))
        self.nameLabel.setText(QtGui.QApplication.translate("Form", "ChannelName", None, QtGui.QApplication.UnicodeUTF8))
        self.holdingLabel.setText(QtGui.QApplication.translate("Form", "Holding:", None, QtGui.QApplication.UnicodeUTF8))
        self.scaleLabel.setText(QtGui.QApplication.translate("Form", "Scale:", None, QtGui.QApplication.UnicodeUTF8))
        self.offsetLabel.setText(QtGui.QApplication.translate("Form", "Offset:", None, QtGui.QApplication.UnicodeUTF8))

from acq4.pyqtgraph import SpinBox
