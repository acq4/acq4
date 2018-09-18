# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'CtrlTemplate.ui'
#
# Created: Wed Oct 19 11:31:41 2011
#      by: PyQt4 UI code generator 4.8.3
#
# WARNING! All changes made in this file will be lost!

from acq4.util import Qt

try:
    _fromUtf8 = Qt.QString.fromUtf8
except AttributeError:
    _fromUtf8 = lambda s: s

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName(_fromUtf8("Form"))
        Form.resize(228, 75)
        self.gridLayout = Qt.QGridLayout(Form)
        self.gridLayout.setMargin(0)
        self.gridLayout.setVerticalSpacing(0)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.label = Qt.QLabel(Form)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 0, 0, 1, 1)
        self.slicePlaneCombo = Qt.QComboBox(Form)
        self.slicePlaneCombo.setObjectName(_fromUtf8("slicePlaneCombo"))
        self.slicePlaneCombo.addItem(_fromUtf8(""))
        self.slicePlaneCombo.addItem(_fromUtf8(""))
        self.slicePlaneCombo.addItem(_fromUtf8(""))
        self.slicePlaneCombo.addItem(_fromUtf8(""))
        self.gridLayout.addWidget(self.slicePlaneCombo, 0, 1, 1, 1)
        self.label_2 = Qt.QLabel(Form)
        self.label_2.setObjectName(_fromUtf8("label_2"))
        self.gridLayout.addWidget(self.label_2, 1, 0, 1, 1)
        self.hemisphereCombo = Qt.QComboBox(Form)
        self.hemisphereCombo.setObjectName(_fromUtf8("hemisphereCombo"))
        self.hemisphereCombo.addItem(_fromUtf8(""))
        self.hemisphereCombo.addItem(_fromUtf8(""))
        self.gridLayout.addWidget(self.hemisphereCombo, 1, 1, 1, 1)
        self.label_3 = Qt.QLabel(Form)
        self.label_3.setObjectName(_fromUtf8("label_3"))
        self.gridLayout.addWidget(self.label_3, 3, 0, 1, 1)
        self.thicknessSpin = SpinBox(Form)
        self.thicknessSpin.setObjectName(_fromUtf8("thicknessSpin"))
        self.gridLayout.addWidget(self.thicknessSpin, 3, 1, 1, 1)
        self.photoCheck = Qt.QCheckBox(Form)
        self.photoCheck.setObjectName(_fromUtf8("photoCheck"))
        self.gridLayout.addWidget(self.photoCheck, 2, 0, 1, 1)
        self.drawingCheck = Qt.QCheckBox(Form)
        self.drawingCheck.setChecked(True)
        self.drawingCheck.setObjectName(_fromUtf8("drawingCheck"))
        self.gridLayout.addWidget(self.drawingCheck, 2, 1, 1, 1)

        self.retranslateUi(Form)
        Qt.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(Qt.QApplication.translate("Form", "Form", None, Qt.QApplication.UnicodeUTF8))
        self.label.setText(Qt.QApplication.translate("Form", "Slice Plane", None, Qt.QApplication.UnicodeUTF8))
        self.slicePlaneCombo.setItemText(0, Qt.QApplication.translate("Form", "Parasaggital", None, Qt.QApplication.UnicodeUTF8))
        self.slicePlaneCombo.setItemText(1, Qt.QApplication.translate("Form", "Coronal (AVCN-DCN)", None, Qt.QApplication.UnicodeUTF8))
        self.slicePlaneCombo.setItemText(2, Qt.QApplication.translate("Form", "Coronal (PVCN-DCN)", None, Qt.QApplication.UnicodeUTF8))
        self.slicePlaneCombo.setItemText(3, Qt.QApplication.translate("Form", "Horizontal (VCN)", None, Qt.QApplication.UnicodeUTF8))
        self.label_2.setText(Qt.QApplication.translate("Form", "Hemisphere", None, Qt.QApplication.UnicodeUTF8))
        self.hemisphereCombo.setItemText(0, Qt.QApplication.translate("Form", "Left", None, Qt.QApplication.UnicodeUTF8))
        self.hemisphereCombo.setItemText(1, Qt.QApplication.translate("Form", "Right", None, Qt.QApplication.UnicodeUTF8))
        self.label_3.setText(Qt.QApplication.translate("Form", "Thickness", None, Qt.QApplication.UnicodeUTF8))
        self.photoCheck.setText(Qt.QApplication.translate("Form", "Photo", None, Qt.QApplication.UnicodeUTF8))
        self.drawingCheck.setText(Qt.QApplication.translate("Form", "Drawing", None, Qt.QApplication.UnicodeUTF8))

from pyqtgraph.SpinBox import SpinBox
