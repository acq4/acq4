import logging
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

logger = logging.getLogger(__name__)

LOG_UI = None
ERROR_DIALOG = None
LOG_TAIL_COUNT = 50


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


def confirmTeleproxServer(parent=None):
    """Ask permission to open a teleprox port so Claude can inspect this process.

    Starting a teleprox server permits arbitrary code execution in this ACQ4 for the
    rest of the session, so this is asked explicitly rather than assumed. Declining
    still produces a text-only handoff.
    """
    box = Qt.QMessageBox(parent)
    box.setIcon(Qt.QMessageBox.Warning)
    box.setWindowTitle("Allow live debugging access?")
    box.setText("Open a local debugging port so Claude can inspect this ACQ4?")
    box.setInformativeText(
        "This opens a loopback port that allows code to run inside this ACQ4 process "
        "until it exits, which is what lets Claude read device and task state directly.\n\n"
        "Decline and Claude still gets the log record and traceback, just not live access."
    )
    box.setStandardButtons(Qt.QMessageBox.Yes | Qt.QMessageBox.No)
    box.setDefaultButton(Qt.QMessageBox.No)
    return box.exec_() == Qt.QMessageBox.Yes


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
        self.records = []        # queued LogRecords not yet displayed
        self.currentRecord = None  # the record on display, for the Claude handoff

        self.msgLabel = Qt.QLabel()
        self.msgLabel.setTextFormat(Qt.Qt.RichText)
        self.msgLabel.setSizePolicy(Qt.QSizePolicy.Expanding, Qt.QSizePolicy.Minimum)
        self.msgLabel.setMinimumWidth(500)
        self.msgLabel.setWordWrap(True)
        self.layout.addWidget(self.msgLabel)

        self.excEdit = Qt.QPlainTextEdit()
        self.excEdit.setReadOnly(True)
        self.excEdit.setLineWrapMode(Qt.QPlainTextEdit.WidgetWidth)
        self.excEdit.setHorizontalScrollBarPolicy(Qt.Qt.ScrollBarAlwaysOff)
        _exc_font = Qt.QFont("Consolas")
        _exc_font.setFixedPitch(True)
        self.excEdit.setFont(_exc_font)
        self.excEdit.setSizePolicy(Qt.QSizePolicy.Expanding, Qt.QSizePolicy.Expanding)
        self.excEdit.hide()
        self.layout.addWidget(self.excEdit)
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
        self.claudeBtn = Qt.QPushButton("Debug with Claude")
        self.btnLayout.addWidget(self.claudeBtn)
        self.btnLayoutWidget = Qt.QWidget()
        self.layout.addWidget(self.btnLayoutWidget)
        self.btnLayoutWidget.setLayout(self.btnLayout)
        self.btnLayout.addStretch()

        self.okBtn.clicked.connect(self.okClicked)
        self.nextBtn.clicked.connect(self.nextMessage)
        self.logBtn.clicked.connect(self.logClicked)
        self.claudeBtn.clicked.connect(self.claudeClicked)

    def show(self, entry: LogRecord):
        if self.disableCheck.isChecked():
            return False
        if self.isVisible():
            self.records.append(entry)
            self.nextBtn.show()
            self.nextBtn.setEnabled(True)
            self.nextBtn.setText("Show next error (%d more)" % len(self.records))
        else:
            w = Qt.QApplication.activeWindow()
            self.nextBtn.hide()
            self._displayRecord(entry)
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

    def _displayRecord(self, entry: LogRecord):
        """Show *entry* and remember it, so the Claude button has something to send."""
        self.currentRecord = entry
        msg = entry.getMessage()
        self.msgLabel.setText(self.cleanText(msg) if msg else "")
        self.msgLabel.setVisible(bool(msg))
        if entry.exc_info:
            self.excEdit.setPlainText(str(entry.exc_info[1]))
            self._fitExcEdit()
            self.excEdit.show()
        else:
            self.excEdit.clear()
            self.excEdit.hide()

    def _fitExcEdit(self):
        """Set a minimum height that fits the content; the widget expands beyond that."""
        n = self.excEdit.document().blockCount()
        line_h = self.excEdit.fontMetrics().lineSpacing()
        m = self.excEdit.contentsMargins()
        self.excEdit.setMinimumHeight(n * line_h + m.top() + m.bottom() + 8)

    @staticmethod
    def cleanText(text):
        text = re.sub(r"&", "&amp;", text)
        text = re.sub(r">", "&gt;", text)
        text = re.sub(r"<", "&lt;", text)
        text = re.sub(r"\n", "<br/>\n", text)
        return text

    def closeEvent(self, ev):
        Qt.QDialog.closeEvent(self, ev)
        self.records = []

    def okClicked(self):
        self.accept()
        self.records = []

    def logClicked(self):
        record = self.currentRecord
        self.accept()
        self.records = []
        get_log_window().raise_window_and_select(record)

    def nextMessage(self):
        self._displayRecord(self.records.pop(0))
        self.nextBtn.setText("Show next error (%d more)" % len(self.records))
        if len(self.records) == 0:
            self.nextBtn.setEnabled(False)

    def claudeClicked(self):
        if self.currentRecord is None:
            return
        from acq4.util import claude_debug

        claude_debug.debugRecordWithClaude(
            self.currentRecord, confirm=lambda: confirmTeleproxServer(self)
        )

    def disable(self, disable):
        self.disableCheck.setChecked(disable)


class DocumentedLogModel(LogModel):
    """Custom LogModel that handles 'docs' attribute as clickable documentation links."""

    def _get_column_text(self, record, col_id):
        """Show the gentletask throughline (task-name chain) in the Task column.

        The throughline is the chain of task names active when the record was
        emitted, set by ThroughlineNameFilter and carried on the record. It is
        joined with ' > '. Records without a throughline fall back to the base
        column text (taskName); every other column defers to the base.
        """
        if col_id == LogColumns.TASK:
            throughline = getattr(record, 'throughline', None)
            if throughline:
                if not hasattr(record, '_column_text_cache'):
                    record._column_text_cache = {}
                if col_id not in record._column_text_cache:
                    record._column_text_cache[col_id] = " > ".join(str(n) for n in throughline)
                return record._column_text_cache[col_id]
        return super()._get_column_text(record, col_id)

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
        elif data_dict.get('type') == 'exception':
            # Exception messages may contain space-aligned text; apply monospace so
            # the alignment is visible (base class only does this for traceback frames).
            item = child_row[0]
            font = item.font()
            font.setFamily("Consolas")
            font.setFixedPitch(True)
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

        # Surface the gentletask throughline: the base viewer ships a hidden
        # 'Task' column; show it (retitled 'Throughline' by the header below)
        # and give it room for a task-name chain.
        self.tree.setColumnHidden(LogColumns.TASK, False)
        self.tree.setColumnWidth(LogColumns.TASK, 250)

        # Connect our custom signal to open URLs in browser
        self.documentation_link_clicked.connect(self._open_documentation_link)

        if not hasattr(LogViewer, '_build_row_context_menu'):
            # NOTE: this method's own `logger` parameter (the teleprox logger name)
            # shadows the module logger above, so it is looked up explicitly here.
            logging.getLogger(__name__).warning(
                "The 'Debug with Claude' row context menu action is unavailable: the "
                "installed teleprox predates the _build_row_context_menu extension point. "
                "Update teleprox to restore it."
            )

    def raise_window(self):
        """Bring the log window to the front."""
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def raise_window_and_select(self, record):
        """Bring the log window to the front and select the given log record."""
        self.raise_window()
        if record is None:
            return
        tree_model = self.tree.model()
        for row in range(tree_model.rowCount()):
            idx = tree_model.index(row, 0)
            if tree_model.data(idx, ItemDataRole.LOG_RECORD) is record:
                self.tree.selectionModel().select(
                    idx,
                    Qt.QItemSelectionModel.ClearAndSelect | Qt.QItemSelectionModel.Rows,
                )
                self.tree.scrollTo(idx, Qt.QAbstractItemView.PositionAtCenter)
                return

    def _replace_model_with_custom(self):
        """Replace the standard LogModel with our CustomLogModel."""
        # Create our custom model
        custom_model = DocumentedLogModel()
        # Retitle the base 'Task' column to 'Throughline' (its contents are the
        # gentletask task-name chain; see DocumentedLogModel._get_column_text).
        titles = list(LogColumns.TITLES)
        titles[LogColumns.TASK] = 'Throughline'
        custom_model.setHorizontalHeaderLabels(titles)

        # Replace the model in the proxy
        if USE_CHAINED_FILTERING:
            # For chained filtering, use the new set_source_model method
            self.proxy_model.set_source_model(custom_model)
            # Update the tree view to point to the (potentially new) final model
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

    def _recordAtIndex(self, index):
        """Return the LogRecord for the top-level row containing *index*, or None.

        Child rows are detail items belonging to a record, so walk up to the row that
        actually carries one (mirroring the base viewer's clipboard handler).
        """
        if not index.isValid():
            return None
        while index.parent().isValid():
            index = index.parent()
        source = self.map_index_to_model(index)
        item = self.model.item(source.row(), 0)
        if item is None:
            return None
        return item.data(ItemDataRole.LOG_RECORD)

    def _logTailForIndex(self, index, count=LOG_TAIL_COUNT):
        """Return up to *count* records immediately preceding the row at *index*."""
        if not index.isValid():
            return []
        while index.parent().isValid():
            index = index.parent()
        row = self.map_index_to_model(index).row()
        tail = []
        for r in range(max(0, row - count), row):
            item = self.model.item(r, 0)
            if item is None:
                continue
            record = item.data(ItemDataRole.LOG_RECORD)
            if record is not None:
                tail.append(record)
        return tail

    def _build_row_context_menu(self, index):
        """Override of the base's extension point: append Debug with Claude to the inherited menu."""
        menu = super()._build_row_context_menu(index)

        if self._recordAtIndex(index) is not None:
            claude_action = Qt.QAction("Debug with Claude", self)
            claude_action.selectedIndex = index
            claude_action.triggered.connect(self._debugRowWithClaude)
            menu.addAction(claude_action)

        return menu

    def _debugRowWithClaude(self):
        index = self.sender().selectedIndex
        record = self._recordAtIndex(index)
        if record is None:
            return
        from acq4.util import claude_debug

        claude_debug.debugRecordWithClaude(
            record,
            log_tail=self._logTailForIndex(index),
            confirm=lambda: confirmTeleproxServer(self),
        )
