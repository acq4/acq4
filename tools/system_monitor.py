# System resource monitoring utility that logs and plots CPU/memory usage over time
#Displays real-time graphs and top process lists with historical timeline selection

import argparse
import sys
import time
import json
import os
import ctypes
import psutil
import threading
import queue
import subprocess
import re
from datetime import datetime

import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets


class PsutilProcessCollector:
    def collect(self):
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                info = proc.info
                if info['cpu_percent'] is not None and info['memory_percent'] is not None:
                    processes.append({
                        'pid': info['pid'],
                        'name': info['name'],
                        'cpu_percent': info['cpu_percent'],
                        'memory_percent': info['memory_percent'],
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return processes


class WindowsProcessCollector(PsutilProcessCollector):
    """Windows process collector backed by NtQuerySystemInformation."""

    def __init__(self):
        self._nt_query_system_information = None
        self._win_spi_struct = None
        self._win_query_buffer_size = 512 * 1024
        self._win_prev_snapshot_time = None
        self._win_prev_proc_cpu_times = {}
        self._win_cpu_count = max(psutil.cpu_count(logical=True) or 1, 1)
        self._win_total_memory_bytes = float(psutil.virtual_memory().total or 1.0)
        self._win_status_info_length_mismatch = -1073741820  # 0xC0000004
        self._win_system_process_information_class = 5
        self._init_windows_backend()

    def _init_windows_backend(self):
        try:
            from ctypes import wintypes
        except Exception:
            return

        class _UNICODE_STRING(ctypes.Structure):
            _fields_ = [
                ('Length', wintypes.USHORT),
                ('MaximumLength', wintypes.USHORT),
                ('Buffer', wintypes.LPWSTR),
            ]

        class _SYSTEM_PROCESS_INFORMATION(ctypes.Structure):
            _fields_ = [
                ('NextEntryOffset', wintypes.ULONG),
                ('NumberOfThreads', wintypes.ULONG),
                ('WorkingSetPrivateSize', ctypes.c_longlong),
                ('HardFaultCount', wintypes.ULONG),
                ('NumberOfThreadsHighWatermark', wintypes.ULONG),
                ('CycleTime', ctypes.c_ulonglong),
                ('CreateTime', ctypes.c_longlong),
                ('UserTime', ctypes.c_longlong),
                ('KernelTime', ctypes.c_longlong),
                ('ImageName', _UNICODE_STRING),
                ('BasePriority', wintypes.LONG),
                ('UniqueProcessId', ctypes.c_void_p),
                ('InheritedFromUniqueProcessId', ctypes.c_void_p),
                ('HandleCount', wintypes.ULONG),
                ('SessionId', wintypes.ULONG),
                ('UniqueProcessKey', ctypes.c_void_p),
                ('PeakVirtualSize', ctypes.c_size_t),
                ('VirtualSize', ctypes.c_size_t),
                ('PageFaultCount', wintypes.ULONG),
                ('PeakWorkingSetSize', ctypes.c_size_t),
                ('WorkingSetSize', ctypes.c_size_t),
                ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
                ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                ('PagefileUsage', ctypes.c_size_t),
                ('PeakPagefileUsage', ctypes.c_size_t),
                ('PrivatePageCount', ctypes.c_size_t),
                ('ReadOperationCount', ctypes.c_longlong),
                ('WriteOperationCount', ctypes.c_longlong),
                ('OtherOperationCount', ctypes.c_longlong),
                ('ReadTransferCount', ctypes.c_longlong),
                ('WriteTransferCount', ctypes.c_longlong),
                ('OtherTransferCount', ctypes.c_longlong),
            ]

        try:
            ntdll = ctypes.WinDLL('ntdll')
            nt_query = ntdll.NtQuerySystemInformation
            nt_query.argtypes = [
                wintypes.ULONG,
                wintypes.PVOID,
                wintypes.ULONG,
                ctypes.POINTER(wintypes.ULONG),
            ]
            nt_query.restype = wintypes.LONG
            self._nt_query_system_information = nt_query
            self._win_spi_struct = _SYSTEM_PROCESS_INFORMATION
        except Exception:
            self._nt_query_system_information = None
            self._win_spi_struct = None

    def collect(self):
        processes = self._collect_windows()
        if processes is not None:
            return processes
        return super().collect()

    def _collect_windows(self):
        if self._nt_query_system_information is None:
            return None

        from ctypes import wintypes

        buffer_size = self._win_query_buffer_size
        return_length = wintypes.ULONG()

        while True:
            buffer = ctypes.create_string_buffer(buffer_size)
            status = self._nt_query_system_information(
                self._win_system_process_information_class,
                buffer,
                buffer_size,
                ctypes.byref(return_length),
            )
            if status == 0:
                break
            if status != self._win_status_info_length_mismatch:
                return None
            buffer_size = max(buffer_size * 2, int(return_length.value) + 64 * 1024)

        self._win_query_buffer_size = buffer_size

        now = time.monotonic()
        interval = None
        if self._win_prev_snapshot_time is not None:
            interval = now - self._win_prev_snapshot_time
        self._win_prev_snapshot_time = now

        total_memory = self._win_total_memory_bytes or 1.0
        cpu_count = float(self._win_cpu_count or 1)
        ticks_per_second = 10_000_000.0  # 100ns units

        processes = []
        current_cpu_times = {}
        offset = 0

        while True:
            spi = self._win_spi_struct.from_buffer_copy(buffer, offset)
            pid = int(spi.UniqueProcessId or 0)

            name = ''
            if spi.ImageName.Buffer and spi.ImageName.Length:
                try:
                    name = ctypes.wstring_at(spi.ImageName.Buffer, spi.ImageName.Length // 2)
                except Exception:
                    name = ''
            if not name:
                name = 'System Idle Process' if pid == 0 else ('System' if pid == 4 else f'PID {pid}')

            total_proc_time = int(spi.UserTime + spi.KernelTime)
            current_cpu_times[pid] = total_proc_time

            cpu_percent = 0.0
            previous_time = self._win_prev_proc_cpu_times.get(pid)
            if interval and interval > 0 and previous_time is not None:
                delta = total_proc_time - previous_time
                if delta > 0:
                    cpu_percent = (delta / (interval * ticks_per_second * cpu_count)) * 100.0

            memory_percent = (float(spi.WorkingSetSize) / total_memory) * 100.0
            processes.append({
                'pid': pid,
                'name': name,
                'cpu_percent': cpu_percent,
                'memory_percent': memory_percent,
            })

            if spi.NextEntryOffset == 0:
                break
            offset += spi.NextEntryOffset

        self._win_prev_proc_cpu_times = current_cpu_times
        return processes


class PowerShellProcessCollector(PsutilProcessCollector):
    """Windows collector that runs PowerShell and parses Format-List output."""

    _FIELD_RE = re.compile(r'^([A-Za-z][A-Za-z0-9_]*)\s*:\s?(.*)$')

    def __init__(self, top_n=20):
        self._top_n = max(int(top_n), 1)
        self._cpu_count = max(psutil.cpu_count(logical=True) or 1, 1)
        self._total_memory_bytes = float(psutil.virtual_memory().total or 1.0)
        self._previous_sample_time = None
        self._previous_cpu_seconds = {}
        self._powershell = self._resolve_powershell_executable()

    def collect(self):
        if os.name != 'nt' or not self._powershell:
            return super().collect()

        output = self._run_query()
        if not output:
            return super().collect()

        records = self._parse_format_list(output)
        if not records:
            return super().collect()

        now = time.monotonic()
        interval = None
        if self._previous_sample_time is not None:
            interval = now - self._previous_sample_time
        self._previous_sample_time = now

        processes = []
        current_cpu_seconds = {}
        for record in records:
            pid = self._to_int(record.get('Id'))
            if pid is None:
                continue

            name = (record.get('Name') or '').strip() or f'PID {pid}'
            cpu_seconds = self._to_float(record.get('CPU'))
            if cpu_seconds is None:
                cpu_seconds = 0.0
            current_cpu_seconds[pid] = cpu_seconds

            cpu_percent = 0.0
            previous = self._previous_cpu_seconds.get(pid)
            if interval and interval > 0 and previous is not None:
                delta = cpu_seconds - previous
                if delta > 0:
                    cpu_percent = (delta / (interval * self._cpu_count)) * 100.0

            ws_bytes = self._to_float(record.get('WS'))
            if ws_bytes is None:
                ws_bytes = 0.0
            memory_percent = (ws_bytes / self._total_memory_bytes) * 100.0

            cmdline = (record.get('FullCommand') or '').strip()
            if not cmdline:
                cmdline = name

            processes.append({
                'pid': pid,
                'name': name,
                'cpu_percent': cpu_percent,
                'memory_percent': memory_percent,
                'cmdline': cmdline,
            })

        self._previous_cpu_seconds = current_cpu_seconds
        return processes if processes else super().collect()

    def _resolve_powershell_executable(self):
        system_root = os.environ.get('SystemRoot', r'C:\Windows')
        candidates = [
            'powershell.exe',
            os.path.join(system_root, 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe'),
        ]
        for candidate in candidates:
            if os.path.isabs(candidate):
                if os.path.exists(candidate):
                    return candidate
            else:
                return candidate
        return None

    def _run_query(self):
        script = (
            f"$cpu = Get-Process | Sort-Object CPU -Descending | Select-Object -First {self._top_n}; "
            f"$mem = Get-Process | Sort-Object WS -Descending | Select-Object -First {self._top_n}; "
            "$top = @($cpu + $mem | Sort-Object Id -Unique); "
            "$top | Select-Object Name, CPU, Id, WS, "
            "@{Name='FullCommand'; Expression={(Get-CimInstance Win32_Process -Filter \"ProcessId = $($_.Id)\" -ErrorAction SilentlyContinue).CommandLine}} | "
            "Format-List"
        )
        try:
            completed = subprocess.run(
                [self._powershell, '-NoProfile', '-Command', script],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except Exception:
            return None
        if completed.returncode != 0:
            return None
        
        return completed.stdout

    def _parse_format_list(self, text):
        records = []
        current = {}
        last_field = None

        for line in text.splitlines():
            if not line.strip():
                if current:
                    records.append(current)
                    current = {}
                    last_field = None
                continue

            match = self._FIELD_RE.match(line)
            if match:
                key, value = match.group(1), match.group(2)
                current[key] = value
                last_field = key
                continue

            if last_field and line.startswith(' '):
                continuation = line.strip()
                if continuation:
                    current[last_field] = f"{current[last_field]} {continuation}".strip()

        if current:
            records.append(current)

        # De-dupe by PID in case a process appears in both CPU and memory top lists.
        by_pid = {}
        for record in records:
            pid = self._to_int(record.get('Id'))
            if pid is not None:
                by_pid[pid] = record
        return list(by_pid.values())

    @staticmethod
    def _to_int(value):
        if value is None:
            return None
        try:
            return int(str(value).strip())
        except Exception:
            return None

    @staticmethod
    def _to_float(value):
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            return float(text)
        except Exception:
            return None


def create_process_collector():
    if os.name == 'nt':
        return PowerShellProcessCollector()
        # return WindowsProcessCollector()
    else:
        return PsutilProcessCollector()


class SystemMonitor(QtWidgets.QWidget):
    def __init__(self, poll_interval=20, load_file=None):
        super().__init__()
        self.poll_interval = poll_interval
        self.is_polling = False
        self.loaded_from_file = load_file is not None
        self.current_log_file = None
        self._cmdline_cache = {}
        self._process_collector = create_process_collector()
        
        # Data storage
        self.timestamps = []
        self.cpu_data = []
        self.memory_data = []
        self.process_history = []  # List of dicts with timestamp and process data
        
        self.setup_ui()
        
        # Set up polling thread and gui update timer
        self.new_process_data = queue.Queue()
        self.poll_thread = None
        self.polling_enabled = False
        self.update_timer = QtCore.QTimer()
        self.update_timer.timeout.connect(self.update_process_data)
        self.update_timer.start(1000)
        
        # Load data if file provided, otherwise create new log file and start polling  
        if load_file:
            self.load_data(load_file)
            self.stop_polling()  # Sets correct button text for non-polling state
        else:
            self.create_new_log_file()
            self.start_polling()

    def setup_ui(self):
        """Set up the user interface"""
        self.setWindowTitle('System Resource Monitor')
        self.setGeometry(100, 100, 1200, 600)
        
        # Main layout with splitter
        main_layout = QtWidgets.QHBoxLayout()
        self.setLayout(main_layout)
        
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        main_layout.addWidget(splitter)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Left side - plot widget
        plot_widget = QtWidgets.QWidget()
        plot_layout = QtWidgets.QVBoxLayout()
        plot_layout.setContentsMargins(0, 0, 0, 0)
        plot_widget.setLayout(plot_layout)
        splitter.addWidget(plot_widget)
        
        # Plot widget
        self.plot_widget = pg.PlotWidget(title="System Resource Usage")
        self.plot_widget.setLabel('left', 'Usage %')
        self.plot_widget.setLabel('bottom', 'Time')
        self.plot_widget.showGrid(True, True)
        self.plot_widget.setYRange(0, 100)
        
        # Add legend first
        self.plot_widget.addLegend(offset=(10, 10))
        
        # Plot curves - legend must exist before curves are added
        self.cpu_curve = self.plot_widget.plot(pen=pg.mkPen(color='red', width=2), name='CPU %')
        self.memory_curve = self.plot_widget.plot(pen=pg.mkPen(color='blue', width=2), name='Memory %')
        
        # Timeline selection line
        self.timeline_line = pg.InfiniteLine(angle=90, movable=True, pen=pg.mkPen(color='green', width=2))
        self.timeline_line.sigPositionChanged.connect(self.on_timeline_changed)
        self.plot_widget.addItem(self.timeline_line)
        self.timeline_line.setVisible(False)  # Hide until we have data
        
        plot_layout.addWidget(self.plot_widget)
        
        # Control buttons
        button_layout = QtWidgets.QHBoxLayout()
        self.start_stop_btn = QtWidgets.QPushButton('')  # Text will be set by start/stop methods
        self.start_stop_btn.clicked.connect(self.toggle_polling)
        button_layout.addWidget(self.start_stop_btn)
        
        self.load_btn = QtWidgets.QPushButton('Load File')
        self.load_btn.clicked.connect(self.load_file_dialog)
        button_layout.addWidget(self.load_btn)
        
        # Poll interval control
        interval_label = QtWidgets.QLabel('Poll Interval:')
        button_layout.addWidget(interval_label)
        
        self.interval_spinbox = QtWidgets.QSpinBox()
        self.interval_spinbox.setRange(1, 300)  # 1 second to 5 minutes
        self.interval_spinbox.setSuffix('s')
        self.interval_spinbox.setValue(self.poll_interval)
        self.interval_spinbox.valueChanged.connect(self.on_interval_changed)
        button_layout.addWidget(self.interval_spinbox)
        button_layout.addStretch()
        
        plot_layout.addLayout(button_layout)
        
        # Right side - process tables widget
        tables_widget = QtWidgets.QWidget()
        tables_layout = QtWidgets.QVBoxLayout()
        tables_layout.setContentsMargins(0, 0, 0, 0)
        tables_widget.setLayout(tables_layout)
        splitter.addWidget(tables_widget)
        
        # Set splitter proportions (2:1 ratio)
        splitter.setSizes([500, 700])
        
        # CPU processes table
        cpu_label = QtWidgets.QLabel('Top 10 CPU Processes')
        tables_layout.addWidget(cpu_label)
        
        self.cpu_table = QtWidgets.QTableWidget(10, 3)
        self.cpu_table.setHorizontalHeaderLabels(['PID', 'CPU %', 'Command'])
        self.cpu_table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.cpu_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.cpu_table.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.cpu_table.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)

        tables_layout.addWidget(self.cpu_table)
        
        # Memory processes table  
        memory_label = QtWidgets.QLabel('Top 10 Memory Processes')
        tables_layout.addWidget(memory_label)
        
        self.memory_table = QtWidgets.QTableWidget(10, 3)
        self.memory_table.setHorizontalHeaderLabels(['PID', 'Mem %', 'Command'])
        self.memory_table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.memory_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.memory_table.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.memory_table.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
        tables_layout.addWidget(self.memory_table)
        
    def update_title(self):
        """Update window title with current log file"""
        base_title = 'System Resource Monitor'
        if self.current_log_file:
            filename = os.path.basename(self.current_log_file)
            self.setWindowTitle(f'{base_title} - {filename}')
        else:
            self.setWindowTitle(base_title)
            
    def create_new_log_file(self):
        """Create a new timestamped log file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_log_file = f"system_monitor_{timestamp}.json"
        self.update_title()
        
    def save_current_data(self):
        """Save current data to the log file"""
        if not self.current_log_file:
            return
            
        data = {
            'poll_interval': self.poll_interval,
            'timestamps': self.timestamps,
            'cpu_data': self.cpu_data,
            'memory_data': self.memory_data,
            'process_history': self.process_history
        }
        
        try:
            with open(self.current_log_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, 'Save Error', f'Failed to save data: {str(e)}')
            
    def load_data(self, filename):
        """Load data from a JSON file"""
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
                
            self.timestamps = data.get('timestamps', [])
            self.cpu_data = data.get('cpu_data', [])
            self.memory_data = data.get('memory_data', [])
            self.process_history = data.get('process_history', [])
            
            # Update displays
            if len(self.timestamps) > 0:
                self.update_plot()
                if self.process_history:
                    self.update_process_tables(self.process_history[-1]['processes'])
                    
                # Show timeline line
                if len(self.timestamps) > 1:
                    self.timeline_line.setVisible(True)
                    start_time = self.timestamps[0]
                    latest_time = (self.timestamps[-1] - start_time) / 60.0
                    self.timeline_line.setPos(latest_time)
                    
            self.current_log_file = filename
            self.update_title()
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Load Error', f'Failed to load file: {str(e)}')
            
    def load_file_dialog(self):
        """Open file dialog to load a saved log file"""
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Load System Monitor Log', '', 'JSON files (*.json);;All files (*.*)')
        
        if filename:
            self.load_data(filename)
            self.loaded_from_file = True
            
    def start_polling(self):
        """Start the polling timer and update button"""
        self.polling_enabled = True
        if self.poll_thread is None or not self.poll_thread.is_alive():
            self.poll_thread = threading.Thread(target=self.poll_system_resources, daemon=True)
            self.poll_thread.start()
        self.start_stop_btn.setText('Stop Polling')
        
    def stop_polling(self):
        """Stop the polling timer and update button"""
        self.polling_enabled = False
        if self.poll_thread and self.poll_thread.is_alive():
            self.poll_thread.join(timeout=5)  # Wait for thread to finish if it's running
        self.start_stop_btn.setText('Start Polling')
        self.save_current_data()
            
    def toggle_polling(self):
        """Start or stop the polling"""
        if self.polling_enabled:
            self.stop_polling()
        else:
            # If we loaded from file, ask user what to do
            if self.loaded_from_file and len(self.timestamps) > 0:
                filename = os.path.basename(self.current_log_file) if self.current_log_file else "loaded file"
                reply = QtWidgets.QMessageBox.question(
                    self, 'Start Polling',
                    f'Do you want to append to the loaded log file "{filename}"?\n\n'
                    'Click Yes to append new data, No to start a new log file.',
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Cancel)
                
                if reply == QtWidgets.QMessageBox.Cancel:
                    return
                elif reply == QtWidgets.QMessageBox.No:
                    # Start new file
                    self.create_new_log_file()
                    self.timestamps.clear()
                    self.cpu_data.clear()
                    self.memory_data.clear()
                    self.process_history.clear()
                    self.update_plot()
                    self.cpu_table.clearContents()
                    self.memory_table.clearContents()
                # If Yes (append), just continue with existing data
                
            self.start_polling()
            
    def poll_system_resources(self):
        """Poll system resources and update displays"""
        while True:
            # Get current timestamp
            timestamp = time.time()
            
            # Get CPU and memory usage
            cpu_percent = psutil.cpu_percent()
            memory_percent = psutil.virtual_memory().percent
            
            # Get process information
            processes = self._process_collector.collect()
                    
            # Store process data with timestamp
            self.new_process_data.put({
                'timestamp': timestamp,
                'cpu_percent': cpu_percent,
                'memory_percent': memory_percent,
                'processes': processes
            })

            # sleep until next interval
            sleep_time = timestamp + self.poll_interval - time.time()

            if sleep_time > 0:
                time.sleep(sleep_time)

    def update_process_data(self):
        if self.new_process_data.empty():
            return
        while not self.new_process_data.empty():
            result = self.new_process_data.get()
            self.process_history.append(result)
            self.timestamps.append(result['timestamp'])
            self.cpu_data.append(result['cpu_percent'])
            self.memory_data.append(result['memory_percent'])

        # Update displays
        self.update_plot()
        processes = self.process_history[-1]['processes']
        self.update_process_tables(processes)
        
        # Show timeline line if we have data and it's not visible yet
        if len(self.timestamps) > 1 and not self.timeline_line.isVisible():
            self.timeline_line.setVisible(True)
            
        # Always move timeline to latest data point on new updates
        if len(self.timestamps) > 0:
            start_time = self.timestamps[0]
            latest_time = (self.timestamps[-1] - start_time) / 60.0
            self.timeline_line.setPos(latest_time)
            
        # Auto-save data periodically
        self.save_current_data()

    def update_plot(self):
        """Update the plot with new data"""
        if len(self.timestamps) > 0:
            # Convert timestamps to relative time in minutes
            start_time = self.timestamps[0]
            relative_times = [(t - start_time) / 60.0 for t in self.timestamps]
            
            self.cpu_curve.setData(relative_times, self.cpu_data)
            self.memory_curve.setData(relative_times, self.memory_data)
            
    def update_process_tables(self, processes):
        """Update the process tables with current data"""
        # Sort by CPU usage
        cpu_processes = sorted(processes, key=lambda x: x['cpu_percent'], reverse=True)[:10]
        
        for i, proc in enumerate(cpu_processes):
            self._fill_process_cmdline(proc)
            self.cpu_table.setItem(i, 0, QtWidgets.QTableWidgetItem(str(proc['pid'])))
            self.cpu_table.setItem(i, 1, QtWidgets.QTableWidgetItem(f"{proc['cpu_percent']:.3f}"))
            self.cpu_table.setItem(i, 2, QtWidgets.QTableWidgetItem(proc['cmdline']))
            
        # Sort by memory usage
        memory_processes = sorted(processes, key=lambda x: x['memory_percent'], reverse=True)[:10]
        
        for i, proc in enumerate(memory_processes):
            self._fill_process_cmdline(proc)
            self.memory_table.setItem(i, 0, QtWidgets.QTableWidgetItem(str(proc['pid'])))
            self.memory_table.setItem(i, 1, QtWidgets.QTableWidgetItem(f"{proc['memory_percent']:.3f}"))
            self.memory_table.setItem(i, 2, QtWidgets.QTableWidgetItem(proc['cmdline']))

    def _fill_process_cmdline(self, proc):
        if 'cmdline' not in proc:
            pid = proc.get('pid')
            name = proc.get('name') or ''
            cached = self._cmdline_cache.get(pid)
            if cached and cached[0] == name:
                proc['cmdline'] = cached[1]
                return

            # use psinfo to get command line if not already present
            try:
                p = psutil.Process(pid)
                cmdline = p.cmdline()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                cmdline = []
            cmdline_text = ' '.join(cmdline) if cmdline else name
            proc['cmdline'] = cmdline_text
            self._cmdline_cache[pid] = (name, cmdline_text)

    def on_timeline_changed(self):
        """Handle timeline selection changes"""
        if len(self.process_history) == 0:
            return
            
        # Get selected time in minutes from plot
        selected_time_minutes = self.timeline_line.getPos()[0]
        
        # Convert to absolute timestamp
        start_time = self.timestamps[0]
        selected_timestamp = start_time + (selected_time_minutes * 60.0)
        
        # Find closest process data point
        closest_data = None
        min_diff = float('inf')
        
        for data_point in self.process_history:
            diff = abs(data_point['timestamp'] - selected_timestamp)
            if diff < min_diff:
                min_diff = diff
                closest_data = data_point
                
        if closest_data:
            self.update_process_tables(closest_data['processes'])
    
    def on_interval_changed(self, value):
        """Handle poll interval changes from the spin box"""
        self.poll_interval = value
        
        # If currently polling, restart the timer with new interval
        if self.is_polling:
            self.update_timer.start(self.poll_interval * 1000)


def main():
    parser = argparse.ArgumentParser(description='System Resource Monitor')
    parser.add_argument('--poll-interval', '-i', type=int, default=20,
                       help='Polling interval in seconds (default: 20)')
    parser.add_argument('--load', '-l', type=str, default=None,
                       help='Load data from a saved JSON log file')
    
    args = parser.parse_args()
    
    app = QtWidgets.QApplication(sys.argv)
    monitor = SystemMonitor(poll_interval=args.poll_interval, load_file=args.load)
    monitor.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
