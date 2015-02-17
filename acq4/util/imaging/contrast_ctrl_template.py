# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/util/imaging/contrast_ctrl_template.ui'
#
# Created: Fri Jan 23 18:20:00 2015
#      by: PyQt4 UI code generator 4.10.4
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
        Form.resize(176, 384)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setMargin(0)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.histogram = HistogramLUTWidget(Form)
        self.histogram.setObjectName(_fromUtf8("histogram"))
        self.gridLayout.addWidget(self.histogram, 0, 0, 1, 2)
        self.btnAutoGain = QtGui.QPushButton(Form)
        self.btnAutoGain.setCheckable(True)
        self.btnAutoGain.setChecked(False)
        self.btnAutoGain.setObjectName(_fromUtf8("btnAutoGain"))
        self.gridLayout.addWidget(self.btnAutoGain, 1, 0, 1, 2)
        self.label_6 = QtGui.QLabel(Form)
        self.label_6.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.label_6.setObjectName(_fromUtf8("label_6"))
        self.gridLayout.addWidget(self.label_6, 2, 0, 1, 1)
        self.spinAutoGainSpeed = QtGui.QDoubleSpinBox(Form)
        self.spinAutoGainSpeed.setProperty("value", 2.0)
        self.spinAutoGainSpeed.setObjectName(_fromUtf8("spinAutoGainSpeed"))
        self.gridLayout.addWidget(self.spinAutoGainSpeed, 2, 1, 1, 1)
        self.label_8 = QtGui.QLabel(Form)
        self.label_8.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.label_8.setObjectName(_fromUtf8("label_8"))
        self.gridLayout.addWidget(self.label_8, 3, 0, 1, 1)
        self.spinAutoGainCenterWeight = QtGui.QDoubleSpinBox(Form)
        self.spinAutoGainCenterWeight.setMaximum(1.0)
        self.spinAutoGainCenterWeight.setSingleStep(0.1)
        self.spinAutoGainCenterWeight.setObjectName(_fromUtf8("spinAutoGainCenterWeight"))
        self.gridLayout.addWidget(self.spinAutoGainCenterWeight, 3, 1, 1, 1)
        self.zoomLiveBtn = QtGui.QPushButton(Form)
        self.zoomLiveBtn.setObjectName(_fromUtf8("zoomLiveBtn"))
        self.gridLayout.addWidget(self.zoomLiveBtn, 6, 0, 1, 2)
        self.label_4 = QtGui.QLabel(Form)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_4.sizePolicy().hasHeightForWidth())
        self.label_4.setSizePolicy(sizePolicy)
        self.label_4.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.label_4.setObjectName(_fromUtf8("label_4"))
        self.gridLayout.addWidget(self.label_4, 4, 0, 1, 1)
        self.alphaSlider = QtGui.QSlider(Form)
        self.alphaSlider.setMaximum(100)
        self.alphaSlider.setSingleStep(1)
        self.alphaSlider.setProperty("value", 100)
        self.alphaSlider.setOrientation(QtCore.Qt.Horizontal)
        self.alphaSlider.setObjectName(_fromUtf8("alphaSlider"))
        self.gridLayout.addWidget(self.alphaSlider, 4, 1, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.btnAutoGain.setToolTip(_translate("Form", "Determines the behavior of the white/black level sliders.\n"
"When enabled, the sliders maximum and minimum values are set\n"
"to the maximum and minimum intensity values in the image.\n"
"When disabled, the minimum is 0 and the maximum is the largest \n"
"possible intensity given the bit depth of the camera.", None))
        self.btnAutoGain.setText(_translate("Form", "Auto Gain", None))
        self.label_6.setText(_translate("Form", "Auto Gain Delay", None))
        self.spinAutoGainSpeed.setToolTip(_translate("Form", "Smooths out the auto gain control, prevents very\n"
"brief flashes from affecting the gain. Larger values\n"
"indicate more smoothing.\n"
"", None))
        self.label_8.setText(_translate("Form", "Frame Center Weight", None))
        self.spinAutoGainCenterWeight.setToolTip(_translate("Form", "Weights the auto gain measurement to the center 1/3 of\n"
"the frame when set to 1.0. A value of 0.0 meters from \n"
"the entire frame.", None))
        self.zoomLiveBtn.setText(_translate("Form", "Zoom to Image", None))
        self.label_4.setText(_translate("Form", "Transparency", None))

from acq4.pyqtgraph import HistogramLUTWidget
