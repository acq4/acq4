# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/analysis/modules/MosaicEditor/MosaicEditorTemplate.ui'
#
# Created: Wed Jan 15 11:45:14 2014
#      by: PyQt4 UI code generator 4.9.1
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
        Form.resize(777, 153)
        self.groupBox = QtGui.QGroupBox(Form)
        self.groupBox.setGeometry(QtCore.QRect(610, 0, 161, 151))
        self.groupBox.setObjectName(_fromUtf8("groupBox"))
        self.mosaicFlipUDBtn = QtGui.QPushButton(self.groupBox)
        self.mosaicFlipUDBtn.setGeometry(QtCore.QRect(70, 110, 71, 32))
        self.mosaicFlipUDBtn.setObjectName(_fromUtf8("mosaicFlipUDBtn"))
        self.mosaicDisplayMin = QtGui.QDoubleSpinBox(self.groupBox)
        self.mosaicDisplayMin.setGeometry(QtCore.QRect(70, 20, 65, 25))
        self.mosaicDisplayMin.setMinimum(-1.0)
        self.mosaicDisplayMin.setMaximum(65000.0)
        self.mosaicDisplayMin.setSingleStep(0.25)
        self.mosaicDisplayMin.setObjectName(_fromUtf8("mosaicDisplayMin"))
        self.mosaicApplyScaleBtn = QtGui.QPushButton(self.groupBox)
        self.mosaicApplyScaleBtn.setGeometry(QtCore.QRect(0, 80, 141, 32))
        self.mosaicApplyScaleBtn.setObjectName(_fromUtf8("mosaicApplyScaleBtn"))
        self.label_2 = QtGui.QLabel(self.groupBox)
        self.label_2.setGeometry(QtCore.QRect(10, 30, 62, 16))
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.label = QtGui.QLabel(self.groupBox)
        self.label.setGeometry(QtCore.QRect(10, 50, 50, 21))
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(100)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label.sizePolicy().hasHeightForWidth())
        self.label.setSizePolicy(sizePolicy)
        self.label.setObjectName(_fromUtf8("label"))
        self.mosaicDisplayMax = QtGui.QDoubleSpinBox(self.groupBox)
        self.mosaicDisplayMax.setGeometry(QtCore.QRect(70, 50, 65, 25))
        self.mosaicDisplayMax.setMaximum(65536.0)
        self.mosaicDisplayMax.setSingleStep(0.25)
        self.mosaicDisplayMax.setProperty("value", 2.0)
        self.mosaicDisplayMax.setObjectName(_fromUtf8("mosaicDisplayMax"))
        self.mosaicFlipLRBtn = QtGui.QPushButton(self.groupBox)
        self.mosaicFlipLRBtn.setGeometry(QtCore.QRect(0, 110, 71, 32))
        self.mosaicFlipLRBtn.setObjectName(_fromUtf8("mosaicFlipLRBtn"))
        self.groupBox_2 = QtGui.QGroupBox(Form)
        self.groupBox_2.setGeometry(QtCore.QRect(460, 0, 147, 151))
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
        self.tileShadingBtn = QtGui.QPushButton(self.groupBox_2)
        self.tileShadingBtn.setObjectName(_fromUtf8("tileShadingBtn"))
        self.verticalLayout.addWidget(self.tileShadingBtn)
        spacerItem = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.verticalLayout.addItem(spacerItem)
        self.frame_3 = QtGui.QFrame(Form)
        self.frame_3.setGeometry(QtCore.QRect(10, 10, 441, 137))
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(100)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.frame_3.sizePolicy().hasHeightForWidth())
        self.frame_3.setSizePolicy(sizePolicy)
        self.frame_3.setObjectName(_fromUtf8("frame_3"))
        self.atlasCombo = QtGui.QComboBox(self.frame_3)
        self.atlasCombo.setGeometry(QtCore.QRect(0, 10, 138, 26))
        self.atlasCombo.setObjectName(_fromUtf8("atlasCombo"))
        self.atlasCombo.addItem(_fromUtf8(""))

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox.setTitle(QtGui.QApplication.translate("Form", "Tile Operations", None, QtGui.QApplication.UnicodeUTF8))
        self.mosaicFlipUDBtn.setText(QtGui.QApplication.translate("Form", "FlipUD", None, QtGui.QApplication.UnicodeUTF8))
        self.mosaicApplyScaleBtn.setText(QtGui.QApplication.translate("Form", "Apply Tile Scale", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("Form", "Min", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Form", "Max", None, QtGui.QApplication.UnicodeUTF8))
        self.mosaicFlipLRBtn.setText(QtGui.QApplication.translate("Form", "FlipLR", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox_2.setTitle(QtGui.QApplication.translate("Form", "Image Correction", None, QtGui.QApplication.UnicodeUTF8))
        self.normalizeBtn.setText(QtGui.QApplication.translate("Form", "Normalize", None, QtGui.QApplication.UnicodeUTF8))
        self.blendBtn.setText(QtGui.QApplication.translate("Form", "Blend", None, QtGui.QApplication.UnicodeUTF8))
        self.autoRangeBtn.setText(QtGui.QApplication.translate("Form", "Auto Range", None, QtGui.QApplication.UnicodeUTF8))
        self.tileShadingBtn.setText(QtGui.QApplication.translate("Form", "Tile Shading", None, QtGui.QApplication.UnicodeUTF8))
        self.atlasCombo.setItemText(0, QtGui.QApplication.translate("Form", "Select Atlas...", None, QtGui.QApplication.UnicodeUTF8))

