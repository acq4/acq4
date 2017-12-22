# -*- coding: utf-8 -*-
from __future__ import print_function

# Form implementation generated from reading ui file 'AnalysisPlotWindow.ui'
#
# Created: Mon Aug 16 22:22:53 2010
#      by: PyQt4 UI code generator 4.5.4
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_AnalysisPlotWindowTemplate(object):
    def setupUi(self, AnalysisPlotWindowTemplate):
        AnalysisPlotWindowTemplate.setObjectName("AnalysisPlotWindowTemplate")
        AnalysisPlotWindowTemplate.resize(465, 407)
        self.gridLayout = QtGui.QGridLayout(AnalysisPlotWindowTemplate)
        self.gridLayout.setObjectName("gridLayout")
        self.splitter_3 = QtGui.QSplitter(AnalysisPlotWindowTemplate)
        self.splitter_3.setOrientation(QtCore.Qt.Horizontal)
        self.splitter_3.setObjectName("splitter_3")
        self.splitter_2 = QtGui.QSplitter(self.splitter_3)
        self.splitter_2.setOrientation(QtCore.Qt.Vertical)
        self.splitter_2.setObjectName("splitter_2")
        self.layoutWidget = QtGui.QWidget(self.splitter_2)
        self.layoutWidget.setObjectName("layoutWidget")
        self.verticalLayout = QtGui.QVBoxLayout(self.layoutWidget)
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.label = QtGui.QLabel(self.layoutWidget)
        self.label.setObjectName("label")
        self.horizontalLayout.addWidget(self.label)
        self.dataSourceCombo = QtGui.QComboBox(self.layoutWidget)
        self.dataSourceCombo.setObjectName("dataSourceCombo")
        self.horizontalLayout.addWidget(self.dataSourceCombo)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.loadDataBtn = QtGui.QPushButton(self.layoutWidget)
        self.loadDataBtn.setObjectName("loadDataBtn")
        self.verticalLayout.addWidget(self.loadDataBtn)
        self.tracePlot = PlotWidget(self.splitter_2)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.tracePlot.sizePolicy().hasHeightForWidth())
        self.tracePlot.setSizePolicy(sizePolicy)
        self.tracePlot.setObjectName("tracePlot")
        self.splitter = QtGui.QSplitter(self.splitter_3)
        self.splitter.setOrientation(QtCore.Qt.Vertical)
        self.splitter.setObjectName("splitter")
        self.addPlotBtn = QtGui.QPushButton(self.splitter)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.MinimumExpanding, QtGui.QSizePolicy.MinimumExpanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.addPlotBtn.sizePolicy().hasHeightForWidth())
        self.addPlotBtn.setSizePolicy(sizePolicy)
        self.addPlotBtn.setMaximumSize(QtCore.QSize(16777215, 32))
        self.addPlotBtn.setObjectName("addPlotBtn")
        self.analysisPlot1 = AnalysisPlotWidget(self.splitter)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.analysisPlot1.sizePolicy().hasHeightForWidth())
        self.analysisPlot1.setSizePolicy(sizePolicy)
        self.analysisPlot1.setObjectName("analysisPlot1")
        self.analysisPlot2 = AnalysisPlotWidget(self.splitter)
        self.analysisPlot2.setObjectName("analysisPlot2")
        self.gridLayout.addWidget(self.splitter_3, 0, 0, 1, 1)

        self.retranslateUi(AnalysisPlotWindowTemplate)
        QtCore.QMetaObject.connectSlotsByName(AnalysisPlotWindowTemplate)

    def retranslateUi(self, AnalysisPlotWindowTemplate):
        AnalysisPlotWindowTemplate.setWindowTitle(QtGui.QApplication.translate("AnalysisPlotWindowTemplate", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("AnalysisPlotWindowTemplate", "Draw data from:", None, QtGui.QApplication.UnicodeUTF8))
        self.loadDataBtn.setText(QtGui.QApplication.translate("AnalysisPlotWindowTemplate", "Load Data", None, QtGui.QApplication.UnicodeUTF8))
        self.addPlotBtn.setText(QtGui.QApplication.translate("AnalysisPlotWindowTemplate", "Add Plot", None, QtGui.QApplication.UnicodeUTF8))

from acq4.pyqtgraph.PlotWidget import PlotWidget
from .AnalysisPlotWidget import AnalysisPlotWidget
