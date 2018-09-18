# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/analysis/modules/STDPAnalyzer/STDPPlotsTemplate.ui'
#
# Created by: PyQt4 UI code generator 4.11.4
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
        Form.resize(545, 664)
        self.verticalLayout = QtGui.QVBoxLayout(Form)
        self.verticalLayout.setMargin(3)
        self.verticalLayout.setSpacing(1)
        self.verticalLayout.setObjectName(_fromUtf8("verticalLayout"))
        self.splitter = QtGui.QSplitter(Form)
        self.splitter.setOrientation(QtCore.Qt.Vertical)
        self.splitter.setObjectName(_fromUtf8("splitter"))
        self.exptPlot = PlotWidget(self.splitter)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.exptPlot.sizePolicy().hasHeightForWidth())
        self.exptPlot.setSizePolicy(sizePolicy)
        self.exptPlot.setObjectName(_fromUtf8("exptPlot"))
        self.tracesPlot = PlotWidget(self.splitter)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(self.tracesPlot.sizePolicy().hasHeightForWidth())
        self.tracesPlot.setSizePolicy(sizePolicy)
        self.tracesPlot.setObjectName(_fromUtf8("tracesPlot"))
        self.plasticityPlot = PlotWidget(self.splitter)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(self.plasticityPlot.sizePolicy().hasHeightForWidth())
        self.plasticityPlot.setSizePolicy(sizePolicy)
        self.plasticityPlot.setObjectName(_fromUtf8("plasticityPlot"))
        self.RMP_plot = PlotWidget(self.splitter)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.RMP_plot.sizePolicy().hasHeightForWidth())
        self.RMP_plot.setSizePolicy(sizePolicy)
        self.RMP_plot.setObjectName(_fromUtf8("RMP_plot"))
        self.RI_plot = PlotWidget(self.splitter)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.RI_plot.sizePolicy().hasHeightForWidth())
        self.RI_plot.setSizePolicy(sizePolicy)
        self.RI_plot.setObjectName(_fromUtf8("RI_plot"))
        self.holdingPlot = PlotWidget(self.splitter)
        self.holdingPlot.setObjectName(_fromUtf8("holdingPlot"))
        self.verticalLayout.addWidget(self.splitter)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))

from acq4.pyqtgraph.widgets.PlotWidget import PlotWidget
