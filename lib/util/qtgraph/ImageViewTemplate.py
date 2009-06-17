# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ImageViewTemplate.ui'
#
# Created: Tue Jun 16 18:46:05 2009
#      by: PyQt4 UI code generator 4.4.4
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(757, 439)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setObjectName("gridLayout")
        self.graphicsView = GraphicsView(Form)
        self.graphicsView.setObjectName("graphicsView")
        self.gridLayout.addWidget(self.graphicsView, 0, 0, 2, 1)
        self.blackSlider = QtGui.QSlider(Form)
        self.blackSlider.setMaximum(4096)
        self.blackSlider.setOrientation(QtCore.Qt.Vertical)
        self.blackSlider.setInvertedAppearance(False)
        self.blackSlider.setInvertedControls(False)
        self.blackSlider.setTickPosition(QtGui.QSlider.TicksBelow)
        self.blackSlider.setTickInterval(410)
        self.blackSlider.setObjectName("blackSlider")
        self.gridLayout.addWidget(self.blackSlider, 0, 1, 1, 1)
        self.whiteSlider = QtGui.QSlider(Form)
        self.whiteSlider.setMaximum(4096)
        self.whiteSlider.setProperty("value", QtCore.QVariant(4096))
        self.whiteSlider.setOrientation(QtCore.Qt.Vertical)
        self.whiteSlider.setObjectName("whiteSlider")
        self.gridLayout.addWidget(self.whiteSlider, 0, 2, 1, 1)
        self.label = QtGui.QLabel(Form)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 1, 1, 1, 1)
        self.label_2 = QtGui.QLabel(Form)
        self.label_2.setObjectName("label_2")
        self.gridLayout.addWidget(self.label_2, 1, 2, 1, 1)
        self.timeSlider = QtGui.QSlider(Form)
        self.timeSlider.setOrientation(QtCore.Qt.Horizontal)
        self.timeSlider.setObjectName("timeSlider")
        self.gridLayout.addWidget(self.timeSlider, 2, 0, 1, 3)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "B", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("Form", "W", None, QtGui.QApplication.UnicodeUTF8))

from GraphicsView import GraphicsView
