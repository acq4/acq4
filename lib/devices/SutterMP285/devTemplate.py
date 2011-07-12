# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'devTemplate.ui'
#
# Created: Tue Jul 12 09:33:16 2011
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
        Form.resize(179, 207)
        self.gridLayout_3 = QtGui.QGridLayout(Form)
        self.gridLayout_3.setObjectName(_fromUtf8("gridLayout_3"))
        self.groupBox_2 = QtGui.QGroupBox(Form)
        self.groupBox_2.setAlignment(QtCore.Qt.AlignCenter)
        self.groupBox_2.setObjectName(_fromUtf8("groupBox_2"))
        self.gridLayout = QtGui.QGridLayout(self.groupBox_2)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.posLabel = QtGui.QLabel(self.groupBox_2)
        self.posLabel.setObjectName(_fromUtf8("posLabel"))
        self.gridLayout.addWidget(self.posLabel, 0, 0, 1, 3)
        self.joyBtn = QtGui.QPushButton(self.groupBox_2)
        self.joyBtn.setMinimumSize(QtCore.QSize(50, 50))
        self.joyBtn.setText(_fromUtf8(""))
        self.joyBtn.setObjectName(_fromUtf8("joyBtn"))
        self.gridLayout.addWidget(self.joyBtn, 1, 1, 1, 1)
        spacerItem = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridLayout.addItem(spacerItem, 1, 0, 1, 1)
        spacerItem1 = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridLayout.addItem(spacerItem1, 1, 2, 1, 1)
        self.gridLayout_3.addWidget(self.groupBox_2, 0, 0, 1, 1)
        self.groupBox = QtGui.QGroupBox(Form)
        self.groupBox.setAlignment(QtCore.Qt.AlignCenter)
        self.groupBox.setObjectName(_fromUtf8("groupBox"))
        self.gridLayout_2 = QtGui.QGridLayout(self.groupBox)
        self.gridLayout_2.setContentsMargins(-1, 0, -1, 0)
        self.gridLayout_2.setHorizontalSpacing(5)
        self.gridLayout_2.setVerticalSpacing(0)
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
        self.label_2 = QtGui.QLabel(self.groupBox)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout_2.addWidget(self.label_2, 0, 0, 1, 1)
        self.xMinBtn = QtGui.QPushButton(self.groupBox)
        self.xMinBtn.setMaximumSize(QtCore.QSize(30, 16777215))
        self.xMinBtn.setObjectName(_fromUtf8("xMinBtn"))
        self.gridLayout_2.addWidget(self.xMinBtn, 0, 1, 1, 1)
        self.xMaxBtn = QtGui.QPushButton(self.groupBox)
        self.xMaxBtn.setMaximumSize(QtCore.QSize(30, 16777215))
        self.xMaxBtn.setObjectName(_fromUtf8("xMaxBtn"))
        self.gridLayout_2.addWidget(self.xMaxBtn, 0, 5, 1, 1)
        self.label_3 = QtGui.QLabel(self.groupBox)
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.gridLayout_2.addWidget(self.label_3, 1, 0, 1, 1)
        self.yMinBtn = QtGui.QPushButton(self.groupBox)
        self.yMinBtn.setMaximumSize(QtCore.QSize(30, 16777215))
        self.yMinBtn.setObjectName(_fromUtf8("yMinBtn"))
        self.gridLayout_2.addWidget(self.yMinBtn, 1, 1, 1, 1)
        self.yMaxBtn = QtGui.QPushButton(self.groupBox)
        self.yMaxBtn.setMaximumSize(QtCore.QSize(30, 16777215))
        self.yMaxBtn.setObjectName(_fromUtf8("yMaxBtn"))
        self.gridLayout_2.addWidget(self.yMaxBtn, 1, 5, 1, 1)
        self.label_4 = QtGui.QLabel(self.groupBox)
        self.label_4.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.label_4.setObjectName(_fromUtf8("label_4"))
        self.gridLayout_2.addWidget(self.label_4, 2, 0, 1, 2)
        self.maxSpeedSpin = QtGui.QDoubleSpinBox(self.groupBox)
        self.maxSpeedSpin.setObjectName(_fromUtf8("maxSpeedSpin"))
        self.gridLayout_2.addWidget(self.maxSpeedSpin, 2, 3, 1, 1)
        self.xMinLabel = QtGui.QLabel(self.groupBox)
        self.xMinLabel.setObjectName(_fromUtf8("xMinLabel"))
        self.gridLayout_2.addWidget(self.xMinLabel, 0, 3, 1, 1)
        self.yMinLabel = QtGui.QLabel(self.groupBox)
        self.yMinLabel.setObjectName(_fromUtf8("yMinLabel"))
        self.gridLayout_2.addWidget(self.yMinLabel, 1, 3, 1, 1)
        self.xMaxLabel = QtGui.QLabel(self.groupBox)
        self.xMaxLabel.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.xMaxLabel.setObjectName(_fromUtf8("xMaxLabel"))
        self.gridLayout_2.addWidget(self.xMaxLabel, 0, 4, 1, 1)
        self.yMaxLabel = QtGui.QLabel(self.groupBox)
        self.yMaxLabel.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.yMaxLabel.setObjectName(_fromUtf8("yMaxLabel"))
        self.gridLayout_2.addWidget(self.yMaxLabel, 1, 4, 1, 1)
        self.gridLayout_3.addWidget(self.groupBox, 1, 0, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox_2.setTitle(QtGui.QApplication.translate("Form", "Position", None, QtGui.QApplication.UnicodeUTF8))
        self.posLabel.setText(QtGui.QApplication.translate("Form", "0,0", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox.setTitle(QtGui.QApplication.translate("Form", "Limits", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("Form", "X", None, QtGui.QApplication.UnicodeUTF8))
        self.xMinBtn.setText(QtGui.QApplication.translate("Form", "set", None, QtGui.QApplication.UnicodeUTF8))
        self.xMaxBtn.setText(QtGui.QApplication.translate("Form", "set", None, QtGui.QApplication.UnicodeUTF8))
        self.label_3.setText(QtGui.QApplication.translate("Form", "Y", None, QtGui.QApplication.UnicodeUTF8))
        self.yMinBtn.setText(QtGui.QApplication.translate("Form", "set", None, QtGui.QApplication.UnicodeUTF8))
        self.yMaxBtn.setText(QtGui.QApplication.translate("Form", "set", None, QtGui.QApplication.UnicodeUTF8))
        self.label_4.setText(QtGui.QApplication.translate("Form", "Speed", None, QtGui.QApplication.UnicodeUTF8))
        self.xMinLabel.setText(QtGui.QApplication.translate("Form", "0", None, QtGui.QApplication.UnicodeUTF8))
        self.yMinLabel.setText(QtGui.QApplication.translate("Form", "0", None, QtGui.QApplication.UnicodeUTF8))
        self.xMaxLabel.setText(QtGui.QApplication.translate("Form", "0", None, QtGui.QApplication.UnicodeUTF8))
        self.yMaxLabel.setText(QtGui.QApplication.translate("Form", "0", None, QtGui.QApplication.UnicodeUTF8))

