# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'QtCam.ui'
#
# Created: Fri Mar 13 15:02:50 2009
#      by: PyQt4 UI code generator 4.3.3
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(QtCore.QSize(QtCore.QRect(0,0,799,600).size()).expandedTo(MainWindow.minimumSizeHint()))

        self.centralwidget = QtGui.QWidget(MainWindow)
        self.centralwidget.setGeometry(QtCore.QRect(0,87,654,426))
        self.centralwidget.setObjectName("centralwidget")

        self.gridlayout = QtGui.QGridLayout(self.centralwidget)
        self.gridlayout.setMargin(0)
        self.gridlayout.setSpacing(0)
        self.gridlayout.setObjectName("gridlayout")

        self.graphicsWidget = QtGui.QWidget(self.centralwidget)
        self.graphicsWidget.setObjectName("graphicsWidget")
        self.gridlayout.addWidget(self.graphicsWidget,0,0,1,1)
        MainWindow.setCentralWidget(self.centralwidget)

        self.menubar = QtGui.QMenuBar(MainWindow)
        self.menubar.setGeometry(QtCore.QRect(0,0,799,21))
        self.menubar.setObjectName("menubar")
        MainWindow.setMenuBar(self.menubar)

        self.statusbar = QtGui.QStatusBar(MainWindow)
        self.statusbar.setGeometry(QtCore.QRect(0,581,799,19))
        self.statusbar.setObjectName("statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.dockWidget = QtGui.QDockWidget(MainWindow)
        self.dockWidget.setGeometry(QtCore.QRect(0,21,799,62))

        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred,QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.dockWidget.sizePolicy().hasHeightForWidth())
        self.dockWidget.setSizePolicy(sizePolicy)
        self.dockWidget.setFeatures(QtGui.QDockWidget.DockWidgetFloatable|QtGui.QDockWidget.DockWidgetMovable|QtGui.QDockWidget.DockWidgetVerticalTitleBar)
        self.dockWidget.setObjectName("dockWidget")

        self.dockWidgetContents = QtGui.QWidget(self.dockWidget)
        self.dockWidgetContents.setGeometry(QtCore.QRect(22,0,777,62))
        self.dockWidgetContents.setObjectName("dockWidgetContents")

        self.vboxlayout = QtGui.QVBoxLayout(self.dockWidgetContents)
        self.vboxlayout.setSpacing(2)
        self.vboxlayout.setMargin(0)
        self.vboxlayout.setObjectName("vboxlayout")

        self.hboxlayout = QtGui.QHBoxLayout()
        self.hboxlayout.setSpacing(6)
        self.hboxlayout.setObjectName("hboxlayout")

        self.btnAcquire = QtGui.QPushButton(self.dockWidgetContents)
        self.btnAcquire.setCheckable(True)
        self.btnAcquire.setObjectName("btnAcquire")
        self.hboxlayout.addWidget(self.btnAcquire)

        self.btnRecord = QtGui.QPushButton(self.dockWidgetContents)
        self.btnRecord.setEnabled(False)
        self.btnRecord.setCheckable(True)
        self.btnRecord.setFlat(False)
        self.btnRecord.setObjectName("btnRecord")
        self.hboxlayout.addWidget(self.btnRecord)

        self.btnSnap = QtGui.QToolButton(self.dockWidgetContents)
        self.btnSnap.setEnabled(False)
        self.btnSnap.setObjectName("btnSnap")
        self.hboxlayout.addWidget(self.btnSnap)

        self.label = QtGui.QLabel(self.dockWidgetContents)
        self.label.setObjectName("label")
        self.hboxlayout.addWidget(self.label)

        self.txtStorageDir = QtGui.QLineEdit(self.dockWidgetContents)

        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding,QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(5)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.txtStorageDir.sizePolicy().hasHeightForWidth())
        self.txtStorageDir.setSizePolicy(sizePolicy)
        self.txtStorageDir.setObjectName("txtStorageDir")
        self.hboxlayout.addWidget(self.txtStorageDir)

        self.btnSelectDir = QtGui.QToolButton(self.dockWidgetContents)
        self.btnSelectDir.setObjectName("btnSelectDir")
        self.hboxlayout.addWidget(self.btnSelectDir)
        self.vboxlayout.addLayout(self.hboxlayout)

        self.hboxlayout1 = QtGui.QHBoxLayout()
        self.hboxlayout1.setSpacing(6)
        self.hboxlayout1.setObjectName("hboxlayout1")

        self.label_2 = QtGui.QLabel(self.dockWidgetContents)
        self.label_2.setObjectName("label_2")
        self.hboxlayout1.addWidget(self.label_2)

        self.spinBinning = QtGui.QSpinBox(self.dockWidgetContents)
        self.spinBinning.setMinimum(1)
        self.spinBinning.setMaximum(1000)
        self.spinBinning.setObjectName("spinBinning")
        self.hboxlayout1.addWidget(self.spinBinning)

        self.label_3 = QtGui.QLabel(self.dockWidgetContents)
        self.label_3.setObjectName("label_3")
        self.hboxlayout1.addWidget(self.label_3)

        self.spinExposure = QtGui.QDoubleSpinBox(self.dockWidgetContents)
        self.spinExposure.setDecimals(3)
        self.spinExposure.setMinimum(0.0)
        self.spinExposure.setMaximum(1000.0)
        self.spinExposure.setSingleStep(0.01)
        self.spinExposure.setObjectName("spinExposure")
        self.hboxlayout1.addWidget(self.spinExposure)

        self.frame = QtGui.QFrame(self.dockWidgetContents)
        self.frame.setFrameShape(QtGui.QFrame.StyledPanel)
        self.frame.setFrameShadow(QtGui.QFrame.Sunken)
        self.frame.setObjectName("frame")

        self.hboxlayout2 = QtGui.QHBoxLayout(self.frame)
        self.hboxlayout2.setSpacing(2)
        self.hboxlayout2.setMargin(0)
        self.hboxlayout2.setObjectName("hboxlayout2")

        self.btnFullFrame = QtGui.QPushButton(self.frame)
        self.btnFullFrame.setObjectName("btnFullFrame")
        self.hboxlayout2.addWidget(self.btnFullFrame)
        self.hboxlayout1.addWidget(self.frame)

        self.comboTransferMode = QtGui.QComboBox(self.dockWidgetContents)
        self.comboTransferMode.setObjectName("comboTransferMode")
        self.hboxlayout1.addWidget(self.comboTransferMode)

        self.comboShutterMode = QtGui.QComboBox(self.dockWidgetContents)
        self.comboShutterMode.setObjectName("comboShutterMode")
        self.hboxlayout1.addWidget(self.comboShutterMode)

        spacerItem = QtGui.QSpacerItem(40,20,QtGui.QSizePolicy.Expanding,QtGui.QSizePolicy.Minimum)
        self.hboxlayout1.addItem(spacerItem)
        self.vboxlayout.addLayout(self.hboxlayout1)
        self.dockWidget.setWidget(self.dockWidgetContents)
        MainWindow.addDockWidget(QtCore.Qt.DockWidgetArea(4),self.dockWidget)

        self.dockWidget_2 = QtGui.QDockWidget(MainWindow)
        self.dockWidget_2.setGeometry(QtCore.QRect(658,87,141,310))

        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Maximum,QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.dockWidget_2.sizePolicy().hasHeightForWidth())
        self.dockWidget_2.setSizePolicy(sizePolicy)
        self.dockWidget_2.setObjectName("dockWidget_2")

        self.dockWidgetContents_2 = QtGui.QWidget(self.dockWidget_2)
        self.dockWidgetContents_2.setGeometry(QtCore.QRect(0,22,141,288))
        self.dockWidgetContents_2.setObjectName("dockWidgetContents_2")

        self.vboxlayout1 = QtGui.QVBoxLayout(self.dockWidgetContents_2)
        self.vboxlayout1.setSpacing(0)
        self.vboxlayout1.setMargin(0)
        self.vboxlayout1.setObjectName("vboxlayout1")

        self.hboxlayout3 = QtGui.QHBoxLayout()
        self.hboxlayout3.setObjectName("hboxlayout3")

        self.sliderAvgLevel = QtGui.QSlider(self.dockWidgetContents_2)
        self.sliderAvgLevel.setEnabled(False)
        self.sliderAvgLevel.setMaximum(4096)
        self.sliderAvgLevel.setOrientation(QtCore.Qt.Vertical)
        self.sliderAvgLevel.setInvertedAppearance(False)
        self.sliderAvgLevel.setObjectName("sliderAvgLevel")
        self.hboxlayout3.addWidget(self.sliderAvgLevel)

        self.verticalSlider = QtGui.QSlider(self.dockWidgetContents_2)
        self.verticalSlider.setOrientation(QtCore.Qt.Vertical)
        self.verticalSlider.setObjectName("verticalSlider")
        self.hboxlayout3.addWidget(self.verticalSlider)

        self.sliderWhiteLevel = QtGui.QSlider(self.dockWidgetContents_2)
        self.sliderWhiteLevel.setMaximum(10000)
        self.sliderWhiteLevel.setSingleStep(10)
        self.sliderWhiteLevel.setPageStep(200)
        self.sliderWhiteLevel.setProperty("value",QtCore.QVariant(10000))
        self.sliderWhiteLevel.setSliderPosition(10000)
        self.sliderWhiteLevel.setOrientation(QtCore.Qt.Vertical)
        self.sliderWhiteLevel.setObjectName("sliderWhiteLevel")
        self.hboxlayout3.addWidget(self.sliderWhiteLevel)

        self.sliderBlackLevel = QtGui.QSlider(self.dockWidgetContents_2)
        self.sliderBlackLevel.setMaximum(10000)
        self.sliderBlackLevel.setSingleStep(10)
        self.sliderBlackLevel.setPageStep(200)
        self.sliderBlackLevel.setOrientation(QtCore.Qt.Vertical)
        self.sliderBlackLevel.setInvertedAppearance(False)
        self.sliderBlackLevel.setInvertedControls(False)
        self.sliderBlackLevel.setTickPosition(QtGui.QSlider.TicksBelow)
        self.sliderBlackLevel.setTickInterval(1000)
        self.sliderBlackLevel.setObjectName("sliderBlackLevel")
        self.hboxlayout3.addWidget(self.sliderBlackLevel)

        self.vboxlayout2 = QtGui.QVBoxLayout()
        self.vboxlayout2.setObjectName("vboxlayout2")

        self.labelLevelMax = QtGui.QLabel(self.dockWidgetContents_2)
        self.labelLevelMax.setObjectName("labelLevelMax")
        self.vboxlayout2.addWidget(self.labelLevelMax)

        spacerItem1 = QtGui.QSpacerItem(20,40,QtGui.QSizePolicy.Minimum,QtGui.QSizePolicy.Expanding)
        self.vboxlayout2.addItem(spacerItem1)

        self.labelLevelMid = QtGui.QLabel(self.dockWidgetContents_2)
        self.labelLevelMid.setObjectName("labelLevelMid")
        self.vboxlayout2.addWidget(self.labelLevelMid)

        spacerItem2 = QtGui.QSpacerItem(20,40,QtGui.QSizePolicy.Minimum,QtGui.QSizePolicy.Expanding)
        self.vboxlayout2.addItem(spacerItem2)

        self.labelLevelMin = QtGui.QLabel(self.dockWidgetContents_2)
        self.labelLevelMin.setObjectName("labelLevelMin")
        self.vboxlayout2.addWidget(self.labelLevelMin)
        self.hboxlayout3.addLayout(self.vboxlayout2)
        self.vboxlayout1.addLayout(self.hboxlayout3)

        self.btnAutoGain = QtGui.QPushButton(self.dockWidgetContents_2)
        self.btnAutoGain.setCheckable(True)
        self.btnAutoGain.setChecked(False)
        self.btnAutoGain.setObjectName("btnAutoGain")
        self.vboxlayout1.addWidget(self.btnAutoGain)

        self.gridlayout1 = QtGui.QGridLayout()
        self.gridlayout1.setHorizontalSpacing(6)
        self.gridlayout1.setVerticalSpacing(0)
        self.gridlayout1.setObjectName("gridlayout1")

        self.label_6 = QtGui.QLabel(self.dockWidgetContents_2)
        self.label_6.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.label_6.setObjectName("label_6")
        self.gridlayout1.addWidget(self.label_6,0,0,1,1)

        self.spinAutoGainSpeed = QtGui.QDoubleSpinBox(self.dockWidgetContents_2)
        self.spinAutoGainSpeed.setProperty("value",QtCore.QVariant(2.0))
        self.spinAutoGainSpeed.setObjectName("spinAutoGainSpeed")
        self.gridlayout1.addWidget(self.spinAutoGainSpeed,0,1,1,1)

        self.label_8 = QtGui.QLabel(self.dockWidgetContents_2)
        self.label_8.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.label_8.setObjectName("label_8")
        self.gridlayout1.addWidget(self.label_8,1,0,1,1)

        self.spinAutoGainCenterWeight = QtGui.QDoubleSpinBox(self.dockWidgetContents_2)
        self.spinAutoGainCenterWeight.setMaximum(1.0)
        self.spinAutoGainCenterWeight.setSingleStep(0.1)
        self.spinAutoGainCenterWeight.setObjectName("spinAutoGainCenterWeight")
        self.gridlayout1.addWidget(self.spinAutoGainCenterWeight,1,1,1,1)
        self.vboxlayout1.addLayout(self.gridlayout1)
        self.dockWidget_2.setWidget(self.dockWidgetContents_2)
        MainWindow.addDockWidget(QtCore.Qt.DockWidgetArea(2),self.dockWidget_2)

        self.dockWidget_3 = QtGui.QDockWidget(MainWindow)
        self.dockWidget_3.setGeometry(QtCore.QRect(658,401,141,112))
        self.dockWidget_3.setObjectName("dockWidget_3")

        self.dockWidgetContents_3 = QtGui.QWidget(self.dockWidget_3)
        self.dockWidgetContents_3.setGeometry(QtCore.QRect(0,22,141,90))
        self.dockWidgetContents_3.setObjectName("dockWidgetContents_3")

        self.vboxlayout3 = QtGui.QVBoxLayout(self.dockWidgetContents_3)
        self.vboxlayout3.setSpacing(2)
        self.vboxlayout3.setMargin(0)
        self.vboxlayout3.setObjectName("vboxlayout3")

        self.frame_2 = QtGui.QFrame(self.dockWidgetContents_3)
        self.frame_2.setFrameShape(QtGui.QFrame.StyledPanel)
        self.frame_2.setFrameShadow(QtGui.QFrame.Raised)
        self.frame_2.setObjectName("frame_2")

        self.hboxlayout4 = QtGui.QHBoxLayout(self.frame_2)
        self.hboxlayout4.setSpacing(0)
        self.hboxlayout4.setMargin(0)
        self.hboxlayout4.setObjectName("hboxlayout4")

        self.label_4 = QtGui.QLabel(self.frame_2)
        self.label_4.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.label_4.setObjectName("label_4")
        self.hboxlayout4.addWidget(self.label_4)

        self.spinFilterTime = QtGui.QDoubleSpinBox(self.frame_2)
        self.spinFilterTime.setSingleStep(1.0)
        self.spinFilterTime.setProperty("value",QtCore.QVariant(5.0))
        self.spinFilterTime.setObjectName("spinFilterTime")
        self.hboxlayout4.addWidget(self.spinFilterTime)
        self.vboxlayout3.addWidget(self.frame_2)

        self.frame_3 = QtGui.QFrame(self.dockWidgetContents_3)
        self.frame_3.setFrameShape(QtGui.QFrame.StyledPanel)
        self.frame_3.setFrameShadow(QtGui.QFrame.Raised)
        self.frame_3.setObjectName("frame_3")

        self.hboxlayout5 = QtGui.QHBoxLayout(self.frame_3)
        self.hboxlayout5.setSpacing(2)
        self.hboxlayout5.setMargin(0)
        self.hboxlayout5.setObjectName("hboxlayout5")

        self.label_5 = QtGui.QLabel(self.frame_3)
        self.label_5.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.label_5.setObjectName("label_5")
        self.hboxlayout5.addWidget(self.label_5)

        self.spinFlattenSize = QtGui.QDoubleSpinBox(self.frame_3)
        self.spinFlattenSize.setProperty("value",QtCore.QVariant(4.0))
        self.spinFlattenSize.setObjectName("spinFlattenSize")
        self.hboxlayout5.addWidget(self.spinFlattenSize)
        self.vboxlayout3.addWidget(self.frame_3)

        self.btnDivideBackground = QtGui.QToolButton(self.dockWidgetContents_3)
        self.btnDivideBackground.setCheckable(True)
        self.btnDivideBackground.setObjectName("btnDivideBackground")
        self.vboxlayout3.addWidget(self.btnDivideBackground)

        self.btnLockBackground = QtGui.QToolButton(self.dockWidgetContents_3)
        self.btnLockBackground.setCheckable(True)
        self.btnLockBackground.setObjectName("btnLockBackground")
        self.vboxlayout3.addWidget(self.btnLockBackground)
        self.dockWidget_3.setWidget(self.dockWidgetContents_3)
        MainWindow.addDockWidget(QtCore.Qt.DockWidgetArea(2),self.dockWidget_3)

        self.dockWidget_4 = QtGui.QDockWidget(MainWindow)
        self.dockWidget_4.setGeometry(QtCore.QRect(0,517,799,64))
        self.dockWidget_4.setFeatures(QtGui.QDockWidget.DockWidgetFloatable|QtGui.QDockWidget.DockWidgetMovable|QtGui.QDockWidget.DockWidgetVerticalTitleBar)
        self.dockWidget_4.setObjectName("dockWidget_4")

        self.dockWidgetContents_4 = QtGui.QWidget(self.dockWidget_4)
        self.dockWidgetContents_4.setGeometry(QtCore.QRect(22,0,777,64))
        self.dockWidgetContents_4.setObjectName("dockWidgetContents_4")

        self.gridlayout2 = QtGui.QGridLayout(self.dockWidgetContents_4)
        self.gridlayout2.setMargin(0)
        self.gridlayout2.setSpacing(0)
        self.gridlayout2.setObjectName("gridlayout2")

        self.checkEnableROIs = QtGui.QCheckBox(self.dockWidgetContents_4)
        self.checkEnableROIs.setObjectName("checkEnableROIs")
        self.gridlayout2.addWidget(self.checkEnableROIs,0,0,1,2)

        self.plotWidget = QtGui.QWidget(self.dockWidgetContents_4)

        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding,QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.plotWidget.sizePolicy().hasHeightForWidth())
        self.plotWidget.setSizePolicy(sizePolicy)
        self.plotWidget.setObjectName("plotWidget")
        self.gridlayout2.addWidget(self.plotWidget,0,2,3,1)

        self.listROIs = QtGui.QListWidget(self.dockWidgetContents_4)

        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred,QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.listROIs.sizePolicy().hasHeightForWidth())
        self.listROIs.setSizePolicy(sizePolicy)
        self.listROIs.setMaximumSize(QtCore.QSize(100,16777215))
        self.listROIs.setObjectName("listROIs")
        self.gridlayout2.addWidget(self.listROIs,0,3,3,1)

        self.btnAddROI = QtGui.QPushButton(self.dockWidgetContents_4)
        self.btnAddROI.setObjectName("btnAddROI")
        self.gridlayout2.addWidget(self.btnAddROI,1,0,1,2)

        self.label_7 = QtGui.QLabel(self.dockWidgetContents_4)
        self.label_7.setObjectName("label_7")
        self.gridlayout2.addWidget(self.label_7,2,0,1,1)

        self.spinROITime = QtGui.QDoubleSpinBox(self.dockWidgetContents_4)
        self.spinROITime.setSingleStep(0.1)
        self.spinROITime.setProperty("value",QtCore.QVariant(5.0))
        self.spinROITime.setObjectName("spinROITime")
        self.gridlayout2.addWidget(self.spinROITime,2,1,1,1)
        self.dockWidget_4.setWidget(self.dockWidgetContents_4)
        MainWindow.addDockWidget(QtCore.Qt.DockWidgetArea(8),self.dockWidget_4)

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QtGui.QApplication.translate("MainWindow", "QtCam", None, QtGui.QApplication.UnicodeUTF8))
        self.dockWidget.setWindowTitle(QtGui.QApplication.translate("MainWindow", "Camera", None, QtGui.QApplication.UnicodeUTF8))
        self.btnAcquire.setText(QtGui.QApplication.translate("MainWindow", "Acquire", None, QtGui.QApplication.UnicodeUTF8))
        self.btnRecord.setText(QtGui.QApplication.translate("MainWindow", "Record", None, QtGui.QApplication.UnicodeUTF8))
        self.btnSnap.setText(QtGui.QApplication.translate("MainWindow", "Snap", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("MainWindow", "Storage Dir", None, QtGui.QApplication.UnicodeUTF8))
        self.btnSelectDir.setText(QtGui.QApplication.translate("MainWindow", "...", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("MainWindow", "Binning", None, QtGui.QApplication.UnicodeUTF8))
        self.label_3.setText(QtGui.QApplication.translate("MainWindow", "Exposure", None, QtGui.QApplication.UnicodeUTF8))
        self.btnFullFrame.setText(QtGui.QApplication.translate("MainWindow", "Full Frame", None, QtGui.QApplication.UnicodeUTF8))
        self.dockWidget_2.setWindowTitle(QtGui.QApplication.translate("MainWindow", "Display Gain", None, QtGui.QApplication.UnicodeUTF8))
        self.labelLevelMax.setText(QtGui.QApplication.translate("MainWindow", "4096", None, QtGui.QApplication.UnicodeUTF8))
        self.labelLevelMin.setText(QtGui.QApplication.translate("MainWindow", "0", None, QtGui.QApplication.UnicodeUTF8))
        self.btnAutoGain.setText(QtGui.QApplication.translate("MainWindow", "Auto Gain", None, QtGui.QApplication.UnicodeUTF8))
        self.label_6.setText(QtGui.QApplication.translate("MainWindow", "Slow", None, QtGui.QApplication.UnicodeUTF8))
        self.label_8.setText(QtGui.QApplication.translate("MainWindow", "Center Weight", None, QtGui.QApplication.UnicodeUTF8))
        self.dockWidget_3.setWindowTitle(QtGui.QApplication.translate("MainWindow", "Background Subtraction", None, QtGui.QApplication.UnicodeUTF8))
        self.label_4.setText(QtGui.QApplication.translate("MainWindow", "Time const.", None, QtGui.QApplication.UnicodeUTF8))
        self.label_5.setText(QtGui.QApplication.translate("MainWindow", "Blur Bg.", None, QtGui.QApplication.UnicodeUTF8))
        self.btnDivideBackground.setText(QtGui.QApplication.translate("MainWindow", "Divide Background", None, QtGui.QApplication.UnicodeUTF8))
        self.btnLockBackground.setText(QtGui.QApplication.translate("MainWindow", "Lock Background", None, QtGui.QApplication.UnicodeUTF8))
        self.dockWidget_4.setWindowTitle(QtGui.QApplication.translate("MainWindow", "Plots", None, QtGui.QApplication.UnicodeUTF8))
        self.checkEnableROIs.setText(QtGui.QApplication.translate("MainWindow", "Enable ROIs", None, QtGui.QApplication.UnicodeUTF8))
        self.btnAddROI.setText(QtGui.QApplication.translate("MainWindow", "Add ROI", None, QtGui.QApplication.UnicodeUTF8))
        self.label_7.setText(QtGui.QApplication.translate("MainWindow", "Time:", None, QtGui.QApplication.UnicodeUTF8))

