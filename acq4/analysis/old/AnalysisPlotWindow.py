# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'AnalysisPlotWindow.ui'
#
# Created: Mon Aug 16 15:31:55 2010
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
        self.widget = QtGui.QWidget(self.splitter_2)
        self.widget.setObjectName("widget")
        self.verticalLayout = QtGui.QVBoxLayout(self.widget)
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.label = QtGui.QLabel(self.widget)
        self.label.setObjectName("label")
        self.horizontalLayout.addWidget(self.label)
        self.comboBox = QtGui.QComboBox(self.widget)
        self.comboBox.setObjectName("comboBox")
        self.horizontalLayout.addWidget(self.comboBox)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.loadDataBtn = QtGui.QPushButton(self.widget)
        self.loadDataBtn.setObjectName("loadDataBtn")
        self.verticalLayout.addWidget(self.loadDataBtn)
        self.widget1 = PlotWidget(self.splitter_2)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.widget1.sizePolicy().hasHeightForWidth())
        self.widget1.setSizePolicy(sizePolicy)
        self.widget1.setObjectName("widget1")
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
        self.widget_2 = AnalysisPlotWidget(self.splitter)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.widget_2.sizePolicy().hasHeightForWidth())
        self.widget_2.setSizePolicy(sizePolicy)
        self.widget_2.setObjectName("widget_2")
        self.widget_3 = AnalysisPlotWidget(self.splitter)
        self.widget_3.setObjectName("widget_3")
        self.gridLayout.addWidget(self.splitter_3, 0, 0, 1, 1)

        self.retranslateUi(AnalysisPlotWindowTemplate)
        QtCore.QMetaObject.connectSlotsByName(AnalysisPlotWindowTemplate)

    def retranslateUi(self, AnalysisPlotWindowTemplate):
        AnalysisPlotWindowTemplate.setWindowTitle(QtGui.QApplication.translate("AnalysisPlotWindowTemplate", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("AnalysisPlotWindowTemplate", "Draw data from:", None, QtGui.QApplication.UnicodeUTF8))
        self.loadDataBtn.setText(QtGui.QApplication.translate("AnalysisPlotWindowTemplate", "Load Data", None, QtGui.QApplication.UnicodeUTF8))
        self.addPlotBtn.setText(QtGui.QApplication.translate("AnalysisPlotWindowTemplate", "Add Plot", None, QtGui.QApplication.UnicodeUTF8))

from acq4.pyqtgraph.PlotWidget import PlotWidget
from AnalysisPlotWidget import AnalysisPlotWidget
