# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/modules/TaskRunner/analysisModules/Imaging/imagingTemplate.ui'
#
# Created by: PyQt5 UI code generator 5.8.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(368, 416)
        self.gridLayout = QtWidgets.QGridLayout(Form)
        self.gridLayout.setObjectName("gridLayout")
        self.label = QtWidgets.QLabel(Form)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 0, 0, 1, 1)
        self.scannerComboBox = InterfaceCombo(Form)
        self.scannerComboBox.setObjectName("scannerComboBox")
        self.gridLayout.addWidget(self.scannerComboBox, 0, 1, 1, 1)
        self.label_3 = QtWidgets.QLabel(Form)
        self.label_3.setObjectName("label_3")
        self.gridLayout.addWidget(self.label_3, 0, 2, 1, 1)
        self.downSampling = QtWidgets.QSpinBox(Form)
        self.downSampling.setAlignment(Qt.Qt.AlignRight|Qt.Qt.AlignTrailing|Qt.Qt.AlignVCenter)
        self.downSampling.setMinimum(1)
        self.downSampling.setMaximum(1000)
        self.downSampling.setProperty("value", 1)
        self.downSampling.setObjectName("downSampling")
        self.gridLayout.addWidget(self.downSampling, 0, 3, 1, 1)
        spacerItem = QtWidgets.QSpacerItem(68, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.gridLayout.addItem(spacerItem, 0, 4, 1, 1)
        self.label_2 = QtWidgets.QLabel(Form)
        self.label_2.setObjectName("label_2")
        self.gridLayout.addWidget(self.label_2, 1, 0, 1, 1)
        self.detectorComboBox = InterfaceCombo(Form)
        self.detectorComboBox.setObjectName("detectorComboBox")
        self.gridLayout.addWidget(self.detectorComboBox, 1, 1, 1, 1)
        self.label_4 = QtWidgets.QLabel(Form)
        self.label_4.setObjectName("label_4")
        self.gridLayout.addWidget(self.label_4, 1, 2, 1, 1)
        self.alphaSlider = QtWidgets.QSlider(Form)
        self.alphaSlider.setMaximum(100)
        self.alphaSlider.setSingleStep(2)
        self.alphaSlider.setProperty("value", 0)
        self.alphaSlider.setOrientation(Qt.Qt.Horizontal)
        self.alphaSlider.setInvertedAppearance(False)
        self.alphaSlider.setInvertedControls(True)
        self.alphaSlider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        self.alphaSlider.setObjectName("alphaSlider")
        self.gridLayout.addWidget(self.alphaSlider, 1, 3, 1, 1)
        spacerItem1 = QtWidgets.QSpacerItem(85, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.gridLayout.addItem(spacerItem1, 1, 4, 1, 1)
        self.plotWidget = ImageView(Form)
        self.plotWidget.setObjectName("plotWidget")
        self.gridLayout.addWidget(self.plotWidget, 2, 0, 1, 5)

        self.retranslateUi(Form)
        Qt.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        _translate = Qt.QCoreApplication.translate
        Form.setWindowTitle(_translate("Form", "Form"))
        self.label.setText(_translate("Form", "Scanner"))
        self.label_3.setText(_translate("Form", "Downsampling"))
        self.label_2.setText(_translate("Form", "Detector"))
        self.label_4.setText(_translate("Form", "ROI alpha"))

from acq4.pyqtgraph import ImageView
from acq4.util.InterfaceCombo import InterfaceCombo
