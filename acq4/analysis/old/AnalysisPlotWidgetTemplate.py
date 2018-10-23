# -*- coding: utf-8 -*-
from __future__ import print_function

# Form implementation generated from reading ui file 'AnalysisPlotWidgetTemplate.ui'
#
# Created: Mon Aug 16 15:31:49 2010
#      by: PyQt4 UI code generator 4.5.4
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_AnalysisPlotWidgetTemplate(object):
    def setupUi(self, AnalysisPlotWidgetTemplate):
        AnalysisPlotWidgetTemplate.setObjectName("AnalysisPlotWidgetTemplate")
        AnalysisPlotWidgetTemplate.resize(692, 423)
        self.gridLayout = QtGui.QGridLayout(AnalysisPlotWidgetTemplate)
        self.gridLayout.setObjectName("gridLayout")
        self.verticalLayout = QtGui.QVBoxLayout()
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout_3 = QtGui.QHBoxLayout()
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.label = QtGui.QLabel(AnalysisPlotWidgetTemplate)
        self.label.setObjectName("label")
        self.horizontalLayout.addWidget(self.label)
        self.xAxisCombo = QtGui.QComboBox(AnalysisPlotWidgetTemplate)
        self.xAxisCombo.setObjectName("xAxisCombo")
        self.horizontalLayout.addWidget(self.xAxisCombo)
        self.horizontalLayout_3.addLayout(self.horizontalLayout)
        self.horizontalLayout_2 = QtGui.QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.label_2 = QtGui.QLabel(AnalysisPlotWidgetTemplate)
        self.label_2.setObjectName("label_2")
        self.horizontalLayout_2.addWidget(self.label_2)
        self.yAxisCombo = QtGui.QComboBox(AnalysisPlotWidgetTemplate)
        self.yAxisCombo.setObjectName("yAxisCombo")
        self.horizontalLayout_2.addWidget(self.yAxisCombo)
        self.horizontalLayout_3.addLayout(self.horizontalLayout_2)
        spacerItem = QtGui.QSpacerItem(188, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.horizontalLayout_3.addItem(spacerItem)
        self.removeBtn = QtGui.QPushButton(AnalysisPlotWidgetTemplate)
        self.removeBtn.setObjectName("removeBtn")
        self.horizontalLayout_3.addWidget(self.removeBtn)
        self.verticalLayout.addLayout(self.horizontalLayout_3)
        self.gridLayout.addLayout(self.verticalLayout, 0, 0, 1, 1)
        self.widget = PlotWidget(AnalysisPlotWidgetTemplate)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.widget.sizePolicy().hasHeightForWidth())
        self.widget.setSizePolicy(sizePolicy)
        self.widget.setObjectName("widget")
        self.gridLayout.addWidget(self.widget, 1, 0, 1, 1)

        self.retranslateUi(AnalysisPlotWidgetTemplate)
        QtCore.QMetaObject.connectSlotsByName(AnalysisPlotWidgetTemplate)

    def retranslateUi(self, AnalysisPlotWidgetTemplate):
        AnalysisPlotWidgetTemplate.setWindowTitle(QtGui.QApplication.translate("AnalysisPlotWidgetTemplate", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("AnalysisPlotWidgetTemplate", "x axis:", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("AnalysisPlotWidgetTemplate", "y axis:", None, QtGui.QApplication.UnicodeUTF8))
        self.removeBtn.setText(QtGui.QApplication.translate("AnalysisPlotWidgetTemplate", "Remove", None, QtGui.QApplication.UnicodeUTF8))

from acq4.pyqtgraph.PlotWidget import PlotWidget
