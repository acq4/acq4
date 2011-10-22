# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'GeneratorTemplate.ui'
#
# Created: Sat Oct 22 14:33:29 2011
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
        Form.resize(480, 395)
        Form.setMinimumSize(QtCore.QSize(0, 100))
        self.verticalLayout_4 = QtGui.QVBoxLayout(Form)
        self.verticalLayout_4.setSpacing(0)
        self.verticalLayout_4.setMargin(0)
        self.verticalLayout_4.setObjectName(_fromUtf8("verticalLayout_4"))
        self.frame = QtGui.QFrame(Form)
        self.frame.setFrameShape(QtGui.QFrame.StyledPanel)
        self.frame.setFrameShadow(QtGui.QFrame.Raised)
        self.frame.setObjectName(_fromUtf8("frame"))
        self.verticalLayout = QtGui.QVBoxLayout(self.frame)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setMargin(0)
        self.verticalLayout.setObjectName(_fromUtf8("verticalLayout"))
        self.stack = QtGui.QStackedWidget(self.frame)
        self.stack.setObjectName(_fromUtf8("stack"))
        self.page = QtGui.QWidget()
        self.page.setObjectName(_fromUtf8("page"))
        self.verticalLayout_3 = QtGui.QVBoxLayout(self.page)
        self.verticalLayout_3.setSpacing(0)
        self.verticalLayout_3.setObjectName(_fromUtf8("verticalLayout_3"))
        self.stimulusTree = ParameterTree(self.page)
        self.stimulusTree.setHeaderHidden(True)
        self.stimulusTree.setObjectName(_fromUtf8("stimulusTree"))
        self.stimulusTree.headerItem().setText(0, _fromUtf8("1"))
        self.verticalLayout_3.addWidget(self.stimulusTree)
        self.advSplitter = QtGui.QSplitter(self.page)
        self.advSplitter.setOrientation(QtCore.Qt.Vertical)
        self.advSplitter.setChildrenCollapsible(False)
        self.advSplitter.setObjectName(_fromUtf8("advSplitter"))
        self.functionText = QtGui.QTextEdit(self.advSplitter)
        self.functionText.setMinimumSize(QtCore.QSize(0, 15))
        self.functionText.setObjectName(_fromUtf8("functionText"))
        self.seqTree = ParameterTree(self.advSplitter)
        self.seqTree.setObjectName(_fromUtf8("seqTree"))
        self.seqTree.headerItem().setText(0, _fromUtf8("1"))
        self.seqTree.header().setVisible(False)
        self.errorText = QtGui.QTextBrowser(self.advSplitter)
        self.errorText.setMinimumSize(QtCore.QSize(0, 15))
        self.errorText.setObjectName(_fromUtf8("errorText"))
        self.verticalLayout_3.addWidget(self.advSplitter)
        self.stack.addWidget(self.page)
        self.page_2 = QtGui.QWidget()
        self.page_2.setObjectName(_fromUtf8("page_2"))
        self.verticalLayout_2 = QtGui.QVBoxLayout(self.page_2)
        self.verticalLayout_2.setMargin(0)
        self.verticalLayout_2.setObjectName(_fromUtf8("verticalLayout_2"))
        self.textBrowser = QtGui.QTextBrowser(self.page_2)
        self.textBrowser.setObjectName(_fromUtf8("textBrowser"))
        self.verticalLayout_2.addWidget(self.textBrowser)
        self.textBrowser_2 = QtGui.QTextBrowser(self.page_2)
        self.textBrowser_2.setObjectName(_fromUtf8("textBrowser_2"))
        self.verticalLayout_2.addWidget(self.textBrowser_2)
        self.stack.addWidget(self.page_2)
        self.verticalLayout.addWidget(self.stack)
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.advancedBtn = QtGui.QPushButton(self.frame)
        self.advancedBtn.setCheckable(True)
        self.advancedBtn.setObjectName(_fromUtf8("advancedBtn"))
        self.horizontalLayout.addWidget(self.advancedBtn)
        self.errorBtn = QtGui.QToolButton(self.frame)
        self.errorBtn.setEnabled(True)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.errorBtn.sizePolicy().hasHeightForWidth())
        self.errorBtn.setSizePolicy(sizePolicy)
        font = QtGui.QFont()
        font.setWeight(75)
        font.setBold(True)
        self.errorBtn.setFont(font)
        self.errorBtn.setCheckable(True)
        self.errorBtn.setObjectName(_fromUtf8("errorBtn"))
        self.horizontalLayout.addWidget(self.errorBtn)
        self.helpBtn = QtGui.QToolButton(self.frame)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.helpBtn.sizePolicy().hasHeightForWidth())
        self.helpBtn.setSizePolicy(sizePolicy)
        font = QtGui.QFont()
        font.setWeight(75)
        font.setBold(True)
        self.helpBtn.setFont(font)
        self.helpBtn.setCheckable(True)
        self.helpBtn.setObjectName(_fromUtf8("helpBtn"))
        self.horizontalLayout.addWidget(self.helpBtn)
        spacerItem = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.horizontalLayout.addItem(spacerItem)
        self.updateBtn = QtGui.QPushButton(self.frame)
        self.updateBtn.setObjectName(_fromUtf8("updateBtn"))
        self.horizontalLayout.addWidget(self.updateBtn)
        self.autoUpdateCheck = QtGui.QCheckBox(self.frame)
        self.autoUpdateCheck.setObjectName(_fromUtf8("autoUpdateCheck"))
        self.horizontalLayout.addWidget(self.autoUpdateCheck)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.verticalLayout_4.addWidget(self.frame)

        self.retranslateUi(Form)
        self.stack.setCurrentIndex(0)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.functionText.setHtml(QtGui.QApplication.translate("Form", "<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.0//EN\" \"http://www.w3.org/TR/REC-html40/strict.dtd\">\n"
"<html><head><meta name=\"qrichtext\" content=\"1\" /><style type=\"text/css\">\n"
"p, li { white-space: pre-wrap; }\n"
"</style></head><body style=\" font-family:\'Ubuntu\'; font-size:9pt; font-weight:400; font-style:normal;\">\n"
"<p style=\"-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-family:\'Sans Serif\'; font-size:7pt;\"></p></body></html>", None, QtGui.QApplication.UnicodeUTF8))
        self.textBrowser.setHtml(QtGui.QApplication.translate("Form", "<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.0//EN\" \"http://www.w3.org/TR/REC-html40/strict.dtd\">\n"
"<html><head><meta name=\"qrichtext\" content=\"1\" /><style type=\"text/css\">\n"
"p, li { white-space: pre-wrap; }\n"
"</style></head><body style=\" font-family:\'Ubuntu\'; font-size:9pt; font-weight:400; font-style:normal;\">\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:7pt; font-weight:600;\">Functions:</span><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\"> any valid Python expression is allowed. A few useful functions are provided:</span></p>\n"
"<p style=\"-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-family:\'Sans Serif\'; font-size:7pt;\"></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\">steps( </span><span style=\" font-family:\'Sans Serif\'; font-size:7pt; font-style:italic;\">times</span><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\">, </span><span style=\" font-family:\'Sans Serif\'; font-size:7pt; font-style:italic;\">values</span><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\">, [</span><span style=\" font-family:\'Sans Serif\'; font-size:7pt; font-style:italic;\">base</span><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\">=0.0] )</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\">pulse( </span><span style=\" font-family:\'Sans Serif\'; font-size:7pt; font-style:italic;\">times</span><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\">, </span><span style=\" font-family:\'Sans Serif\'; font-size:7pt; font-style:italic;\">widths</span><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\">, </span><span style=\" font-family:\'Sans Serif\'; font-size:7pt; font-style:italic;\">values</span><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\">, [</span><span style=\" font-family:\'Sans Serif\'; font-size:7pt; font-style:italic;\">base</span><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\">=0.0] )</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\">sineWave(</span><span style=\" font-family:\'Sans Serif\'; font-size:7pt; font-style:italic;\">period, amplitude=1.0, phase=0.0, start=0.0, stop=None, base=0.0</span><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\">)</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\">squareWave(</span><span style=\" font-family:\'Sans Serif\'; font-size:7pt; font-style:italic;\">period, amplitude=1.0, phase=0.0, duty=0.5, start=0.0, stop=None, base=0.0</span><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\">)</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\">sawWave(</span><span style=\" font-family:\'Sans Serif\'; font-size:7pt; font-style:italic;\">period, amplitude=1.0, phase=0.0, start=0.0, stop=None, base=0.0</span><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\">)</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\">listWave(</span><span style=\" font-family:\'Sans Serif\'; font-size:7pt; font-style:italic;\">period, values, phase=0.0, start=0.0, stop=None, base=0.0</span><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\">)</span></p>\n"
"<p style=\"-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-family:\'Sans Serif\'; font-size:7pt;\"></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\">In each of these functions, </span><span style=\" font-family:\'Sans Serif\'; font-size:7pt; font-style:italic;\">times</span><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\"> must be specified as a list of times in seconds. Lists are notated as numbers enclosed in brackets and separated by commas like [0.0, 0.2, ...]. The steps function also requires a list of </span><span style=\" font-family:\'Sans Serif\'; font-size:7pt; font-style:italic;\">values.</span><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\"> The pulses function can accept either lists or single values for </span><span style=\" font-family:\'Sans Serif\'; font-size:7pt; font-style:italic;\">widths</span><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\"> and </span><span style=\" font-family:\'Sans Serif\'; font-size:7pt; font-style:italic;\">values</span><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\">. The argument </span><span style=\" font-family:\'Sans Serif\'; font-size:7pt; font-style:italic;\">base</span><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\"> is optional for both functions.</span></p></body></html>", None, QtGui.QApplication.UnicodeUTF8))
        self.textBrowser_2.setHtml(QtGui.QApplication.translate("Form", "<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.0//EN\" \"http://www.w3.org/TR/REC-html40/strict.dtd\">\n"
"<html><head><meta name=\"qrichtext\" content=\"1\" /><style type=\"text/css\">\n"
"p, li { white-space: pre-wrap; }\n"
"</style></head><body style=\" font-family:\'Ubuntu\'; font-size:9pt; font-weight:400; font-style:normal;\">\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:7pt; font-weight:600;\">Parameters</span><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\"> are defined like:</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\">    parameter_name = value</span></p>\n"
"<p style=\"-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-family:\'Sans Serif\'; font-size:7pt;\"></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\">Each parameter can be used in place of numerical values in the function. Parameters may also define a sequence of values like:</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\">    parameter_name = value; first:last/num</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\">    parameter_name = value; first:last:step</span></p>\n"
"<p style=\"-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-family:\'Sans Serif\'; font-size:7pt;\"></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\">Optional arguments \'l\' (log), \'r\' (randomize) may be added at the end after a colon:</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:7pt;\">    parameter_name = value; first:last/num:opts</span></p>\n"
"<p style=\"-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-family:\'Sans Serif\'; font-size:7pt;\"></p></body></html>", None, QtGui.QApplication.UnicodeUTF8))
        self.advancedBtn.setText(QtGui.QApplication.translate("Form", "Advanced", None, QtGui.QApplication.UnicodeUTF8))
        self.errorBtn.setText(QtGui.QApplication.translate("Form", "!", None, QtGui.QApplication.UnicodeUTF8))
        self.helpBtn.setText(QtGui.QApplication.translate("Form", "?", None, QtGui.QApplication.UnicodeUTF8))
        self.updateBtn.setText(QtGui.QApplication.translate("Form", "Update", None, QtGui.QApplication.UnicodeUTF8))
        self.autoUpdateCheck.setText(QtGui.QApplication.translate("Form", "Auto", None, QtGui.QApplication.UnicodeUTF8))

from pyqtgraph.parametertree import ParameterTree
