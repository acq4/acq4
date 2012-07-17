# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './lib/devices/Microscope/deviceTemplate.ui'
#
# Created: Wed Jun 13 15:38:36 2012
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
        Form.resize(415, 206)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setMargin(3)
        self.gridLayout.setHorizontalSpacing(8)
        self.gridLayout.setVerticalSpacing(0)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.label_2 = QtGui.QLabel(Form)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout.addWidget(self.label_2, 0, 0, 1, 1)
        spacerItem = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridLayout.addItem(spacerItem, 0, 3, 1, 1)
        spacerItem1 = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem1, 1, 0, 1, 1)
        self.objectiveLayout = QtGui.QGridLayout()
        self.objectiveLayout.setSpacing(4)
        self.objectiveLayout.setObjectName(_fromUtf8("objectiveLayout"))
        self.widget = QtGui.QWidget(Form)
        self.widget.setMinimumSize(QtCore.QSize(20, 0))
        self.widget.setObjectName(_fromUtf8("widget"))
        self.objectiveLayout.addWidget(self.widget, 0, 0, 1, 1)
        self.widget_5 = QtGui.QWidget(Form)
        self.widget_5.setMinimumSize(QtCore.QSize(20, 0))
        self.widget_5.setObjectName(_fromUtf8("widget_5"))
        self.objectiveLayout.addWidget(self.widget_5, 0, 1, 1, 1)
        self.label_3 = QtGui.QLabel(Form)
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.objectiveLayout.addWidget(self.label_3, 0, 2, 1, 1)
        self.label_4 = QtGui.QLabel(Form)
        self.label_4.setObjectName(_fromUtf8("label_4"))
        self.objectiveLayout.addWidget(self.label_4, 0, 3, 1, 1)
        self.label_5 = QtGui.QLabel(Form)
        self.label_5.setObjectName(_fromUtf8("label_5"))
        self.objectiveLayout.addWidget(self.label_5, 0, 4, 1, 1)
        self.gridLayout.addLayout(self.objectiveLayout, 0, 1, 1, 2)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("Form", "Objective:", None, QtGui.QApplication.UnicodeUTF8))
        self.label_3.setText(QtGui.QApplication.translate("Form", "X", None, QtGui.QApplication.UnicodeUTF8))
        self.label_4.setText(QtGui.QApplication.translate("Form", "Y", None, QtGui.QApplication.UnicodeUTF8))
        self.label_5.setText(QtGui.QApplication.translate("Form", "Scale", None, QtGui.QApplication.UnicodeUTF8))

