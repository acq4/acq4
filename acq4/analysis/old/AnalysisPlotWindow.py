# -*- coding: utf-8 -*-
from __future__ import print_function

# Form implementation generated from reading ui file 'AnalysisPlotWindow.ui'
#
# Created: Mon Aug 16 15:31:55 2010
#      by: PyQt4 UI code generator 4.5.4
#
# WARNING! All changes made in this file will be lost!

from acq4.util import Qt

class Ui_AnalysisPlotWindowTemplate(object):
    def setupUi(self, AnalysisPlotWindowTemplate):
        AnalysisPlotWindowTemplate.setObjectName("AnalysisPlotWindowTemplate")
        AnalysisPlotWindowTemplate.resize(465, 407)
        self.gridLayout = Qt.QGridLayout(AnalysisPlotWindowTemplate)
        self.gridLayout.setObjectName("gridLayout")
        self.splitter_3 = Qt.QSplitter(AnalysisPlotWindowTemplate)
        self.splitter_3.setOrientation(Qt.Qt.Horizontal)
        self.splitter_3.setObjectName("splitter_3")
        self.splitter_2 = Qt.QSplitter(self.splitter_3)
        self.splitter_2.setOrientation(Qt.Qt.Vertical)
        self.splitter_2.setObjectName("splitter_2")
        self.widget = Qt.QWidget(self.splitter_2)
        self.widget.setObjectName("widget")
        self.verticalLayout = Qt.QVBoxLayout(self.widget)
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout = Qt.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.label = Qt.QLabel(self.widget)
        self.label.setObjectName("label")
        self.horizontalLayout.addWidget(self.label)
        self.comboBox = Qt.QComboBox(self.widget)
        self.comboBox.setObjectName("comboBox")
        self.horizontalLayout.addWidget(self.comboBox)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.loadDataBtn = Qt.QPushButton(self.widget)
        self.loadDataBtn.setObjectName("loadDataBtn")
        self.verticalLayout.addWidget(self.loadDataBtn)
        self.widget1 = PlotWidget(self.splitter_2)
        sizePolicy = Qt.QSizePolicy(Qt.QSizePolicy.Preferred, Qt.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.widget1.sizePolicy().hasHeightForWidth())
        self.widget1.setSizePolicy(sizePolicy)
        self.widget1.setObjectName("widget1")
        self.splitter = Qt.QSplitter(self.splitter_3)
        self.splitter.setOrientation(Qt.Qt.Vertical)
        self.splitter.setObjectName("splitter")
        self.addPlotBtn = Qt.QPushButton(self.splitter)
        sizePolicy = Qt.QSizePolicy(Qt.QSizePolicy.MinimumExpanding, Qt.QSizePolicy.MinimumExpanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.addPlotBtn.sizePolicy().hasHeightForWidth())
        self.addPlotBtn.setSizePolicy(sizePolicy)
        self.addPlotBtn.setMaximumSize(Qt.QSize(16777215, 32))
        self.addPlotBtn.setObjectName("addPlotBtn")
        self.widget_2 = AnalysisPlotWidget(self.splitter)
        sizePolicy = Qt.QSizePolicy(Qt.QSizePolicy.Preferred, Qt.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.widget_2.sizePolicy().hasHeightForWidth())
        self.widget_2.setSizePolicy(sizePolicy)
        self.widget_2.setObjectName("widget_2")
        self.widget_3 = AnalysisPlotWidget(self.splitter)
        self.widget_3.setObjectName("widget_3")
        self.gridLayout.addWidget(self.splitter_3, 0, 0, 1, 1)

        self.retranslateUi(AnalysisPlotWindowTemplate)
        Qt.QMetaObject.connectSlotsByName(AnalysisPlotWindowTemplate)

    def retranslateUi(self, AnalysisPlotWindowTemplate):
        AnalysisPlotWindowTemplate.setWindowTitle(Qt.QApplication.translate("AnalysisPlotWindowTemplate", "Form", None, Qt.QApplication.UnicodeUTF8))
        self.label.setText(Qt.QApplication.translate("AnalysisPlotWindowTemplate", "Draw data from:", None, Qt.QApplication.UnicodeUTF8))
        self.loadDataBtn.setText(Qt.QApplication.translate("AnalysisPlotWindowTemplate", "Load Data", None, Qt.QApplication.UnicodeUTF8))
        self.addPlotBtn.setText(Qt.QApplication.translate("AnalysisPlotWindowTemplate", "Add Plot", None, Qt.QApplication.UnicodeUTF8))

from acq4.pyqtgraph.PlotWidget import PlotWidget
from .AnalysisPlotWidget import AnalysisPlotWidget
