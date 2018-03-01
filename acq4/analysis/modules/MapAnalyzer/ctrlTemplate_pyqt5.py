# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/analysis/modules/MapAnalyzer/ctrlTemplate.ui'
#
# Created by: PyQt5 UI code generator 5.8.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(501, 469)
        self.groupBox = QtWidgets.QGroupBox(Form)
        self.groupBox.setGeometry(Qt.QRect(20, 60, 181, 121))
        self.groupBox.setObjectName("groupBox")
        self.radioButton = QtWidgets.QRadioButton(self.groupBox)
        self.radioButton.setGeometry(Qt.QRect(20, 20, 95, 21))
        self.radioButton.setObjectName("radioButton")
        self.radioButton_2 = QtWidgets.QRadioButton(self.groupBox)
        self.radioButton_2.setGeometry(Qt.QRect(20, 50, 95, 21))
        self.radioButton_2.setObjectName("radioButton_2")
        self.checkBox = QtWidgets.QCheckBox(self.groupBox)
        self.checkBox.setGeometry(Qt.QRect(20, 80, 80, 21))
        self.checkBox.setObjectName("checkBox")
        self.doubleSpinBox = QtWidgets.QDoubleSpinBox(self.groupBox)
        self.doubleSpinBox.setGeometry(Qt.QRect(110, 80, 62, 23))
        self.doubleSpinBox.setObjectName("doubleSpinBox")
        self.groupBox_2 = QtWidgets.QGroupBox(Form)
        self.groupBox_2.setGeometry(Qt.QRect(20, 190, 181, 91))
        self.groupBox_2.setObjectName("groupBox_2")
        self.groupBox_3 = QtWidgets.QGroupBox(Form)
        self.groupBox_3.setGeometry(Qt.QRect(20, 290, 181, 81))
        self.groupBox_3.setObjectName("groupBox_3")
        self.label = QtWidgets.QLabel(self.groupBox_3)
        self.label.setGeometry(Qt.QRect(10, 30, 54, 15))
        self.label.setObjectName("label")
        self.label_2 = QtWidgets.QLabel(self.groupBox_3)
        self.label_2.setGeometry(Qt.QRect(10, 60, 54, 15))
        self.label_2.setObjectName("label_2")

        self.retranslateUi(Form)
        Qt.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        _translate = Qt.QCoreApplication.translate
        Form.setWindowTitle(_translate("Form", "Form"))
        self.groupBox.setTitle(_translate("Form", "Spontaneous Rate"))
        self.radioButton.setText(_translate("Form", "Constant"))
        self.radioButton_2.setText(_translate("Form", "Per-episode"))
        self.checkBox.setText(_translate("Form", "Averaging"))
        self.groupBox_2.setTitle(_translate("Form", "Event Selection"))
        self.groupBox_3.setTitle(_translate("Form", "Amplitude"))
        self.label.setText(_translate("Form", "Mean"))
        self.label_2.setText(_translate("Form", "Stdev"))

