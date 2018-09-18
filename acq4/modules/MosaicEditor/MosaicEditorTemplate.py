# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/analysis/modules/MosaicEditor/MosaicEditorTemplate.ui'
#
# Created by: PyQt4 UI code generator 4.11.4
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
        Form.resize(427, 123)
        self.horizontalLayout = QtGui.QHBoxLayout(Form)
        self.horizontalLayout.setMargin(0)
        self.horizontalLayout.setSpacing(3)
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.frame_3 = QtGui.QFrame(Form)
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
        self.horizontalLayout.addWidget(self.frame_3)
        self.groupBox_2 = QtGui.QGroupBox(Form)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(10)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.groupBox_2.sizePolicy().hasHeightForWidth())
        self.groupBox_2.setSizePolicy(sizePolicy)
        self.groupBox_2.setObjectName(_fromUtf8("groupBox_2"))
        self.verticalLayout = QtGui.QVBoxLayout(self.groupBox_2)
        self.verticalLayout.setMargin(0)
        self.verticalLayout.setSpacing(0)
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
        self.horizontalLayout.addWidget(self.groupBox_2)
        self.groupBox = QtGui.QGroupBox(Form)
        self.groupBox.setObjectName(_fromUtf8("groupBox"))
        self.gridLayout = QtGui.QGridLayout(self.groupBox)
        self.gridLayout.setMargin(0)
        self.gridLayout.setSpacing(1)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.label_2 = QtGui.QLabel(self.groupBox)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout.addWidget(self.label_2, 0, 0, 1, 1)
        self.mosaicDisplayMin = QtGui.QDoubleSpinBox(self.groupBox)
        self.mosaicDisplayMin.setMinimum(-1.0)
        self.mosaicDisplayMin.setMaximum(65000.0)
        self.mosaicDisplayMin.setSingleStep(0.25)
        self.mosaicDisplayMin.setObjectName(_fromUtf8("mosaicDisplayMin"))
        self.gridLayout.addWidget(self.mosaicDisplayMin, 0, 1, 1, 1)
        self.label = QtGui.QLabel(self.groupBox)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(100)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label.sizePolicy().hasHeightForWidth())
        self.label.setSizePolicy(sizePolicy)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 1, 0, 1, 1)
        self.mosaicDisplayMax = QtGui.QDoubleSpinBox(self.groupBox)
        self.mosaicDisplayMax.setMaximum(65536.0)
        self.mosaicDisplayMax.setSingleStep(0.25)
        self.mosaicDisplayMax.setProperty("value", 2.0)
        self.mosaicDisplayMax.setObjectName(_fromUtf8("mosaicDisplayMax"))
        self.gridLayout.addWidget(self.mosaicDisplayMax, 1, 1, 1, 1)
        self.mosaicApplyScaleBtn = QtGui.QPushButton(self.groupBox)
        self.mosaicApplyScaleBtn.setObjectName(_fromUtf8("mosaicApplyScaleBtn"))
        self.gridLayout.addWidget(self.mosaicApplyScaleBtn, 2, 0, 1, 2)
        self.mosaicFlipUDBtn = QtGui.QPushButton(self.groupBox)
        self.mosaicFlipUDBtn.setObjectName(_fromUtf8("mosaicFlipUDBtn"))
        self.gridLayout.addWidget(self.mosaicFlipUDBtn, 3, 1, 1, 1)
        self.mosaicFlipLRBtn = QtGui.QPushButton(self.groupBox)
        self.mosaicFlipLRBtn.setObjectName(_fromUtf8("mosaicFlipLRBtn"))
        self.gridLayout.addWidget(self.mosaicFlipLRBtn, 3, 0, 1, 1)
        spacerItem1 = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem1, 4, 0, 1, 2)
        self.horizontalLayout.addWidget(self.groupBox)
        self.horizontalLayout.setStretch(0, 5)
        self.horizontalLayout.setStretch(1, 1)
        self.horizontalLayout.setStretch(2, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.atlasCombo.setItemText(0, _translate("Form", "Select Atlas...", None))
        self.groupBox_2.setTitle(_translate("Form", "Image Correction", None))
        self.normalizeBtn.setText(_translate("Form", "Normalize", None))
        self.blendBtn.setText(_translate("Form", "Blend", None))
        self.autoRangeBtn.setText(_translate("Form", "Auto Range", None))
        self.tileShadingBtn.setText(_translate("Form", "Tile Shading", None))
        self.groupBox.setTitle(_translate("Form", "Tile Operations", None))
        self.label_2.setText(_translate("Form", "Min", None))
        self.label.setText(_translate("Form", "Max", None))
        self.mosaicApplyScaleBtn.setText(_translate("Form", "Apply Tile Scale", None))
        self.mosaicFlipUDBtn.setText(_translate("Form", "FlipUD", None))
        self.mosaicFlipLRBtn.setText(_translate("Form", "FlipLR", None))

