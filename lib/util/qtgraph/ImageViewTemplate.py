# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ImageViewTemplate.ui'
#
# Created: Wed Sep 02 12:29:18 2009
#      by: PyQt4 UI code generator 4.5.4
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(757, 495)
        self.verticalLayout = QtGui.QVBoxLayout(Form)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setMargin(0)
        self.verticalLayout.setObjectName("verticalLayout")
        self.splitter = QtGui.QSplitter(Form)
        self.splitter.setOrientation(QtCore.Qt.Vertical)
        self.splitter.setObjectName("splitter")
        self.widget = QtGui.QWidget(self.splitter)
        self.widget.setObjectName("widget")
        self.gridLayout = QtGui.QGridLayout(self.widget)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName("gridLayout")
        self.graphicsView = GraphicsView(self.widget)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.graphicsView.sizePolicy().hasHeightForWidth())
        self.graphicsView.setSizePolicy(sizePolicy)
        self.graphicsView.setObjectName("graphicsView")
        self.gridLayout.addWidget(self.graphicsView, 0, 0, 3, 1)
        self.blackSlider = QtGui.QSlider(self.widget)
        self.blackSlider.setMaximum(4096)
        self.blackSlider.setOrientation(QtCore.Qt.Vertical)
        self.blackSlider.setInvertedAppearance(False)
        self.blackSlider.setInvertedControls(False)
        self.blackSlider.setTickPosition(QtGui.QSlider.TicksBelow)
        self.blackSlider.setTickInterval(410)
        self.blackSlider.setObjectName("blackSlider")
        self.gridLayout.addWidget(self.blackSlider, 0, 1, 1, 1)
        self.whiteSlider = QtGui.QSlider(self.widget)
        self.whiteSlider.setMaximum(4096)
        self.whiteSlider.setProperty("value", QtCore.QVariant(4096))
        self.whiteSlider.setOrientation(QtCore.Qt.Vertical)
        self.whiteSlider.setObjectName("whiteSlider")
        self.gridLayout.addWidget(self.whiteSlider, 0, 2, 1, 2)
        self.label = QtGui.QLabel(self.widget)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 1, 1, 1, 1)
        self.label_2 = QtGui.QLabel(self.widget)
        self.label_2.setObjectName("label_2")
        self.gridLayout.addWidget(self.label_2, 1, 2, 1, 2)
        self.roiBtn = QtGui.QPushButton(self.widget)
        self.roiBtn.setMaximumSize(QtCore.QSize(30, 16777215))
        self.roiBtn.setCheckable(True)
        self.roiBtn.setObjectName("roiBtn")
        self.gridLayout.addWidget(self.roiBtn, 2, 1, 1, 3)
        self.timeSlider = QtGui.QSlider(self.widget)
        self.timeSlider.setMaximum(65535)
        self.timeSlider.setOrientation(QtCore.Qt.Horizontal)
        self.timeSlider.setObjectName("timeSlider")
        self.gridLayout.addWidget(self.timeSlider, 3, 0, 1, 4)
        self.roiPlot = PlotWidget(self.splitter)
        self.roiPlot.setMinimumSize(QtCore.QSize(0, 40))
        self.roiPlot.setObjectName("roiPlot")
        self.verticalLayout.addWidget(self.splitter)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "B", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("Form", "W", None, QtGui.QApplication.UnicodeUTF8))
        self.roiBtn.setText(QtGui.QApplication.translate("Form", "ROI", None, QtGui.QApplication.UnicodeUTF8))

from lib.util.PlotWidget import PlotWidget
from GraphicsView import GraphicsView
