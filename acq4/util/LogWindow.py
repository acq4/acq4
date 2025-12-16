import re
import webbrowser
from logging import LogRecord

from pyqtgraph import FeedbackButton
from teleprox.log.logviewer import LogViewer
from teleprox.log.logviewer.constants import ItemDataRole
from teleprox.log.logviewer.constants import LogColumns
from teleprox.log.logviewer.filtering import LogFilterProxyModel
from teleprox.log.logviewer.filtering import USE_CHAINED_FILTERING
from teleprox.log.logviewer.log_model import LogModel
from teleprox.log.logviewer.viewer import QtLogHandler

from acq4.util import Qt

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

        LOG_UI = DocumentedLogViewer()
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

        self.clicked.connect(get_log_window().raise_window)


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
        elif entry.exc_info:
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


class DocumentedLogModel(LogModel):
    """Custom LogModel that handles 'docs' attribute as clickable documentation links."""

    def _get_attribute_handler(self, attr_name):
        """Override to add custom handler for 'docs' attribute."""
        # Check for docs attribute
        if attr_name == 'docs' or attr_name.endswith('_docs'):
            return self._create_docs_children

        # Fall back to parent implementation for all other attributes
        return super()._get_attribute_handler(attr_name)

    def _create_docs_children(self, record, attr_name, attr_value):
        """Create child items for documentation links."""
        children = []

        # Skip if docs is None or empty
        if not attr_value:
            return children

        # Create "Documentation" category
        docs_category_item = self._create_category_item(f"Documentation ({attr_name})", record)

        # Handle different docs formats
        if isinstance(attr_value, str):
            # Single doc link as string
            doc_links = [attr_value]
        elif isinstance(attr_value, (list, tuple)):
            # Multiple doc links
            doc_links = attr_value
        else:
            # Unknown format, convert to string
            doc_links = [str(attr_value)]

        # Create child items for each documentation link
        for i, doc_link in enumerate(doc_links):
            doc_url = str(doc_link).strip()
            if doc_url:
                # Create clickable documentation link item
                doc_row = self._create_child_row(
                    "",
                    f"📖 {doc_url}",  # Using book emoji to indicate it's a doc link
                    {
                        'type': 'documentation_link',
                        'text': doc_url,
                        'url': doc_url,
                        'link_index': i,
                        'parent_record': record,
                    },
                    record,
                )
                docs_category_item.appendRow(doc_row)

        # Create sibling items for the docs category
        sibling_items = self._create_sibling_items_with_filter_data(record)
        children.append([docs_category_item] + sibling_items)

        return children

    def _create_child_row(self, label, message, data_dict, parent_record):
        """Override to make documentation links clickable."""
        child_row = super()._create_child_row(label, message, data_dict, parent_record)

        # Make documentation links clickable
        if data_dict.get('type') == 'documentation_link':
            item = child_row[0]
            item.setFlags(Qt.Qt.ItemIsEnabled | Qt.Qt.ItemIsSelectable)  # Allow clicking

            # Style documentation links differently
            item.setForeground(Qt.QColor("#0066CC"))  # Blue for links
            font = item.font()
            font.setUnderline(True)  # Underline to indicate it's clickable
            item.setFont(font)

        return child_row

    def _create_remote_exception_children(self, exc_value, record):
        """Override to add docs support for exceptions that have getattr(exc, 'docs', [])."""
        # Get the standard remote exception children first
        children = super()._create_remote_exception_children(exc_value, record)

        # Check if this exception has docs attribute
        if hasattr(exc_value, 'docs'):
            docs_attr = getattr(exc_value, 'docs', None)
            if docs_attr:
                # Use our docs handler to create documentation children
                docs_children = self._create_docs_children(record, 'exception_docs', docs_attr)
                children.extend(docs_children)

        return children


class DocumentedLogViewer(LogViewer):
    """Custom LogViewer that handles documentation link clicks."""

    # Signal emitted when user clicks on a documentation link
    documentation_link_clicked = Qt.Signal(str)  # (url)

    def __init__(self, logger='', initial_filters=('level: info',), parent=None):
        # Call parent __init__ first
        super().__init__(logger, initial_filters, parent)

        # Replace the standard model with our custom one
        self._replace_model_with_custom()

        # Connect our custom signal to open URLs in browser
        self.documentation_link_clicked.connect(self._open_documentation_link)

    def raise_window(self):
        """Bring the log window to the front."""
        self.show()
        self.raise_()
        self.activateWindow()

    def _replace_model_with_custom(self):
        """Replace the standard LogModel with our CustomLogModel."""
        # Create our custom model
        custom_model = DocumentedLogModel()
        custom_model.setHorizontalHeaderLabels(LogColumns.TITLES)

        # Replace the model in the proxy
        if USE_CHAINED_FILTERING:
            # For chained filtering, we need to update the source model
            if hasattr(self.proxy_model, 'set_source_model'):
                self.proxy_model.set_source_model(custom_model)
            elif hasattr(self.proxy_model, '_source_model'):
                self.proxy_model._source_model = custom_model
            else:
                # Fallback: recreate proxy with new model
                self.proxy_model = LogFilterProxyModel(custom_model)
                self.tree.setModel(self.proxy_model.final_model)
        else:
            # For simple proxy model, just set source model
            self.proxy_model.setSourceModel(custom_model)

        # Update our reference to the model
        self.model = custom_model

    def _on_item_clicked(self, index):
        """Override to handle documentation link clicks."""
        if not index.isValid():
            return

        # Map to source model if using proxy
        source_index = self.map_index_to_model(index)

        # Get the actual item from our LogModel
        item = self.model.itemFromIndex(source_index)
        if not item:
            return

        # Check if this is a documentation link
        data = item.data(ItemDataRole.LOG_RECORD)
        if data and isinstance(data, dict) and data.get('type') == 'documentation_link':
            url = data.get('url')
            if url:
                # Emit our custom signal for documentation links
                self.documentation_link_clicked.emit(url)
                return

        # Fall back to parent implementation for other click types (code lines, etc.)
        super()._on_item_clicked(index)

    def _open_documentation_link(self, url):
        """Open documentation link in default browser."""
        webbrowser.open(f"https://acq4.readthedocs.io/en/latest/{url}")
