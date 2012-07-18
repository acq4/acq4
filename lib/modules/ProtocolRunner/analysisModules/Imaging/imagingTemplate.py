# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '.\lib\modules\ProtocolRunner\analysisModules\Imaging\imagingTemplate.ui'
#
# Created: Wed Jul 18 15:13:00 2012
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
        Form.resize(337, 416)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.scannerComboBox = InterfaceCombo(Form)
        self.scannerComboBox.setObjectName(_fromUtf8("scannerComboBox"))
        self.gridLayout.addWidget(self.scannerComboBox, 0, 1, 1, 1)
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 0, 0, 1, 1)
        self.downSampling = QtGui.QSpinBox(Form)
        self.downSampling.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.downSampling.setMinimum(1)
        self.downSampling.setMaximum(1000)
        self.downSampling.setProperty("value", 1)
        self.downSampling.setObjectName(_fromUtf8("downSampling"))
        self.gridLayout.addWidget(self.downSampling, 0, 3, 1, 1)
        self.detectorComboBox = InterfaceCombo(Form)
        self.detectorComboBox.setObjectName(_fromUtf8("detectorComboBox"))
        self.gridLayout.addWidget(self.detectorComboBox, 1, 1, 1, 1)
        self.label_2 = QtGui.QLabel(Form)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout.addWidget(self.label_2, 1, 0, 1, 1)
        self.label_3 = QtGui.QLabel(Form)
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.gridLayout.addWidget(self.label_3, 0, 2, 1, 1)
        self.splitter = QtGui.QSplitter(Form)
        self.splitter.setOrientation(QtCore.Qt.Horizontal)
        self.splitter.setObjectName(_fromUtf8("splitter"))
        self.plotWidget = PlotWidget(self.splitter)
        self.plotWidget.setObjectName(_fromUtf8("plotWidget"))
        self.histogram = HistogramLUTWidget(self.splitter)
        self.histogram.setObjectName(_fromUtf8("histogram"))
        self.gridLayout.addWidget(self.splitter, 6, 0, 1, 4)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Scanner", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("Form", "Detector", None, QtGui.QApplication.UnicodeUTF8))
        self.label_3.setText(QtGui.QApplication.translate("Form", "Downsampling", None, QtGui.QApplication.UnicodeUTF8))

from pyqtgraph import HistogramLUTWidget, PlotWidget
from InterfaceCombo import InterfaceCombo
