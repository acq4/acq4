# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/devices/Microscope/deviceTemplate.ui'
#
# Created by: PyQt5 UI code generator 5.8.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(415, 206)
        self.gridLayout = QtWidgets.QGridLayout(Form)
        self.gridLayout.setContentsMargins(3, 3, 3, 3)
        self.gridLayout.setHorizontalSpacing(8)
        self.gridLayout.setVerticalSpacing(0)
        self.gridLayout.setObjectName("gridLayout")
        self.label_2 = QtWidgets.QLabel(Form)
        self.label_2.setObjectName("label_2")
        self.gridLayout.addWidget(self.label_2, 0, 0, 1, 1)
        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.gridLayout.addItem(spacerItem, 0, 3, 1, 1)
        spacerItem1 = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem1, 1, 0, 1, 1)
        self.objectiveLayout = QtWidgets.QGridLayout()
        self.objectiveLayout.setSpacing(4)
        self.objectiveLayout.setObjectName("objectiveLayout")
        self.label_5 = QtWidgets.QLabel(Form)
        self.label_5.setObjectName("label_5")
        self.objectiveLayout.addWidget(self.label_5, 0, 5, 1, 1)
        self.label_4 = QtWidgets.QLabel(Form)
        self.label_4.setObjectName("label_4")
        self.objectiveLayout.addWidget(self.label_4, 0, 3, 1, 1)
        self.widget_5 = QtWidgets.QWidget(Form)
        self.widget_5.setMinimumSize(Qt.QSize(20, 0))
        self.widget_5.setObjectName("widget_5")
        self.objectiveLayout.addWidget(self.widget_5, 0, 1, 1, 1)
        self.label_3 = QtWidgets.QLabel(Form)
        self.label_3.setObjectName("label_3")
        self.objectiveLayout.addWidget(self.label_3, 0, 2, 1, 1)
        self.widget = QtWidgets.QWidget(Form)
        self.widget.setMinimumSize(Qt.QSize(20, 0))
        self.widget.setObjectName("widget")
        self.objectiveLayout.addWidget(self.widget, 0, 0, 1, 1)
        self.label = QtWidgets.QLabel(Form)
        self.label.setObjectName("label")
        self.objectiveLayout.addWidget(self.label, 0, 4, 1, 1)
        self.gridLayout.addLayout(self.objectiveLayout, 0, 1, 1, 2)

        self.retranslateUi(Form)
        Qt.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        _translate = Qt.QCoreApplication.translate
        Form.setWindowTitle(_translate("Form", "Form"))
        self.label_2.setText(_translate("Form", "Objective:"))
        self.label_5.setText(_translate("Form", "Scale"))
        self.label_4.setText(_translate("Form", "Y"))
        self.label_3.setText(_translate("Form", "X"))
        self.label.setText(_translate("Form", "Z"))

