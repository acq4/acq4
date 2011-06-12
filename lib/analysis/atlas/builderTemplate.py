# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'builderTemplate.ui'
#
# Created: Sun Jun 12 10:59:19 2011
#      by: PyQt4 UI code generator 4.8.3
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
        Form.resize(663, 521)
        self.gridLayout_4 = QtGui.QGridLayout(Form)
        self.gridLayout_4.setObjectName(_fromUtf8("gridLayout_4"))
        self.view = GraphicsView(Form)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(10)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.view.sizePolicy().hasHeightForWidth())
        self.view.setSizePolicy(sizePolicy)
        self.view.setObjectName(_fromUtf8("view"))
        self.gridLayout_4.addWidget(self.view, 0, 0, 3, 1)
        self.groupBox = QtGui.QGroupBox(Form)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.groupBox.sizePolicy().hasHeightForWidth())
        self.groupBox.setSizePolicy(sizePolicy)
        self.groupBox.setObjectName(_fromUtf8("groupBox"))
        self.gridLayout = QtGui.QGridLayout(self.groupBox)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.dorsalRadio = QtGui.QRadioButton(self.groupBox)
        self.dorsalRadio.setObjectName(_fromUtf8("dorsalRadio"))
        self.gridLayout.addWidget(self.dorsalRadio, 1, 1, 1, 1)
        self.rostralRadio = QtGui.QRadioButton(self.groupBox)
        self.rostralRadio.setObjectName(_fromUtf8("rostralRadio"))
        self.gridLayout.addWidget(self.rostralRadio, 2, 1, 1, 1)
        self.rightRadio = QtGui.QRadioButton(self.groupBox)
        self.rightRadio.setChecked(True)
        self.rightRadio.setObjectName(_fromUtf8("rightRadio"))
        self.gridLayout.addWidget(self.rightRadio, 0, 1, 1, 1)
        self.gridLayout_4.addWidget(self.groupBox, 0, 1, 1, 1)
        self.groupBox_3 = QtGui.QGroupBox(Form)
        self.groupBox_3.setObjectName(_fromUtf8("groupBox_3"))
        self.gridLayout_3 = QtGui.QGridLayout(self.groupBox_3)
        self.gridLayout_3.setObjectName(_fromUtf8("gridLayout_3"))
        self.label = QtGui.QLabel(self.groupBox_3)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout_3.addWidget(self.label, 0, 0, 1, 1)
        self.radiusSpin = QtGui.QSpinBox(self.groupBox_3)
        self.radiusSpin.setMinimum(1)
        self.radiusSpin.setObjectName(_fromUtf8("radiusSpin"))
        self.gridLayout_3.addWidget(self.radiusSpin, 0, 1, 1, 1)
        self.label_2 = QtGui.QLabel(self.groupBox_3)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout_3.addWidget(self.label_2, 1, 0, 1, 1)
        self.labelSpin = QtGui.QSpinBox(self.groupBox_3)
        self.labelSpin.setObjectName(_fromUtf8("labelSpin"))
        self.gridLayout_3.addWidget(self.labelSpin, 1, 1, 1, 1)
        self.gridLayout_4.addWidget(self.groupBox_3, 1, 1, 1, 1)
        self.groupBox_2 = QtGui.QGroupBox(Form)
        self.groupBox_2.setObjectName(_fromUtf8("groupBox_2"))
        self.gridLayout_2 = QtGui.QGridLayout(self.groupBox_2)
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
        self.labelTree = TreeWidget(self.groupBox_2)
        self.labelTree.setHeaderHidden(True)
        self.labelTree.setObjectName(_fromUtf8("labelTree"))
        self.labelTree.headerItem().setText(0, _fromUtf8("1"))
        self.gridLayout_2.addWidget(self.labelTree, 0, 0, 1, 1)
        self.gridLayout_4.addWidget(self.groupBox_2, 2, 1, 2, 1)
        self.zSlider = QtGui.QSlider(Form)
        self.zSlider.setOrientation(QtCore.Qt.Horizontal)
        self.zSlider.setObjectName(_fromUtf8("zSlider"))
        self.gridLayout_4.addWidget(self.zSlider, 3, 0, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox.setTitle(QtGui.QApplication.translate("Form", "View", None, QtGui.QApplication.UnicodeUTF8))
        self.dorsalRadio.setText(QtGui.QApplication.translate("Form", "Dorsal", None, QtGui.QApplication.UnicodeUTF8))
        self.rostralRadio.setText(QtGui.QApplication.translate("Form", "Rostral", None, QtGui.QApplication.UnicodeUTF8))
        self.rightRadio.setText(QtGui.QApplication.translate("Form", "Right", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox_3.setTitle(QtGui.QApplication.translate("Form", "Drawing", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Radius", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("Form", "Label", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox_2.setTitle(QtGui.QApplication.translate("Form", "Labels", None, QtGui.QApplication.UnicodeUTF8))

from TreeWidget import TreeWidget
from pyqtgraph.GraphicsView import GraphicsView
