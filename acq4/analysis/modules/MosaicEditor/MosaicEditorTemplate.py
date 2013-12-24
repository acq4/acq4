# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './acq4/analysis/modules/MosaicEditor/MosaicEditorTemplate.ui'
#
# Created: Tue Dec 24 01:49:12 2013
#      by: PyQt4 UI code generator 4.10
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
        Form.resize(784, 137)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.splitter_2 = QtGui.QSplitter(Form)
        self.splitter_2.setOrientation(QtCore.Qt.Horizontal)
        self.splitter_2.setObjectName(_fromUtf8("splitter_2"))
        self.splitter = QtGui.QSplitter(self.splitter_2)
        self.splitter.setOrientation(QtCore.Qt.Vertical)
        self.splitter.setObjectName(_fromUtf8("splitter"))
        self.layoutWidget = QtGui.QWidget(self.splitter)
        self.layoutWidget.setObjectName(_fromUtf8("layoutWidget"))
        self.gridLayout_3 = QtGui.QGridLayout(self.layoutWidget)
        self.gridLayout_3.setMargin(0)
        self.gridLayout_3.setObjectName(_fromUtf8("gridLayout_3"))
        self.groupBox_2 = QtGui.QGroupBox(self.layoutWidget)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(10)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.groupBox_2.sizePolicy().hasHeightForWidth())
        self.groupBox_2.setSizePolicy(sizePolicy)
        self.groupBox_2.setObjectName(_fromUtf8("groupBox_2"))
        self.verticalLayout = QtGui.QVBoxLayout(self.groupBox_2)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setMargin(0)
        self.verticalLayout.setObjectName(_fromUtf8("verticalLayout"))
        self.normalizeBtn = QtGui.QPushButton(self.groupBox_2)
        self.normalizeBtn.setObjectName(_fromUtf8("normalizeBtn"))
        self.verticalLayout.addWidget(self.normalizeBtn)
        self.blendBtn = QtGui.QPushButton(self.groupBox_2)
        self.blendBtn.setObjectName(_fromUtf8("blendBtn"))
        self.verticalLayout.addWidget(self.blendBtn)
        self.autoRangeBtn = QtGui.QPushButton(self.groupBox_2)
        self.autoRangeBtn.setObjectName(_fromUtf8("autoRangeBtn"))
        self.verticalLayout.addWidget(self.autoRangeBtn)
        spacerItem = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.verticalLayout.addItem(spacerItem)
        self.gridLayout_3.addWidget(self.groupBox_2, 0, 1, 1, 1)
        self.frame_3 = QtGui.QFrame(self.layoutWidget)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(100)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.frame_3.sizePolicy().hasHeightForWidth())
        self.frame_3.setSizePolicy(sizePolicy)
        self.frame_3.setObjectName(_fromUtf8("frame_3"))
        self.gridLayout_2 = QtGui.QGridLayout(self.frame_3)
        self.gridLayout_2.setMargin(0)
        self.gridLayout_2.setSpacing(0)
        self.gridLayout_2.setObjectName(_fromUtf8("gridLayout_2"))
        self.atlasCombo = QtGui.QComboBox(self.frame_3)
        self.atlasCombo.setObjectName(_fromUtf8("atlasCombo"))
        self.atlasCombo.addItem(_fromUtf8(""))
        self.gridLayout_2.addWidget(self.atlasCombo, 0, 0, 1, 1)
        self.atlasLayout = QtGui.QGridLayout()
        self.atlasLayout.setSpacing(0)
        self.atlasLayout.setObjectName(_fromUtf8("atlasLayout"))
        self.gridLayout_2.addLayout(self.atlasLayout, 1, 0, 1, 1)
        self.gridLayout_3.addWidget(self.frame_3, 0, 0, 1, 1)
        self.gridLayout.addWidget(self.splitter_2, 0, 0, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.groupBox_2.setTitle(_translate("Form", "Image Correction", None))
        self.normalizeBtn.setText(_translate("Form", "Normalize", None))
        self.blendBtn.setText(_translate("Form", "Blend", None))
        self.autoRangeBtn.setText(_translate("Form", "Auto Range", None))
        self.atlasCombo.setItemText(0, _translate("Form", "Select Atlas...", None))

