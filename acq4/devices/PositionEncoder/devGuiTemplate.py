# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '.\devGuiTemplate.ui'
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

class Ui_encoderDevGui(object):
    def setupUi(self, encoderDevGui):
        encoderDevGui.setObjectName(_fromUtf8("encoderDevGui"))
        encoderDevGui.resize(293, 172)
        self.gridLayout = QtGui.QGridLayout(encoderDevGui)
        self.gridLayout.setMargin(0)
        self.gridLayout.setSpacing(3)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.label = QtGui.QLabel(encoderDevGui)
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.label.setFont(font)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 0, 0, 1, 1)
        self.label_2 = QtGui.QLabel(encoderDevGui)
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.label_2.setFont(font)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout.addWidget(self.label_2, 1, 0, 1, 1)
        spacerItem = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem, 2, 0, 1, 1)
        self.label_4 = QtGui.QLabel(encoderDevGui)
        self.label_4.setObjectName(_fromUtf8("label_4"))
        self.gridLayout.addWidget(self.label_4, 1, 2, 1, 1)
        self.UnitLabel = QtGui.QLabel(encoderDevGui)
        self.UnitLabel.setText(_fromUtf8(""))
        self.UnitLabel.setObjectName(_fromUtf8("UnitLabel"))
        self.gridLayout.addWidget(self.UnitLabel, 1, 3, 1, 1)
        self.ResolutionLabel = QtGui.QLabel(encoderDevGui)
        font = QtGui.QFont()
        font.setStyleStrategy(QtGui.QFont.PreferDefault)
        self.ResolutionLabel.setFont(font)
        self.ResolutionLabel.setContextMenuPolicy(QtCore.Qt.DefaultContextMenu)
        self.ResolutionLabel.setLayoutDirection(QtCore.Qt.RightToLeft)
        self.ResolutionLabel.setText(_fromUtf8(""))
        self.ResolutionLabel.setObjectName(_fromUtf8("ResolutionLabel"))
        self.gridLayout.addWidget(self.ResolutionLabel, 1, 1, 1, 1)
        self.TypeLabel = QtGui.QLabel(encoderDevGui)
        self.TypeLabel.setText(_fromUtf8(""))
        self.TypeLabel.setObjectName(_fromUtf8("TypeLabel"))
        self.gridLayout.addWidget(self.TypeLabel, 0, 1, 1, 3)

        self.retranslateUi(encoderDevGui)
        QtCore.QMetaObject.connectSlotsByName(encoderDevGui)

    def retranslateUi(self, encoderDevGui):
        encoderDevGui.setWindowTitle(_translate("encoderDevGui", "Form", None))
        self.label.setText(_translate("encoderDevGui", "Encoder Type ", None))
        self.label_2.setText(_translate("encoderDevGui", "Encoder Resolution", None))
        self.label_4.setText(_translate("encoderDevGui", "pulses per", None))

