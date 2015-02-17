# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'acq4/util/imaging/bg_subtract_template.ui'
#
# Created: Fri Jan 23 18:19:42 2015
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
        Form.resize(162, 90)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setMargin(0)
        self.gridLayout.setVerticalSpacing(0)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.bgBlurSpin = QtGui.QDoubleSpinBox(Form)
        self.bgBlurSpin.setProperty("value", 0.0)
        self.bgBlurSpin.setObjectName(_fromUtf8("bgBlurSpin"))
        self.gridLayout.addWidget(self.bgBlurSpin, 2, 1, 1, 1)
        self.bgTimeSpin = QtGui.QDoubleSpinBox(Form)
        self.bgTimeSpin.setDecimals(1)
        self.bgTimeSpin.setSingleStep(1.0)
        self.bgTimeSpin.setProperty("value", 3.0)
        self.bgTimeSpin.setObjectName(_fromUtf8("bgTimeSpin"))
        self.gridLayout.addWidget(self.bgTimeSpin, 0, 1, 1, 1)
        self.label_5 = QtGui.QLabel(Form)
        self.label_5.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.label_5.setObjectName(_fromUtf8("label_5"))
        self.gridLayout.addWidget(self.label_5, 2, 0, 1, 1)
        self.collectBgBtn = QtGui.QPushButton(Form)
        self.collectBgBtn.setCheckable(True)
        self.collectBgBtn.setObjectName(_fromUtf8("collectBgBtn"))
        self.gridLayout.addWidget(self.collectBgBtn, 0, 0, 1, 1)
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setSpacing(0)
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.subtractBgBtn = QtGui.QPushButton(Form)
        self.subtractBgBtn.setCheckable(True)
        self.subtractBgBtn.setAutoExclusive(False)
        self.subtractBgBtn.setObjectName(_fromUtf8("subtractBgBtn"))
        self.horizontalLayout.addWidget(self.subtractBgBtn)
        self.divideBgBtn = QtGui.QPushButton(Form)
        self.divideBgBtn.setCheckable(True)
        self.divideBgBtn.setAutoExclusive(False)
        self.divideBgBtn.setObjectName(_fromUtf8("divideBgBtn"))
        self.horizontalLayout.addWidget(self.divideBgBtn)
        self.gridLayout.addLayout(self.horizontalLayout, 3, 0, 1, 2)
        self.horizontalLayout_2 = QtGui.QHBoxLayout()
        self.horizontalLayout_2.setObjectName(_fromUtf8("horizontalLayout_2"))
        spacerItem = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.horizontalLayout_2.addItem(spacerItem)
        self.contAvgBgCheck = QtGui.QCheckBox(Form)
        self.contAvgBgCheck.setObjectName(_fromUtf8("contAvgBgCheck"))
        self.horizontalLayout_2.addWidget(self.contAvgBgCheck)
        self.gridLayout.addLayout(self.horizontalLayout_2, 1, 0, 1, 2)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.bgBlurSpin.setToolTip(_translate("Form", "<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.0//EN\" \"http://www.w3.org/TR/REC-html40/strict.dtd\">\n"
"<html><head><meta name=\"qrichtext\" content=\"1\" /><style type=\"text/css\">\n"
"p, li { white-space: pre-wrap; }\n"
"</style></head><body style=\" font-family:\'MS Shell Dlg 2\'; font-size:8.25pt; font-weight:400; font-style:normal;\">\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-size:8pt;\">Blurs the background frame before dividing it from the current frame.</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-size:8pt;\">Large blur values may cause performance to degrade.</span></p></body></html>", None))
        self.bgTimeSpin.setToolTip(_translate("Form", "Sets the approximate number of frames to be averaged for\n"
"background division.", None))
        self.bgTimeSpin.setSuffix(_translate("Form", " s", None))
        self.label_5.setText(_translate("Form", "Blur Background", None))
        self.collectBgBtn.setText(_translate("Form", "Collect Background", None))
        self.subtractBgBtn.setText(_translate("Form", "Subtract", None))
        self.divideBgBtn.setToolTip(_translate("Form", "Enables background division. \n"
"Either a set of static background frames need to have already by collected\n"
"(by pressing \'Static\' above) or \'Continuous\' needs to be pressed.", None))
        self.divideBgBtn.setText(_translate("Form", "Divide", None))
        self.contAvgBgCheck.setText(_translate("Form", "Continuous Average", None))

