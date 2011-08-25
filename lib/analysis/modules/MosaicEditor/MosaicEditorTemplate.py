# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './lib/analysis/modules/MosaicEditor/MosaicEditorTemplate.ui'
#
# Created: Wed Aug 17 13:49:52 2011
#      by: pyside-uic 0.2.11 running on PySide 1.0.5
#
# WARNING! All changes made in this file will be lost!

from PySide import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(784, 137)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setObjectName("gridLayout")
        self.splitter_2 = QtGui.QSplitter(Form)
        self.splitter_2.setOrientation(QtCore.Qt.Horizontal)
        self.splitter_2.setObjectName("splitter_2")
        self.splitter = QtGui.QSplitter(self.splitter_2)
        self.splitter.setOrientation(QtCore.Qt.Vertical)
        self.splitter.setObjectName("splitter")
        self.layoutWidget = QtGui.QWidget(self.splitter)
        self.layoutWidget.setObjectName("layoutWidget")
        self.gridLayout_3 = QtGui.QGridLayout(self.layoutWidget)
        self.gridLayout_3.setContentsMargins(0, 0, 0, 0)
        self.gridLayout_3.setObjectName("gridLayout_3")
        self.groupBox_2 = QtGui.QGroupBox(self.layoutWidget)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(10)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.groupBox_2.sizePolicy().hasHeightForWidth())
        self.groupBox_2.setSizePolicy(sizePolicy)
        self.groupBox_2.setObjectName("groupBox_2")
        self.verticalLayout = QtGui.QVBoxLayout(self.groupBox_2)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout.setObjectName("verticalLayout")
        self.normalizeBtn = QtGui.QPushButton(self.groupBox_2)
        self.normalizeBtn.setObjectName("normalizeBtn")
        self.verticalLayout.addWidget(self.normalizeBtn)
        self.blendBtn = QtGui.QPushButton(self.groupBox_2)
        self.blendBtn.setObjectName("blendBtn")
        self.verticalLayout.addWidget(self.blendBtn)
        self.autoRangeBtn = QtGui.QPushButton(self.groupBox_2)
        self.autoRangeBtn.setObjectName("autoRangeBtn")
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
        self.frame_3.setObjectName("frame_3")
        self.gridLayout_2 = QtGui.QGridLayout(self.frame_3)
        self.gridLayout_2.setContentsMargins(0, 0, 0, 0)
        self.gridLayout_2.setSpacing(0)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.atlasCombo = QtGui.QComboBox(self.frame_3)
        self.atlasCombo.setObjectName("atlasCombo")
        self.atlasCombo.addItem("")
        self.gridLayout_2.addWidget(self.atlasCombo, 0, 0, 1, 1)
        self.atlasLayout = QtGui.QGridLayout()
        self.atlasLayout.setSpacing(0)
        self.atlasLayout.setObjectName("atlasLayout")
        self.gridLayout_2.addLayout(self.atlasLayout, 1, 0, 1, 1)
        self.gridLayout_3.addWidget(self.frame_3, 0, 0, 1, 1)
        self.gridLayout.addWidget(self.splitter_2, 0, 0, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.groupBox_2.setTitle(QtGui.QApplication.translate("Form", "Image Correction", None, QtGui.QApplication.UnicodeUTF8))
        self.normalizeBtn.setText(QtGui.QApplication.translate("Form", "Normalize", None, QtGui.QApplication.UnicodeUTF8))
        self.blendBtn.setText(QtGui.QApplication.translate("Form", "Blend", None, QtGui.QApplication.UnicodeUTF8))
        self.autoRangeBtn.setText(QtGui.QApplication.translate("Form", "Auto Range", None, QtGui.QApplication.UnicodeUTF8))
        self.atlasCombo.setItemText(0, QtGui.QApplication.translate("Form", "Select Atlas...", None, QtGui.QApplication.UnicodeUTF8))

