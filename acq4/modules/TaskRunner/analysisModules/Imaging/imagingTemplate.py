# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './acq4/modules/TaskRunner/analysisModules/Imaging/imagingTemplate.ui'
#
# Created: Tue Dec 24 01:49:11 2013
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

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName(_fromUtf8("Form"))
        Form.resize(368, 416)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 0, 0, 1, 1)
        self.scannerComboBox = InterfaceCombo(Form)
        self.scannerComboBox.setObjectName(_fromUtf8("scannerComboBox"))
        self.gridLayout.addWidget(self.scannerComboBox, 0, 1, 1, 1)
        self.label_3 = QtGui.QLabel(Form)
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.gridLayout.addWidget(self.label_3, 0, 2, 1, 1)
        self.downSampling = QtGui.QSpinBox(Form)
        self.downSampling.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.downSampling.setMinimum(1)
        self.downSampling.setMaximum(1000)
        self.downSampling.setProperty("value", 1)
        self.downSampling.setObjectName(_fromUtf8("downSampling"))
        self.gridLayout.addWidget(self.downSampling, 0, 3, 1, 1)
        spacerItem = QtGui.QSpacerItem(68, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridLayout.addItem(spacerItem, 0, 4, 1, 1)
        self.label_2 = QtGui.QLabel(Form)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout.addWidget(self.label_2, 1, 0, 1, 1)
        self.detectorComboBox = InterfaceCombo(Form)
        self.detectorComboBox.setObjectName(_fromUtf8("detectorComboBox"))
        self.gridLayout.addWidget(self.detectorComboBox, 1, 1, 1, 1)
        self.label_4 = QtGui.QLabel(Form)
        self.label_4.setObjectName(_fromUtf8("label_4"))
        self.gridLayout.addWidget(self.label_4, 1, 2, 1, 1)
        self.alphaSlider = QtGui.QSlider(Form)
        self.alphaSlider.setMaximum(100)
        self.alphaSlider.setSingleStep(2)
        self.alphaSlider.setProperty("value", 0)
        self.alphaSlider.setOrientation(QtCore.Qt.Horizontal)
        self.alphaSlider.setInvertedAppearance(False)
        self.alphaSlider.setInvertedControls(True)
        self.alphaSlider.setTickPosition(QtGui.QSlider.TicksBelow)
        self.alphaSlider.setObjectName(_fromUtf8("alphaSlider"))
        self.gridLayout.addWidget(self.alphaSlider, 1, 3, 1, 1)
        spacerItem1 = QtGui.QSpacerItem(85, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridLayout.addItem(spacerItem1, 1, 4, 1, 1)
        self.plotWidget = ImageView(Form)
        self.plotWidget.setObjectName(_fromUtf8("plotWidget"))
        self.gridLayout.addWidget(self.plotWidget, 2, 0, 1, 5)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.label.setText(_translate("Form", "Scanner", None))
        self.label_3.setText(_translate("Form", "Downsampling", None))
        self.label_2.setText(_translate("Form", "Detector", None))
        self.label_4.setText(_translate("Form", "ROI alpha", None))

from acq4.pyqtgraph import ImageView
from acq4.util.InterfaceCombo import InterfaceCombo
