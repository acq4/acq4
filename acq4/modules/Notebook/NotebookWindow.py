"""
NotebookWindow.py - Main UI window for the Notebook module
Copyright 2025
Distributed under MIT/X11 license. See license.txt for more information.
"""

import os
import subprocess
import json
import tempfile
import webbrowser
from pathlib import Path

import pyqtgraph as pg
from acq4.util import Qt
from acq4.util.DataManager import getHandle


# Try to import QWebEngineView for embedded web display
try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    WEBENGINE_AVAILABLE = True
except ImportError:
    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        WEBENGINE_AVAILABLE = True
    except ImportError:
        WEBENGINE_AVAILABLE = False
        QWebEngineView = None


class NotebookWindow(Qt.QMainWindow):
    """Main window for the Notebook module.

    Provides interface for creating, viewing, and managing Jupyter notebooks
    within ACQ4, with integration to the Data Manager.
    """

    def __init__(self, module, config):
        """Initialize the Notebook window.

        Parameters
        ----------
        module : Notebook
            Parent Notebook module
        config : dict
            Configuration dictionary
        """
        Qt.QMainWindow.__init__(self)
        self.module = module
        self.config = config
        self.hasQuit = False
        self.currentNotebook = None
        self.voilaProcess = None
        self.voilaPort = None

        self.setWindowTitle("Notebook")
        self.resize(1000, 700)

        # Create central widget with splitter layout
        self.centralWidget = Qt.QWidget()
        self.setCentralWidget(self.centralWidget)
        self.layout = Qt.QVBoxLayout(self.centralWidget)

        # Create toolbar
        self._createToolbar()

        # Create splitter for file browser and content area
        self.splitter = Qt.QSplitter(Qt.Qt.Horizontal)
        self.layout.addWidget(self.splitter)

        # Left panel: File browser
        self._createFileBrowser()

        # Right panel: Notebook viewer
        self._createNotebookViewer()

        # Status bar
        self.statusBar = Qt.QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready")

        # Load initial state
        self._loadState()
        self._refreshFileList()

        self.show()

    def _createToolbar(self):
        """Create the toolbar with control buttons."""
        toolbar = Qt.QToolBar("Notebook Controls")
        self.addToolBar(toolbar)

        # New notebook button
        newBtn = Qt.QPushButton("New Notebook")
        newBtn.clicked.connect(self._onNewNotebook)
        toolbar.addWidget(newBtn)

        toolbar.addSeparator()

        # Open in Jupyter button
        openJupyterBtn = Qt.QPushButton("Open in Jupyter")
        openJupyterBtn.clicked.connect(self._onOpenJupyter)
        toolbar.addWidget(openJupyterBtn)

        # Open in Voila button
        if WEBENGINE_AVAILABLE:
            openVoilaBtn = Qt.QPushButton("View with Voila")
            openVoilaBtn.clicked.connect(self._onOpenVoila)
            toolbar.addWidget(openVoilaBtn)

        # Open in browser button
        openBrowserBtn = Qt.QPushButton("Open in Browser")
        openBrowserBtn.clicked.connect(self._onOpenBrowser)
        toolbar.addWidget(openBrowserBtn)

        toolbar.addSeparator()

        # Refresh button
        refreshBtn = Qt.QPushButton("Refresh")
        refreshBtn.clicked.connect(self._refreshFileList)
        toolbar.addWidget(refreshBtn)

    def _createFileBrowser(self):
        """Create the file browser panel."""
        self.fileBrowserWidget = Qt.QWidget()
        layout = Qt.QVBoxLayout(self.fileBrowserWidget)

        # Title
        label = Qt.QLabel("Notebooks")
        label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        layout.addWidget(label)

        # Directory label
        self.dirLabel = Qt.QLabel("No directory selected")
        self.dirLabel.setWordWrap(True)
        self.dirLabel.setStyleSheet("font-size: 9pt; color: gray;")
        layout.addWidget(self.dirLabel)

        # File list
        self.fileList = Qt.QListWidget()
        self.fileList.itemDoubleClicked.connect(self._onFileDoubleClicked)
        self.fileList.itemSelectionChanged.connect(self._onFileSelectionChanged)
        layout.addWidget(self.fileList)

        # Add to splitter
        self.splitter.addWidget(self.fileBrowserWidget)
        self.splitter.setStretchFactor(0, 1)

    def _createNotebookViewer(self):
        """Create the notebook viewing panel."""
        self.viewerWidget = Qt.QWidget()
        layout = Qt.QVBoxLayout(self.viewerWidget)

        if WEBENGINE_AVAILABLE:
            # Use web engine view for embedded display
            self.webView = QWebEngineView()
            layout.addWidget(self.webView)

            # Load a placeholder page
            self._showPlaceholder()
        else:
            # Fallback: show instructions
            infoLabel = Qt.QLabel(
                "<h2>Notebook Viewer</h2>"
                "<p>QWebEngineView is not available in this Qt installation.</p>"
                "<p>Use the toolbar buttons to:</p>"
                "<ul>"
                "<li><b>Open in Jupyter</b> - Launch Jupyter Lab/Notebook</li>"
                "<li><b>Open in Browser</b> - Open notebook file in system browser</li>"
                "</ul>"
                "<p>To enable embedded viewing, install PyQtWebEngine:</p>"
                "<pre>pip install PyQtWebEngine</pre>"
            )
            infoLabel.setWordWrap(True)
            infoLabel.setAlignment(Qt.Qt.AlignTop | Qt.Qt.AlignLeft)
            infoLabel.setMargin(20)
            layout.addWidget(infoLabel)
            self.webView = None

        # Add to splitter
        self.splitter.addWidget(self.viewerWidget)
        self.splitter.setStretchFactor(1, 3)

    def _showPlaceholder(self):
        """Show placeholder HTML in the web view."""
        if self.webView is None:
            return

        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    padding: 40px;
                    background-color: #f5f5f5;
                }
                .container {
                    max-width: 600px;
                    margin: 0 auto;
                    background: white;
                    padding: 30px;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }
                h1 {
                    color: #333;
                }
                p {
                    color: #666;
                    line-height: 1.6;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Notebook Viewer</h1>
                <p>Select a notebook from the list on the left to view it.</p>
                <p>You can also create a new notebook or open existing ones in Jupyter or Voila.</p>
            </div>
        </body>
        </html>
        """
        self.webView.setHtml(html)

    def _refreshFileList(self):
        """Refresh the list of notebooks in the current directory."""
        self.fileList.clear()

        # Get current directory from Data Manager
        currentDir = self.module.getCurrentDir()
        if currentDir is None:
            self.dirLabel.setText("No directory selected in Data Manager")
            self.statusBar.showMessage("No directory selected")
            return

        try:
            dirPath = currentDir.name()
            self.dirLabel.setText(f"Directory: {dirPath}")

            # List all .ipynb files in the directory
            notebooks = []
            if os.path.exists(dirPath):
                for item in os.listdir(dirPath):
                    if item.endswith('.ipynb') and not item.startswith('.'):
                        notebooks.append(item)

            # Sort notebooks
            notebooks.sort()

            # Add to list widget
            for notebook in notebooks:
                item = Qt.QListWidgetItem(notebook)
                item.setData(Qt.Qt.UserRole, os.path.join(dirPath, notebook))
                self.fileList.addItem(item)

            self.statusBar.showMessage(f"Found {len(notebooks)} notebook(s)")

        except Exception as e:
            self.statusBar.showMessage(f"Error listing notebooks: {e}")
            print(f"Error in _refreshFileList: {e}")

    def _onFileDoubleClicked(self, item):
        """Handle double-click on a notebook file.

        Parameters
        ----------
        item : QListWidgetItem
            The clicked item
        """
        notebookPath = item.data(Qt.Qt.UserRole)
        self._openNotebookFile(notebookPath)

    def _onFileSelectionChanged(self):
        """Handle selection change in file list."""
        items = self.fileList.selectedItems()
        if items:
            notebookPath = items[0].data(Qt.Qt.UserRole)
            self.currentNotebook = notebookPath
            self.statusBar.showMessage(f"Selected: {os.path.basename(notebookPath)}")

    def _openNotebookFile(self, notebookPath):
        """Open a notebook file for viewing.

        Parameters
        ----------
        notebookPath : str
            Path to the notebook file
        """
        self.currentNotebook = notebookPath

        if self.webView:
            # For now, show basic info about the notebook
            try:
                with open(notebookPath, 'r', encoding='utf-8') as f:
                    nb_data = json.load(f)

                num_cells = len(nb_data.get('cells', []))
                title = nb_data.get('metadata', {}).get('title', 'Untitled')

                html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <style>
                        body {{
                            font-family: Arial, sans-serif;
                            padding: 40px;
                            background-color: #f5f5f5;
                        }}
                        .container {{
                            max-width: 600px;
                            margin: 0 auto;
                            background: white;
                            padding: 30px;
                            border-radius: 8px;
                            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                        }}
                        h1 {{
                            color: #333;
                        }}
                        .info {{
                            color: #666;
                            line-height: 1.6;
                        }}
                        .actions {{
                            margin-top: 20px;
                            padding-top: 20px;
                            border-top: 1px solid #ddd;
                        }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>{title}</h1>
                        <div class="info">
                            <p><strong>File:</strong> {os.path.basename(notebookPath)}</p>
                            <p><strong>Cells:</strong> {num_cells}</p>
                            <p><strong>Format:</strong> nbformat {nb_data.get('nbformat', 'unknown')}</p>
                        </div>
                        <div class="actions">
                            <p>Use the toolbar buttons to:</p>
                            <ul>
                                <li>Open in Jupyter for full editing</li>
                                <li>View with Voila for interactive display</li>
                                <li>Open in browser for external viewing</li>
                            </ul>
                        </div>
                    </div>
                </body>
                </html>
                """
                self.webView.setHtml(html)
                self.statusBar.showMessage(f"Loaded: {os.path.basename(notebookPath)}")

            except Exception as e:
                self.statusBar.showMessage(f"Error loading notebook: {e}")
                print(f"Error in _openNotebookFile: {e}")

    def _onNewNotebook(self):
        """Create a new notebook in the current directory."""
        currentDir = self.module.getCurrentDir()
        if currentDir is None:
            Qt.QMessageBox.warning(
                self, "No Directory",
                "Please select a directory in the Data Manager first."
            )
            return

        # Get notebook name from user
        name, ok = Qt.QInputDialog.getText(
            self, "New Notebook",
            "Enter notebook name:",
            Qt.QLineEdit.Normal,
            "untitled"
        )

        if not ok or not name:
            return

        # Ensure .ipynb extension
        if not name.endswith('.ipynb'):
            name += '.ipynb'

        try:
            # Create empty notebook structure
            from acq4.filetypes.NotebookFile import NotebookFile
            empty_notebook = NotebookFile.createEmptyNotebook(title=name)

            # Write to Data Manager
            fh = currentDir.writeFile(empty_notebook, name)

            self.statusBar.showMessage(f"Created: {name}")
            self._refreshFileList()

            # Select the new notebook
            for i in range(self.fileList.count()):
                item = self.fileList.item(i)
                if item.text() == name:
                    self.fileList.setCurrentItem(item)
                    break

        except Exception as e:
            Qt.QMessageBox.critical(
                self, "Error",
                f"Failed to create notebook: {e}"
            )
            print(f"Error in _onNewNotebook: {e}")

    def _onOpenJupyter(self):
        """Open the current notebook in Jupyter Lab or Notebook."""
        if self.currentNotebook is None:
            Qt.QMessageBox.warning(
                self, "No Notebook Selected",
                "Please select a notebook first."
            )
            return

        try:
            # Try Jupyter Lab first, fall back to Jupyter Notebook
            notebook_dir = os.path.dirname(self.currentNotebook)

            try:
                # Try jupyter lab
                subprocess.Popen(
                    ['jupyter', 'lab', self.currentNotebook],
                    cwd=notebook_dir
                )
                self.statusBar.showMessage("Launched Jupyter Lab")
            except FileNotFoundError:
                # Fall back to jupyter notebook
                subprocess.Popen(
                    ['jupyter', 'notebook', self.currentNotebook],
                    cwd=notebook_dir
                )
                self.statusBar.showMessage("Launched Jupyter Notebook")

        except Exception as e:
            Qt.QMessageBox.critical(
                self, "Error",
                f"Failed to launch Jupyter: {e}\n\n"
                "Make sure Jupyter is installed:\n"
                "pip install jupyterlab"
            )
            print(f"Error in _onOpenJupyter: {e}")

    def _onOpenVoila(self):
        """Open the current notebook with Voila in the embedded view."""
        if self.currentNotebook is None:
            Qt.QMessageBox.warning(
                self, "No Notebook Selected",
                "Please select a notebook first."
            )
            return

        if not WEBENGINE_AVAILABLE:
            Qt.QMessageBox.warning(
                self, "WebEngine Not Available",
                "QWebEngineView is not available. Please install PyQtWebEngine."
            )
            return

        try:
            # Stop existing Voila process if running
            self._stopVoila()

            # Start Voila server
            import socket

            # Find an available port
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', 0))
                s.listen(1)
                self.voilaPort = s.getsockname()[1]

            # Launch Voila
            self.voilaProcess = subprocess.Popen(
                [
                    'voila',
                    self.currentNotebook,
                    '--port', str(self.voilaPort),
                    '--no-browser'
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # Wait a moment for server to start
            Qt.QTimer.singleShot(2000, lambda: self._loadVoilaPage())

            self.statusBar.showMessage("Starting Voila server...")

        except FileNotFoundError:
            Qt.QMessageBox.critical(
                self, "Error",
                "Voila is not installed.\n\n"
                "Install with: pip install voila"
            )
        except Exception as e:
            Qt.QMessageBox.critical(
                self, "Error",
                f"Failed to launch Voila: {e}"
            )
            print(f"Error in _onOpenVoila: {e}")

    def _loadVoilaPage(self):
        """Load the Voila page in the web view."""
        if self.webView and self.voilaPort:
            url = f"http://localhost:{self.voilaPort}"
            self.webView.setUrl(Qt.QUrl(url))
            self.statusBar.showMessage(f"Viewing with Voila on port {self.voilaPort}")

    def _stopVoila(self):
        """Stop the Voila server if running."""
        if self.voilaProcess:
            try:
                self.voilaProcess.terminate()
                self.voilaProcess.wait(timeout=5)
            except:
                self.voilaProcess.kill()
            self.voilaProcess = None
            self.voilaPort = None

    def _onOpenBrowser(self):
        """Open the current notebook in the system browser."""
        if self.currentNotebook is None:
            Qt.QMessageBox.warning(
                self, "No Notebook Selected",
                "Please select a notebook first."
            )
            return

        try:
            # Open as file URL in browser (will render as JSON)
            file_url = Path(self.currentNotebook).as_uri()
            webbrowser.open(file_url)
            self.statusBar.showMessage("Opened in browser")

        except Exception as e:
            Qt.QMessageBox.critical(
                self, "Error",
                f"Failed to open in browser: {e}"
            )
            print(f"Error in _onOpenBrowser: {e}")

    def _loadState(self):
        """Load saved window state."""
        # Could load window geometry, splitter position, etc.
        pass

    def _saveState(self):
        """Save window state."""
        # Could save window geometry, splitter position, etc.
        pass

    def quit(self):
        """Clean up resources and close the window."""
        if self.hasQuit:
            return

        self.hasQuit = True
        self._stopVoila()
        self._saveState()
        self.close()
