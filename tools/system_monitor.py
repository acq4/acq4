# System resource monitoring utility that logs and plots CPU/memory usage over time
#Displays real-time graphs and top process lists with historical timeline selection

import argparse
import sys
import time
import json
import os
import psutil
from datetime import datetime

import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets


class SystemMonitor(QtWidgets.QWidget):
    def __init__(self, poll_interval=20, load_file=None):
        super().__init__()
        self.poll_interval = poll_interval
        self.is_polling = False
        self.loaded_from_file = load_file is not None
        self.current_log_file = None
        
        # Data storage
        self.timestamps = []
        self.cpu_data = []
        self.memory_data = []
        self.process_history = []  # List of dicts with timestamp and process data
        
        self.setup_ui()
        
        # Set up polling timer
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.poll_system_resources)
        
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
        self.cpu_table.horizontalHeader().setStretchLastSection(True)
        tables_layout.addWidget(self.cpu_table)
        
        # Memory processes table  
        memory_label = QtWidgets.QLabel('Top 10 Memory Processes')
        tables_layout.addWidget(memory_label)
        
        self.memory_table = QtWidgets.QTableWidget(10, 3)
        self.memory_table.setHorizontalHeaderLabels(['PID', 'Mem %', 'Command'])
        self.memory_table.horizontalHeader().setStretchLastSection(True)
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
        self.timer.start(self.poll_interval * 1000)
        self.is_polling = True
        self.start_stop_btn.setText('Stop Polling')
        
    def stop_polling(self):
        """Stop the polling timer and update button"""
        self.timer.stop()
        self.is_polling = False
        self.start_stop_btn.setText('Start Polling')
        self.save_current_data()
            
    def toggle_polling(self):
        """Start or stop the polling"""
        if self.is_polling:
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
        # Get current timestamp
        timestamp = time.time()
        
        # Get CPU and memory usage
        cpu_percent = psutil.cpu_percent()
        memory_percent = psutil.virtual_memory().percent
        
        # Store data
        self.timestamps.append(timestamp)
        self.cpu_data.append(cpu_percent)
        self.memory_data.append(memory_percent)
        
        # Get process information
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cpu_percent', 'memory_percent']):
            try:
                info = proc.info
                if info['cpu_percent'] is not None and info['memory_percent'] is not None:
                    # Get full command line
                    cmdline = ' '.join(info['cmdline']) if info['cmdline'] else info['name']
                    processes.append({
                        'pid': info['pid'],
                        'cpu_percent': info['cpu_percent'],
                        'memory_percent': info['memory_percent'],
                        'cmdline': cmdline[:50]  # Truncate long command lines
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
                
        # Store process data with timestamp
        self.process_history.append({
            'timestamp': timestamp,
            'processes': processes
        })
        
        # Update displays
        self.update_plot()
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
            self.cpu_table.setItem(i, 0, QtWidgets.QTableWidgetItem(str(proc['pid'])))
            self.cpu_table.setItem(i, 1, QtWidgets.QTableWidgetItem(f"{proc['cpu_percent']:.1f}"))
            self.cpu_table.setItem(i, 2, QtWidgets.QTableWidgetItem(proc['cmdline']))
            
        # Sort by memory usage
        memory_processes = sorted(processes, key=lambda x: x['memory_percent'], reverse=True)[:10]
        
        for i, proc in enumerate(memory_processes):
            self.memory_table.setItem(i, 0, QtWidgets.QTableWidgetItem(str(proc['pid'])))
            self.memory_table.setItem(i, 1, QtWidgets.QTableWidgetItem(f"{proc['memory_percent']:.1f}"))
            self.memory_table.setItem(i, 2, QtWidgets.QTableWidgetItem(proc['cmdline']))
            
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
            self.timer.start(self.poll_interval * 1000)


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