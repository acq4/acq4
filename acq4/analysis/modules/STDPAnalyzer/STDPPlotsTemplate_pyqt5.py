# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/analysis/modules/STDPAnalyzer/STDPPlotsTemplate.ui'
#
# Created by: PyQt5 UI code generator 5.8.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(545, 664)
        self.verticalLayout = QtWidgets.QVBoxLayout(Form)
        self.verticalLayout.setContentsMargins(3, 3, 3, 3)
        self.verticalLayout.setSpacing(1)
        self.verticalLayout.setObjectName("verticalLayout")
        self.splitter = QtWidgets.QSplitter(Form)
        self.splitter.setOrientation(Qt.Qt.Vertical)
        self.splitter.setObjectName("splitter")
        self.exptPlot = PlotWidget(self.splitter)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.exptPlot.sizePolicy().hasHeightForWidth())
        self.exptPlot.setSizePolicy(sizePolicy)
        self.exptPlot.setObjectName("exptPlot")
        self.tracesPlot = PlotWidget(self.splitter)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(self.tracesPlot.sizePolicy().hasHeightForWidth())
        self.tracesPlot.setSizePolicy(sizePolicy)
        self.tracesPlot.setObjectName("tracesPlot")
        self.plasticityPlot = PlotWidget(self.splitter)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(self.plasticityPlot.sizePolicy().hasHeightForWidth())
        self.plasticityPlot.setSizePolicy(sizePolicy)
        self.plasticityPlot.setObjectName("plasticityPlot")
        self.RMP_plot = PlotWidget(self.splitter)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.RMP_plot.sizePolicy().hasHeightForWidth())
        self.RMP_plot.setSizePolicy(sizePolicy)
        self.RMP_plot.setObjectName("RMP_plot")
        self.RI_plot = PlotWidget(self.splitter)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.RI_plot.sizePolicy().hasHeightForWidth())
        self.RI_plot.setSizePolicy(sizePolicy)
        self.RI_plot.setObjectName("RI_plot")
        self.holdingPlot = PlotWidget(self.splitter)
        self.holdingPlot.setObjectName("holdingPlot")
        self.verticalLayout.addWidget(self.splitter)

        self.retranslateUi(Form)
        Qt.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        _translate = Qt.QCoreApplication.translate
        Form.setWindowTitle(_translate("Form", "Form"))

from acq4.pyqtgraph.widgets.PlotWidget import PlotWidget
