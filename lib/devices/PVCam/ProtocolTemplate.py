# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ProtocolTemplate.ui'
#
# Created: Mon Apr 27 11:43:34 2009
#      by: PyQt4 UI code generator 4.4.4
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(718, 444)
        self.horizontalLayout = QtGui.QHBoxLayout(Form)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.splitter = QtGui.QSplitter(Form)
        self.splitter.setOrientation(QtCore.Qt.Horizontal)
        self.splitter.setObjectName("splitter")
        self.layoutWidget = QtGui.QWidget(self.splitter)
        self.layoutWidget.setObjectName("layoutWidget")
        self.verticalLayout = QtGui.QVBoxLayout(self.layoutWidget)
        self.verticalLayout.setObjectName("verticalLayout")
        self.recordCheck = QtGui.QCheckBox(self.layoutWidget)
        self.recordCheck.setObjectName("recordCheck")
        self.verticalLayout.addWidget(self.recordCheck)
        self.triggerCheck = QtGui.QCheckBox(self.layoutWidget)
        self.triggerCheck.setObjectName("triggerCheck")
        self.verticalLayout.addWidget(self.triggerCheck)
        self.displayCheck = QtGui.QCheckBox(self.layoutWidget)
        self.displayCheck.setObjectName("displayCheck")
        self.verticalLayout.addWidget(self.displayCheck)
        self.recordExposeCheck = QtGui.QCheckBox(self.layoutWidget)
        self.recordExposeCheck.setObjectName("recordExposeCheck")
        self.verticalLayout.addWidget(self.recordExposeCheck)
        spacerItem = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.verticalLayout.addItem(spacerItem)
        self.layoutWidget1 = QtGui.QWidget(self.splitter)
        self.layoutWidget1.setObjectName("layoutWidget1")
        self.gridLayout = QtGui.QGridLayout(self.layoutWidget1)
        self.gridLayout.setObjectName("gridLayout")
        self.widget = QtGui.QWidget(self.layoutWidget1)
        self.widget.setObjectName("widget")
        self.gridLayout.addWidget(self.widget, 0, 0, 1, 1)
        self.verticalSlider = QtGui.QSlider(self.layoutWidget1)
        self.verticalSlider.setOrientation(QtCore.Qt.Vertical)
        self.verticalSlider.setObjectName("verticalSlider")
        self.gridLayout.addWidget(self.verticalSlider, 0, 1, 1, 1)
        self.verticalSlider_2 = QtGui.QSlider(self.layoutWidget1)
        self.verticalSlider_2.setOrientation(QtCore.Qt.Vertical)
        self.verticalSlider_2.setObjectName("verticalSlider_2")
        self.gridLayout.addWidget(self.verticalSlider_2, 0, 2, 1, 1)
        self.horizontalSlider = QtGui.QSlider(self.layoutWidget1)
        self.horizontalSlider.setOrientation(QtCore.Qt.Horizontal)
        self.horizontalSlider.setObjectName("horizontalSlider")
        self.gridLayout.addWidget(self.horizontalSlider, 1, 0, 1, 1)
        self.label = QtGui.QLabel(self.layoutWidget1)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 1, 1, 1, 1)
        self.label_2 = QtGui.QLabel(self.layoutWidget1)
        self.label_2.setObjectName("label_2")
        self.gridLayout.addWidget(self.label_2, 1, 2, 1, 1)
        self.horizontalLayout.addWidget(self.splitter)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.recordCheck.setText(QtGui.QApplication.translate("Form", "Record", None, QtGui.QApplication.UnicodeUTF8))
        self.triggerCheck.setText(QtGui.QApplication.translate("Form", "Trigger", None, QtGui.QApplication.UnicodeUTF8))
        self.displayCheck.setText(QtGui.QApplication.translate("Form", "Display", None, QtGui.QApplication.UnicodeUTF8))
        self.recordExposeCheck.setText(QtGui.QApplication.translate("Form", "Record Expose Channel", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "B", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("Form", "W", None, QtGui.QApplication.UnicodeUTF8))

