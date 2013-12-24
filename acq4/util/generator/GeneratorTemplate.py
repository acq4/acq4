# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file './acq4/util/generator/GeneratorTemplate.ui'
#
# Created: Tue Dec 24 01:49:16 2013
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
        Form.resize(336, 439)
        Form.setMinimumSize(QtCore.QSize(0, 100))
        self.verticalLayout_5 = QtGui.QVBoxLayout(Form)
        self.verticalLayout_5.setSpacing(0)
        self.verticalLayout_5.setMargin(0)
        self.verticalLayout_5.setObjectName(_fromUtf8("verticalLayout_5"))
        self.frame = QtGui.QFrame(Form)
        self.frame.setFrameShape(QtGui.QFrame.StyledPanel)
        self.frame.setFrameShadow(QtGui.QFrame.Raised)
        self.frame.setObjectName(_fromUtf8("frame"))
        self.verticalLayout_4 = QtGui.QVBoxLayout(self.frame)
        self.verticalLayout_4.setSpacing(0)
        self.verticalLayout_4.setMargin(0)
        self.verticalLayout_4.setObjectName(_fromUtf8("verticalLayout_4"))
        self.splitter = QtGui.QSplitter(self.frame)
        self.splitter.setOrientation(QtCore.Qt.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setObjectName(_fromUtf8("splitter"))
        self.stack = QtGui.QStackedWidget(self.splitter)
        self.stack.setObjectName(_fromUtf8("stack"))
        self.page = QtGui.QWidget()
        self.page.setObjectName(_fromUtf8("page"))
        self.verticalLayout_3 = QtGui.QVBoxLayout(self.page)
        self.verticalLayout_3.setSpacing(0)
        self.verticalLayout_3.setMargin(0)
        self.verticalLayout_3.setObjectName(_fromUtf8("verticalLayout_3"))
        self.stimulusTree = ParameterTree(self.page)
        self.stimulusTree.setHeaderHidden(True)
        self.stimulusTree.setObjectName(_fromUtf8("stimulusTree"))
        self.stimulusTree.headerItem().setText(0, _fromUtf8("1"))
        self.verticalLayout_3.addWidget(self.stimulusTree)
        self.stack.addWidget(self.page)
        self.page_3 = QtGui.QWidget()
        self.page_3.setObjectName(_fromUtf8("page_3"))
        self.gridLayout = QtGui.QGridLayout(self.page_3)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        spacerItem = QtGui.QSpacerItem(20, 76, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem, 0, 1, 1, 1)
        self.label = QtGui.QLabel(self.page_3)
        self.label.setTextFormat(QtCore.Qt.AutoText)
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        self.label.setWordWrap(True)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 1, 0, 1, 3)
        spacerItem1 = QtGui.QSpacerItem(93, 78, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridLayout.addItem(spacerItem1, 2, 0, 2, 1)
        self.forceAdvancedBtn = QtGui.QPushButton(self.page_3)
        self.forceAdvancedBtn.setObjectName(_fromUtf8("forceAdvancedBtn"))
        self.gridLayout.addWidget(self.forceAdvancedBtn, 2, 1, 1, 1)
        spacerItem2 = QtGui.QSpacerItem(92, 78, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridLayout.addItem(spacerItem2, 2, 2, 2, 1)
        self.forceSimpleBtn = QtGui.QPushButton(self.page_3)
        self.forceSimpleBtn.setObjectName(_fromUtf8("forceSimpleBtn"))
        self.gridLayout.addWidget(self.forceSimpleBtn, 3, 1, 1, 1)
        spacerItem3 = QtGui.QSpacerItem(20, 75, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem3, 4, 1, 1, 1)
        self.stack.addWidget(self.page_3)
        self.page_4 = QtGui.QWidget()
        self.page_4.setObjectName(_fromUtf8("page_4"))
        self.verticalLayout = QtGui.QVBoxLayout(self.page_4)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setMargin(0)
        self.verticalLayout.setObjectName(_fromUtf8("verticalLayout"))
        self.splitter_2 = QtGui.QSplitter(self.page_4)
        self.splitter_2.setOrientation(QtCore.Qt.Vertical)
        self.splitter_2.setChildrenCollapsible(False)
        self.splitter_2.setObjectName(_fromUtf8("splitter_2"))
        self.functionText = QtGui.QTextEdit(self.splitter_2)
        self.functionText.setMinimumSize(QtCore.QSize(0, 15))
        self.functionText.setObjectName(_fromUtf8("functionText"))
        self.seqTree = ParameterTree(self.splitter_2)
        self.seqTree.setObjectName(_fromUtf8("seqTree"))
        self.seqTree.headerItem().setText(0, _fromUtf8("1"))
        self.seqTree.header().setVisible(False)
        self.verticalLayout.addWidget(self.splitter_2)
        self.stack.addWidget(self.page_4)
        self.page_2 = QtGui.QWidget()
        self.page_2.setObjectName(_fromUtf8("page_2"))
        self.verticalLayout_2 = QtGui.QVBoxLayout(self.page_2)
        self.verticalLayout_2.setMargin(0)
        self.verticalLayout_2.setObjectName(_fromUtf8("verticalLayout_2"))
        self.textBrowser = QtGui.QTextBrowser(self.page_2)
        self.textBrowser.setObjectName(_fromUtf8("textBrowser"))
        self.verticalLayout_2.addWidget(self.textBrowser)
        self.stack.addWidget(self.page_2)
        self.errorText = QtGui.QTextBrowser(self.splitter)
        self.errorText.setMinimumSize(QtCore.QSize(0, 15))
        self.errorText.setObjectName(_fromUtf8("errorText"))
        self.verticalLayout_4.addWidget(self.splitter)
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setSpacing(0)
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
        font.setBold(True)
        font.setWeight(75)
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
        font.setBold(True)
        font.setWeight(75)
        self.helpBtn.setFont(font)
        self.helpBtn.setCheckable(True)
        self.helpBtn.setObjectName(_fromUtf8("helpBtn"))
        self.horizontalLayout.addWidget(self.helpBtn)
        spacerItem4 = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.horizontalLayout.addItem(spacerItem4)
        self.updateBtn = QtGui.QPushButton(self.frame)
        self.updateBtn.setObjectName(_fromUtf8("updateBtn"))
        self.horizontalLayout.addWidget(self.updateBtn)
        self.autoUpdateCheck = QtGui.QCheckBox(self.frame)
        self.autoUpdateCheck.setObjectName(_fromUtf8("autoUpdateCheck"))
        self.horizontalLayout.addWidget(self.autoUpdateCheck)
        self.verticalLayout_4.addLayout(self.horizontalLayout)
        self.verticalLayout_5.addWidget(self.frame)

        self.retranslateUi(Form)
        self.stack.setCurrentIndex(0)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(_translate("Form", "Form", None))
        self.label.setText(_translate("Form", "Warning: Changes have been made to the function in advanced mode. These changes will be overwritten if you exit advanced mode. ", None))
        self.forceAdvancedBtn.setText(_translate("Form", "Back to\n"
"Advanced Mode", None))
        self.forceSimpleBtn.setText(_translate("Form", "Change to\n"
"Simple Mode", None))
        self.functionText.setHtml(_translate("Form", "<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.0//EN\" \"http://www.w3.org/TR/REC-html40/strict.dtd\">\n"
"<html><head><meta name=\"qrichtext\" content=\"1\" /><style type=\"text/css\">\n"
"p, li { white-space: pre-wrap; }\n"
"</style></head><body style=\" font-family:\'MS Shell Dlg 2\'; font-size:8.25pt; font-weight:400; font-style:normal;\">\n"
"<p style=\"-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-family:\'Sans Serif\'; font-size:7pt;\"></p></body></html>", None))
        self.textBrowser.setHtml(_translate("Form", "<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.0//EN\" \"http://www.w3.org/TR/REC-html40/strict.dtd\">\n"
"<html><head><meta name=\"qrichtext\" content=\"1\" /><style type=\"text/css\">\n"
"p, li { white-space: pre-wrap; }\n"
"</style></head><body style=\" font-family:\'MS Shell Dlg 2\'; font-size:8.25pt; font-weight:400; font-style:normal;\">\n"
"<p align=\"center\" style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Ubuntu\'; font-size:9pt; font-weight:600;\">Waveform Generator Reference</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Ubuntu\'; font-size:8pt;\">Arbitrary waveforms may be generated by entering a Python expression which returns an array of values. The easiest approach is to use one (or more) of the built-in functions:</span></p>\n"
"<ul style=\"margin-top: 0px; margin-bottom: 0px; margin-left: 0px; margin-right: 0px; -qt-list-indent: 1;\"><li style=\" font-family:\'Ubuntu\'; font-size:8pt;\" style=\" margin-top:12px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><a href=\"#steps\"><span style=\" text-decoration: underline; color:#0057ae;\">steps</span></a> - step the waveform to new values at specific times</li>\n"
"<li style=\" font-family:\'Ubuntu\'; font-size:8pt;\" style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><a href=\"#pulse\"><span style=\" text-decoration: underline; color:#0057ae;\">pulse</span></a> - generate one or more square pulses</li>\n"
"<li style=\" font-family:\'Ubuntu\'; font-size:8pt;\" style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><a href=\"#waves\"><span style=\" text-decoration: underline; color:#0057ae;\">squareWave</span></a> - generate a square wave over a specific time range</li>\n"
"<li style=\" font-family:\'Ubuntu\'; font-size:8pt;\" style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><a href=\"#waves\"><span style=\" text-decoration: underline; color:#0057ae;\">sineWave</span></a> - generate a sine wave over a specific time range</li>\n"
"<li style=\" font-family:\'Ubuntu\'; font-size:8pt;\" style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><a href=\"#waves\"><span style=\" text-decoration: underline; color:#0057ae;\">sawWave</span></a> - generate a saw wave over a specific time range</li>\n"
"<li style=\" font-family:\'Ubuntu\'; font-size:8pt;\" style=\" margin-top:0px; margin-bottom:12px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><a href=\"#waves\"><span style=\" text-decoration: underline; color:#0057ae;\">listWave</span></a> - repeat a series of values over a specific time range</li></ul>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Ubuntu\'; font-size:8pt;\">Numerical values may be specified with standard scaled-unit variables like &quot;mV&quot; and &quot;kHz&quot; (these values should be multiplied with a number, eg 120*kHz). </span></p>\n"
"<p style=\"-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-family:\'Ubuntu\'; font-size:8pt;\"></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Ubuntu\'; font-size:8pt; font-weight:600;\">Sequence Parameters</span><span style=\" font-family:\'Ubuntu\'; font-size:8pt;\">: Commonly, we want a function to run multiple times while varying one or more of its parameters. To accomplish this, click &quot;Add Sequence Parameter&quot;, configure the new parameter\'s properties, and substitute any numerical value in the function with the name of the new parameter. Parameters may be renamed or removed by right clicking on their name.</span></p>\n"
"<p style=\"-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-family:\'Ubuntu\'; font-size:8pt;\"></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Ubuntu\'; font-size:8pt; font-weight:600;\">Function Reference:</span></p>\n"
"<p style=\"-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-family:\'Ubuntu\'; font-size:8pt; font-weight:600;\"></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt; font-weight:600;\">steps</span><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">( times, values, [base=0.0] )</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">Steps the waveform to new values at specific times.</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">    times - list of times marking each step</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">                 eg: [1*ms, 10*ms, 30*ms]</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">    values - list of values</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">                 eg: [0*mV, 30*mV, 0*mV]</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">    base - the initial value of the waveform</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">Example: start at 0mV, step down to -30mV at 50ms, then step up to 30mV at 100ms</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">    steps([50*ms, 100*ms], [-30*mV, 30*mV])</span></p>\n"
"<p style=\"-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-family:\'Sans Serif\'; font-size:8pt;\"></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt; font-weight:600;\">pulse</span><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">( times, widths, values, [base=0.0] )</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">Generates one or more square pulses</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">    times - a value or a list of values marking the time of the pulse(s)</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">    widths - a value or a list of values indicating the width of the pulse(s)</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">    values - a value or a list of values indicating the height of the pulse(s)</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">    base - the baseline value of the waveform</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">Example:  20pA pulse starting at 10ms and ending at 40ms</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">    pulse(10*ms, 30*ms, 20*pA)</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">Example:  20 and 30pA pulses, 10ms wide, starting at 20 and 40ms</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">    pulse([20*ms, 40*ms], 10*ms, [20*pA, 30*pA])</span></p>\n"
"<p style=\"-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-family:\'Sans Serif\'; font-size:8pt;\"></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt; font-weight:600;\">sineWave</span><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">(period, amplitude=1.0, phase=0.0, start=0.0, stop=None, base=0.0)</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt; font-weight:600;\">squareWave</span><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">(period, amplitude=1.0, phase=0.0, duty=0.5, start=0.0, stop=None, base=0.0)</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt; font-weight:600;\">sawWave</span><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">(period, amplitude=1.0, phase=0.0, start=0.0, stop=None, base=0.0)</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt; font-weight:600;\">listWave</span><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">(period, values, phase=0.0, start=0.0, stop=None, base=0.0)</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">These functions generate periodic waveforms using (mostly) identical arguments.</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">    period - the period of the wave. Eg: 10*us or 1.0/(100*kHz)</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">    amplitude - the peak amplitude of the wave. Eg: 10*mV</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">    phase - the starting phase of the wave in cycles (ie, 0.5 means 180 degrees)</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">    start - the starting time of the waveform. Everything before uses the base value.</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">    stop - the stopping time of the waveform. Everything after uses the base value.</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">    base - value to use before start/stop of wave.</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">Specific to squareWave:</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">    duty - The duty cycle of the wave (0.0 - 1.0)</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">Specific to listWave:</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Sans Serif\'; font-size:8pt;\">    values - the list of values that are iterated over for each cycle of the wave. </span></p>\n"
"<p style=\"-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-family:\'Sans Serif\'; font-size:8pt;\"></p>\n"
"<p style=\"-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-family:\'Ubuntu\'; font-size:8pt;\"></p>\n"
"<p style=\"-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-family:\'Ubuntu\'; font-size:8pt;\"></p></body></html>", None))
        self.errorText.setHtml(_translate("Form", "<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.0//EN\" \"http://www.w3.org/TR/REC-html40/strict.dtd\">\n"
"<html><head><meta name=\"qrichtext\" content=\"1\" /><style type=\"text/css\">\n"
"p, li { white-space: pre-wrap; }\n"
"</style></head><body style=\" font-family:\'MS Shell Dlg 2\'; font-size:8.25pt; font-weight:400; font-style:normal;\">\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-family:\'Ubuntu\'; font-size:9pt;\">No Error.</span></p></body></html>", None))
        self.advancedBtn.setText(_translate("Form", "Advanced", None))
        self.errorBtn.setText(_translate("Form", "!", None))
        self.helpBtn.setText(_translate("Form", "?", None))
        self.updateBtn.setText(_translate("Form", "Update", None))
        self.autoUpdateCheck.setText(_translate("Form", "Auto", None))

from acq4.pyqtgraph.parametertree import ParameterTree
