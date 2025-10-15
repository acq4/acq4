"""Tools module for discovering and running scripts from the tools/ directory."""

import argparse
import ast
import importlib.util
import inspect
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import click
import pyqtgraph as pg
from acq4.modules.Module import Module
from acq4.util import Qt


class OptionalSpinBox(Qt.QWidget):
    """A spinbox that can be in an 'unset' state for optional arguments."""

    def __init__(self, int_type=True):
        super().__init__()
        self.int_type = int_type

        layout = Qt.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.checkbox = Qt.QCheckBox("Set value:")
        self.spinbox = pg.SpinBox(value=0, int=int_type, decimals=0 if int_type else 6)
        self.spinbox.setEnabled(False)

        self.checkbox.toggled.connect(self.spinbox.setEnabled)

        layout.addWidget(self.checkbox)
        layout.addWidget(self.spinbox)

    def value(self):
        """Return the value, or None if not set."""
        if self.checkbox.isChecked():
            return self.spinbox.value()
        return None


class Tools(Module):
    """Module for discovering and running ACQ4 tools scripts."""

    moduleDisplayName = "Tools"
    moduleCategory = "Utilities"

    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self.manager = manager
        self.tools_dir = Path(__file__).parent.parent.parent / "tools"
        self.discovered_scripts = {}

        self._setupUI()
        # Start script discovery in background
        Qt.QTimer.singleShot(100, self._discover_scripts)

    def _setupUI(self):
        """Initialize the user interface."""
        self.win = Qt.QMainWindow()
        self.win.setWindowTitle('ACQ4 Tools')
        self.win.resize(800, 600)

        # Main widget and layout
        central_widget = Qt.QWidget()
        self.win.setCentralWidget(central_widget)
        layout = Qt.QVBoxLayout(central_widget)

        # Scripts list
        list_label = Qt.QLabel("Available Scripts:")
        layout.addWidget(list_label)

        self.script_list = Qt.QListWidget()
        self.script_list.itemSelectionChanged.connect(self._on_script_selected)
        layout.addWidget(self.script_list)

        # Script info area
        info_label = Qt.QLabel("Script Information:")
        layout.addWidget(info_label)

        self.info_text = Qt.QTextEdit()
        self.info_text.setMaximumHeight(150)
        self.info_text.setReadOnly(True)
        layout.addWidget(self.info_text)

        # Arguments area
        args_label = Qt.QLabel("Arguments:")
        layout.addWidget(args_label)

        # Scroll area for arguments
        scroll_area = Qt.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMaximumHeight(200)

        self.args_widget = Qt.QWidget()
        self.args_layout = Qt.QVBoxLayout(self.args_widget)
        scroll_area.setWidget(self.args_widget)
        layout.addWidget(scroll_area)

        # Daemon checkbox and run button
        run_container = Qt.QWidget()
        run_layout = Qt.QHBoxLayout(run_container)
        run_layout.setContentsMargins(0, 0, 0, 0)

        self.daemon_checkbox = Qt.QCheckBox("Run as daemon (continues after ACQ4 quits)")
        self.daemon_checkbox.setChecked(True)
        run_layout.addWidget(self.daemon_checkbox)

        run_layout.addStretch()  # Push run button to the right

        self.run_button = Qt.QPushButton("Run Script")
        self.run_button.clicked.connect(self._run_script)
        self.run_button.setEnabled(False)
        run_layout.addWidget(self.run_button)

        layout.addWidget(run_container)

        # Output area
        output_label = Qt.QLabel("Output:")
        layout.addWidget(output_label)

        self.output_text = Qt.QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setFont(Qt.QFont("Courier"))
        layout.addWidget(self.output_text)

        self.win.show()

    def _discover_scripts(self):
        """Discover all Python scripts in the tools directory."""
        if not self.tools_dir.exists():
            self.output_text.append(f"Tools directory not found: {self.tools_dir}")
            return

        self.output_text.append("Discovering scripts...")
        Qt.QApplication.processEvents()

        all_scripts = []

        # Collect all script paths first
        for script_path in self.tools_dir.glob("*.py"):
            if not script_path.name.startswith("__"):
                all_scripts.append((script_path.stem, script_path))

        # Also discover subdirectories with scripts
        for subdir in self.tools_dir.iterdir():
            if subdir.is_dir() and subdir.name != "requirements":
                for script_path in subdir.glob("*.py"):
                    if not script_path.name.startswith("__"):
                        key = f"{subdir.name}/{script_path.stem}"
                        all_scripts.append((key, script_path))

        # Process scripts one by one with event processing
        for i, (key, script_path) in enumerate(all_scripts):
            self.output_text.append(f"Analyzing {key}...")
            Qt.QApplication.processEvents()

            try:
                script_info = self._analyze_script(script_path)
                if script_info:
                    self.discovered_scripts[key] = script_info
                    self.script_list.addItem(key)
                    self.output_text.append(f"✓ {key} - Found {len(script_info['args'])} arguments")
                else:
                    self.output_text.append(f"✗ {key} - No parser detected")
            except Exception as e:
                self.output_text.append(f"✗ {key} - Error: {e}")

            Qt.QApplication.processEvents()

        self.output_text.append(f"\nDiscovery complete. Found {len(self.discovered_scripts)} scripts.")

    def _analyze_script(self, script_path: Path) -> Optional[Dict[str, Any]]:
        """Analyze a script to extract documentation and argument information."""
        try:
            with open(script_path, 'r', encoding='utf-8') as f:
                source = f.read()

            # Parse the AST to get docstrings
            tree = ast.parse(source)

            # Get module docstring
            docstring = ast.get_docstring(tree) or "No description available."

            script_info = {
                'path': script_path,
                'docstring': docstring,
                'args': [],
                'parser_type': None
            }

            # Try to detect argument parser type and extract arguments
            if 'argparse' in source:
                script_info['parser_type'] = 'argparse'
                script_info['args'] = self._extract_argparse_args(script_path)
            elif 'click' in source:
                script_info['parser_type'] = 'click'
                script_info['args'] = self._extract_click_args(script_path)

            return script_info

        except Exception as e:
            print(f"Error analyzing {script_path}: {e}")
            return None

    def _extract_argparse_args(self, script_path: Path) -> List[Dict[str, Any]]:
        """Extract argument information from argparse-based scripts."""
        args = []
        try:
            # Use subprocess to get help text - safer than importing
            result = subprocess.run(
                ['python', str(script_path), '--help'],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(self.tools_dir.parent),  # Run from project root
                env={**os.environ, 'PYTHONPATH': str(self.tools_dir.parent)}
            )

            if result.returncode == 0:
                args = self._parse_argparse_help(result.stdout)
                if not args:
                    # Help parsing failed, try source parsing
                    args = self._parse_source_for_args(script_path)
            else:
                # Help failed, fall back to source parsing
                # Try parsing the source code directly
                args = self._parse_source_for_args(script_path)

        except Exception as e:
            print(f"Error extracting argparse args from {script_path}: {e}")
            # Fallback to source parsing
            try:
                args = self._parse_source_for_args(script_path)
            except:
                pass

        return args

    def _parse_source_for_args(self, script_path: Path) -> List[Dict[str, Any]]:
        """Parse script source code to extract argument definitions."""
        args = []
        try:
            with open(script_path, 'r') as f:
                source = f.read()

            import re

            # Check if we have add_argument calls at all
            if 'add_argument' not in source:
                return args

            # Look for add_argument calls with more flexible matching
            lines = source.split('\n')
            in_add_argument = False
            current_arg = None

            for line_num, line in enumerate(lines):
                line = line.strip()

                # Start of add_argument call
                if 'add_argument' in line:
                    in_add_argument = True
                    current_arg = {'line_start': line_num}

                    # Try to extract argument name from this line
                    arg_match = re.search(r"add_argument\s*\(\s*['\"]([^'\"]*)['\"]", line)
                    if arg_match:
                        arg_name = arg_match.group(1)
                        current_arg['name'] = arg_name.lstrip('-')
                        current_arg['is_positional'] = not arg_name.startswith('-')

                if in_add_argument and current_arg:
                    # Extract help text
                    help_match = re.search(r"help\s*=\s*['\"]([^'\"]*)['\"]", line)
                    if help_match:
                        current_arg['description'] = help_match.group(1)

                    # Extract type
                    type_match = re.search(r"type\s*=\s*(\w+)", line)
                    if type_match:
                        current_arg['type'] = type_match.group(1)

                    # Extract default
                    default_match = re.search(r"default\s*=\s*([^,)]+)", line)
                    if default_match:
                        current_arg['default'] = default_match.group(1).strip()

                    # Check for required
                    if 'required=True' in line:
                        current_arg['required'] = True

                    # End of add_argument call
                    if ')' in line:
                        in_add_argument = False

                        # Finalize the argument
                        if 'name' in current_arg and current_arg['name']:
                            final_arg = {
                                'name': current_arg['name'],
                                'description': current_arg.get('description', 'No description'),
                                'type': current_arg.get('type', 'str'),
                                'required': current_arg.get('required', False),
                                'default': current_arg.get('default', None),
                                'is_positional': current_arg.get('is_positional', False)
                            }
                            args.append(final_arg)

                        current_arg = None

        except Exception as e:
            print(f"Error parsing source for {script_path}: {e}")

        return args

    def _parse_argparse_help(self, help_text: str) -> List[Dict[str, Any]]:
        """Parse argparse help text to extract argument information."""
        args = []
        lines = help_text.split('\n')

        in_options = False
        in_positional = False
        current_arg = None

        for line in lines:
            line = line.strip()

            if line.startswith('optional arguments:') or line.startswith('options:'):
                in_options = True
                in_positional = False
                continue

            if line.startswith('positional arguments:'):
                in_options = True
                in_positional = True
                continue

            if in_options and (line.startswith('  -') or (in_positional and line.startswith('  '))):
                # New argument (either optional with - or positional with indent)
                if current_arg:
                    args.append(current_arg)

                parts = line.split(None, 1)
                if len(parts) >= 2:
                    arg_names = parts[0]
                    description = parts[1] if len(parts) > 1 else ""

                    if in_positional and not arg_names.startswith('-'):
                        # Positional argument
                        current_arg = {
                            'name': arg_names,
                            'description': description,
                            'type': 'str',  # Default
                            'required': True,
                            'default': None,
                            'is_positional': True
                        }
                    else:
                        # Optional argument with flags
                        names = [name.strip() for name in arg_names.split(',')]
                        long_name = None
                        short_name = None

                        for name in names:
                            if name.startswith('--'):
                                long_name = name[2:]
                            elif name.startswith('-'):
                                short_name = name[1:]

                        arg_name = long_name or short_name or arg_names

                        current_arg = {
                            'name': arg_name,
                            'short': short_name,
                            'long': long_name,
                            'description': description,
                            'type': 'str',  # Default
                            'required': False,
                            'default': None,
                            'is_positional': False
                        }

            elif in_options and current_arg and line and not line.startswith('  -'):
                # Continuation of description
                current_arg['description'] += ' ' + line

        if current_arg:
            args.append(current_arg)

        return args

    def _extract_click_args(self, script_path: Path) -> List[Dict[str, Any]]:
        """Extract argument information from click-based scripts."""
        args = []
        try:
            # For click, we need to inspect the decorated functions
            spec = importlib.util.spec_from_file_location("temp_module", script_path)
            if spec is None or spec.loader is None:
                return args

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Find click commands
            for name, obj in inspect.getmembers(module):
                if hasattr(obj, '__click_params__'):
                    # This is a click command
                    for param in obj.__click_params__:
                        arg_info = {
                            'name': param.name,
                            'description': param.help or "No description",
                            'type': str(param.type),
                            'required': param.required,
                            'default': param.default
                        }
                        args.append(arg_info)

        except Exception as e:
            print(f"Error extracting click args from {script_path}: {e}")

        return args

    def _on_script_selected(self):
        """Handle script selection."""
        current_item = self.script_list.currentItem()
        if current_item is None:
            return

        script_name = current_item.text()
        if script_name not in self.discovered_scripts:
            return

        script_info = self.discovered_scripts[script_name]

        # Update info text
        info_text = f"Description: {script_info['docstring']}\n"
        info_text += f"Path: {script_info['path']}"
        self.info_text.setPlainText(info_text)

        # Clear previous argument widgets
        for i in reversed(range(self.args_layout.count())):
            child = self.args_layout.takeAt(i)
            if child.widget():
                child.widget().deleteLater()

        # Create argument input widgets
        self.arg_widgets = {}
        for arg in script_info['args']:
            self._create_arg_widget(arg)

        self.run_button.setEnabled(True)

    def _create_arg_widget(self, arg: Dict[str, Any]):
        """Create a widget for entering an argument value."""
        container = Qt.QWidget()
        layout = Qt.QHBoxLayout(container)

        # Argument label
        label_text = arg['name']
        if arg.get('short'):
            label_text += f" (-{arg['short']})"
        if arg.get('long'):
            label_text += f" (--{arg['long']})"

        label = Qt.QLabel(label_text + ":")
        label.setMinimumWidth(150)
        layout.addWidget(label)

        # Create appropriate input widget based on argument type
        arg_type = arg.get('type', 'str').lower()

        if 'bool' in arg_type or arg_type == 'store_true' or arg_type == 'store_false':
            widget = Qt.QCheckBox()
            if arg.get('default'):
                widget.setChecked(True)
        elif 'int' in arg_type:
            # For optional arguments with no default, use a special widget that can be "unset"
            if arg.get('default') is None and not arg.get('required', False):
                widget = OptionalSpinBox(int_type=True)
            else:
                try:
                    default_val = int(arg.get('default', 0)) if arg.get('default') else 0
                except (ValueError, TypeError):
                    default_val = 0
                widget = pg.SpinBox(value=default_val, int=True)
        elif 'float' in arg_type:
            # For optional arguments with no default, use a special widget that can be "unset"
            if arg.get('default') is None and not arg.get('required', False):
                widget = OptionalSpinBox(int_type=False)
            else:
                try:
                    default_val = float(arg.get('default', 0.0)) if arg.get('default') else 0.0
                except (ValueError, TypeError):
                    default_val = 0.0
                widget = pg.SpinBox(value=default_val, decimals=6)
        elif 'file' in arg.get('description', '').lower() or 'filename' in arg.get('name', '').lower():
            # File input with browse button
            file_widget = Qt.QWidget()
            file_layout = Qt.QHBoxLayout(file_widget)
            file_layout.setContentsMargins(0, 0, 0, 0)

            text_edit = Qt.QLineEdit()
            if arg.get('default'):
                text_edit.setText(str(arg['default']))
            file_layout.addWidget(text_edit)

            browse_btn = Qt.QPushButton("Browse...")
            browse_btn.clicked.connect(lambda checked, edit=text_edit: self._browse_file(edit))
            file_layout.addWidget(browse_btn)

            widget = file_widget
        else:
            # Default to text input
            widget = Qt.QLineEdit()
            if arg.get('default'):
                widget.setText(str(arg['default']))

        layout.addWidget(widget)

        # Help text
        if arg.get('description'):
            help_label = Qt.QLabel(f"({arg['description']})")
            help_label.setWordWrap(True)
            help_label.setStyleSheet("color: gray; font-style: italic;")
            layout.addWidget(help_label)

        self.args_layout.addWidget(container)
        self.arg_widgets[arg['name']] = widget

    def _browse_file(self, line_edit):
        """Open file browser dialog."""
        file_path, _ = Qt.QFileDialog.getOpenFileName(self.win, "Select File")
        if file_path:
            line_edit.setText(file_path)

    def _run_script(self):
        """Execute the selected script with the provided arguments."""
        current_item = self.script_list.currentItem()
        if current_item is None:
            return

        script_name = current_item.text()
        if script_name not in self.discovered_scripts:
            return

        script_info = self.discovered_scripts[script_name]
        script_path = script_info['path']

        # Build command line arguments
        cmd = ['python', str(script_path)]

        for arg in script_info['args']:
            widget = self.arg_widgets.get(arg['name'])
            if widget is None:
                continue

            # Get value from widget
            value = None
            is_flag = False

            if isinstance(widget, Qt.QCheckBox):
                if widget.isChecked():
                    is_flag = True
            elif isinstance(widget, OptionalSpinBox):
                value = widget.value()  # Returns None if not set
            elif isinstance(widget, pg.SpinBox):
                value = widget.value()
            elif isinstance(widget, Qt.QLineEdit):
                value = widget.text().strip()
            elif hasattr(widget, 'layout'):  # File widget
                line_edit = widget.layout().itemAt(0).widget()
                if isinstance(line_edit, Qt.QLineEdit):
                    value = line_edit.text().strip()

            # Add argument to command
            if is_flag:
                # Boolean flag argument
                cmd.append(f"--{arg['name']}")
            elif value is not None and value != '' and str(value).lower() != 'none':
                if arg.get('is_positional', False):
                    # Positional argument - just add the value
                    cmd.append(str(value))
                else:
                    # Optional argument - use dashes in name for long form
                    arg_flag = f"--{arg['name'].replace('_', '-')}"
                    cmd.extend([arg_flag, str(value)])
            # If no value provided and it's not required, skip it

        # Check if daemon mode is enabled
        is_daemon = self.daemon_checkbox.isChecked()

        if is_daemon:
            # Run in daemon mode - detached from ACQ4
            self.output_text.append(f"Running as daemon: {' '.join(cmd)}\n")
            self._start_daemon_process(cmd)
        else:
            # Run the script asynchronously
            self.output_text.append(f"Running: {' '.join(cmd)}\n")
            self._start_async_process(cmd)

    def _start_daemon_process(self, cmd):
        """Start a subprocess in daemon mode that persists after ACQ4 exits."""
        try:
            system = platform.system().lower()

            if system == 'windows':
                # On Windows, use subprocess with DETACHED_PROCESS to detach from parent
                import subprocess
                DETACHED_PROCESS = 0x00000008
                process = subprocess.Popen(
                    cmd,
                    cwd=str(self.tools_dir.parent),
                    env={**os.environ, 'PYTHONPATH': str(self.tools_dir.parent)},
                    creationflags=DETACHED_PROCESS,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL
                )
                self.output_text.append(f"Daemon process started with PID: {process.pid}\n")

            else:
                # On Unix-like systems (Linux, macOS), use os.fork() for proper daemonization
                if hasattr(os, 'fork'):
                    pid = os.fork()
                    if pid == 0:
                        # Child process - daemonize and exec
                        try:
                            # Second fork to ensure we're not a session leader
                            if os.fork() > 0:
                                os._exit(0)
                        except OSError:
                            os._exit(1)

                        # Decouple from parent environment
                        os.chdir(str(self.tools_dir.parent))
                        os.setsid()
                        os.umask(0)

                        # Redirect standard file descriptors to devnull
                        with open('/dev/null', 'r') as devnull_in, \
                             open('/dev/null', 'w') as devnull_out, \
                             open('/dev/null', 'w') as devnull_err:

                            os.dup2(devnull_in.fileno(), sys.stdin.fileno())
                            os.dup2(devnull_out.fileno(), sys.stdout.fileno())
                            os.dup2(devnull_err.fileno(), sys.stderr.fileno())

                        # Set environment and execute the command
                        env = os.environ.copy()
                        env['PYTHONPATH'] = str(self.tools_dir.parent)
                        os.execvpe(cmd[0], cmd, env)

                    elif pid > 0:
                        # Parent process - wait for first child to exit
                        os.waitpid(pid, 0)
                        self.output_text.append(f"Daemon process forked successfully\n")
                    else:
                        raise OSError("Fork failed")

                else:
                    # Fallback for systems without fork (should not happen on Linux/macOS)
                    process = subprocess.Popen(
                        cmd,
                        cwd=str(self.tools_dir.parent),
                        env={**os.environ, 'PYTHONPATH': str(self.tools_dir.parent)},
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        stdin=subprocess.DEVNULL
                    )
                    self.output_text.append(f"Background process started with PID: {process.pid}\n")

        except Exception as e:
            self.output_text.append(f"Error starting daemon process: {e}\n")
            # Fallback to regular async process
            self._start_async_process(cmd)

    def _start_async_process(self, cmd):
        """Start a subprocess asynchronously using QProcess."""
        # Create a new process for each script (allows multiple concurrent runs)
        process = Qt.QProcess(self)
        process.finished.connect(lambda exit_code, exit_status: self._on_process_finished(exit_code, exit_status, process))
        process.readyReadStandardOutput.connect(lambda: self._on_stdout_ready(process))
        process.readyReadStandardError.connect(lambda: self._on_stderr_ready(process))

        # Set environment
        env = Qt.QProcessEnvironment.systemEnvironment()
        env.insert('PYTHONPATH', str(self.tools_dir.parent))
        process.setProcessEnvironment(env)

        # Set working directory
        process.setWorkingDirectory(str(self.tools_dir.parent))

        # Start the process
        program = cmd[0]
        arguments = cmd[1:]
        process.start(program, arguments)

        if not process.waitForStarted(3000):  # 3 second timeout
            self.output_text.append("Failed to start process!\n")

    def _on_stdout_ready(self, process):
        """Handle stdout data from the running process."""
        data = process.readAllStandardOutput()
        text = bytes(data).decode('utf-8', errors='replace')
        if text.strip():
            self.output_text.append(text)

    def _on_stderr_ready(self, process):
        """Handle stderr data from the running process."""
        data = process.readAllStandardError()
        text = bytes(data).decode('utf-8', errors='replace')
        if text.strip():
            self.output_text.append("STDERR:")
            self.output_text.append(text)

    def _on_process_finished(self, exit_code, exit_status, process):
        """Handle process completion."""
        if exit_code == 0:
            self.output_text.append("Script completed successfully.\n")
        else:
            self.output_text.append(f"Script exited with code {exit_code}\n")

        # Clean up the process
        process.deleteLater()

    def quit(self):
        """Clean up when module is closed."""
        Module.quit(self)