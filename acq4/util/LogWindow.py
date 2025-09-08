import re
from logging import LogRecord

from acq4.util import Qt
from pyqtgraph import FeedbackButton
from pyqtgraph.debug import threadName
from teleprox.log.logviewer import LogViewer
from teleprox.log.logviewer.viewer import QtLogHandler

LOG_UI = None
ERROR_DIALOG = None


def __reload__(old):
    # preserve old log UIs
    global LOG_UI, ERROR_DIALOG
    LOG_UI = old["LOG_UI"]
    ERROR_DIALOG = old["ERROR_DIALOG"]


def get_log_window():
    global LOG_UI
    if LOG_UI is None:
        from acq4.util.codeEditor import invokeCodeEditor

        LOG_UI = LogViewer()
        LOG_UI.code_line_clicked.connect(invokeCodeEditor)
    return LOG_UI


def get_error_dialog():
    global ERROR_DIALOG
    if ERROR_DIALOG is None:
        ERROR_DIALOG = ErrorDialog()
    return ERROR_DIALOG


class LogButton(FeedbackButton):
    def __init__(self, *args):
        FeedbackButton.__init__(self, *args)

        self.clicked.connect(get_log_window().show)


class ErrorDialog(Qt.QDialog):
    def __init__(self):
        Qt.QDialog.__init__(self)

        self.handler = QtLogHandler()
        self.handler.new_record.connect(self.show)

        self.setWindowFlags(Qt.Qt.Window)
        self.setWindowTitle("ACQ4 Error")
        self.layout = Qt.QVBoxLayout()
        self.layout.setContentsMargins(3, 3, 3, 3)
        self.setLayout(self.layout)
        self.messages = []

        self.msgLabel = Qt.QLabel()
        self.msgLabel.setSizePolicy(Qt.QSizePolicy.Expanding, Qt.QSizePolicy.Expanding)
        self.layout.addWidget(self.msgLabel)
        self.msgLabel.setMaximumWidth(800)
        self.msgLabel.setMinimumWidth(500)
        self.msgLabel.setWordWrap(True)
        self.layout.addStretch()
        self.disableCheck = Qt.QCheckBox("Disable error message popups")
        self.layout.addWidget(self.disableCheck)

        self.btnLayout = Qt.QHBoxLayout()
        self.btnLayout.addStretch()
        self.okBtn = Qt.QPushButton("OK")
        self.btnLayout.addWidget(self.okBtn)
        self.nextBtn = Qt.QPushButton("Show next error")
        self.btnLayout.addWidget(self.nextBtn)
        self.nextBtn.hide()
        self.logBtn = Qt.QPushButton("Show Log...")
        self.btnLayout.addWidget(self.logBtn)
        self.btnLayoutWidget = Qt.QWidget()
        self.layout.addWidget(self.btnLayoutWidget)
        self.btnLayoutWidget.setLayout(self.btnLayout)
        self.btnLayout.addStretch()

        self.okBtn.clicked.connect(self.okClicked)
        self.nextBtn.clicked.connect(self.nextMessage)
        self.logBtn.clicked.connect(self.logClicked)

    def show(self, entry: LogRecord):
        msgLines = []
        if entry.getMessage():
            msgLines.append(self.cleanText(entry.getMessage()))
        if entry.exc_info:
            msgLines.append(self.cleanText(str(entry.exc_info[1])))

        msg = "<br/>".join(msgLines)

        if self.disableCheck.isChecked():
            return False
        if self.isVisible():
            self.messages.append(msg)
            self.nextBtn.show()
            self.nextBtn.setEnabled(True)
            self.nextBtn.setText("Show next error (%d more)" % len(self.messages))
        else:
            w = Qt.QApplication.activeWindow()
            self.nextBtn.hide()
            self.msgLabel.setText(msg)
            self.open()
            if w is not None:
                cp = w.geometry().center()
                self.setGeometry(
                    int(cp.x() - self.width() / 2.0),
                    int(cp.y() - self.height() / 2.0),
                    self.width(),
                    self.height(),
                )
        self.raise_()

    @staticmethod
    def cleanText(text):
        text = re.sub(r"&", "&amp;", text)
        text = re.sub(r">", "&gt;", text)
        text = re.sub(r"<", "&lt;", text)
        text = re.sub(r"\n", "<br/>\n", text)
        return text

    def closeEvent(self, ev):
        Qt.QDialog.closeEvent(self, ev)
        self.messages = []

    def okClicked(self):
        self.accept()
        self.messages = []

    def logClicked(self):
        self.accept()
        log = get_log_window()
        log.show()
        log.raise_()
        self.messages = []

    def nextMessage(self):
        self.msgLabel.setText(self.messages.pop(0))
        self.nextBtn.setText("Show next error (%d more)" % len(self.messages))
        if len(self.messages) == 0:
            self.nextBtn.setEnabled(False)

    def disable(self, disable):
        self.disableCheck.setChecked(disable)
