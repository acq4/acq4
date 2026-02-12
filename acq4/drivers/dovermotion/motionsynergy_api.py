"""
Loads motionsynergy API with minimal UI for initialization and shutdown.
This is meant to be run from a server process that can stay alive to avoid the need to reinitialize the stage.
Clients can connect to the server process to interact with the stage. (see motionsynergy_client.py)
"""

import atexit
import logging
import os
import subprocess
import sys
import re

import pyqtgraph.console as pgconsole
import teleprox.qt as qt
from teleprox.log.logviewer import LogViewer

if is_linux := sys.platform.startswith("linux"):
    # Use Microsoft's dotnet, rather than Mono
    from pythonnet import load

    load("coreclr")

import clr
from System.Collections import *
from System.Collections.Generic import List
from System import String
import System.Threading.Tasks


class MotionSynergyException(Exception):
    def __init__(self, message, result):
        self.result = result
        super().__init__(message + result.Alert.UserDescription + " : " + result.Alert.Description)


def check(result, error_msg=""):
    """Check whether the result of a motionsynergy API call has an error.

    Accepts Task[InstrumentResult] or InstrumentResult instances
    If the result is a Task, then block until the result is available.
    Returns the InstrumentResult
    """
    if isinstance(result, System.Threading.Tasks.Task):
        result = result.Result
    if not result.Success:
        raise MotionSynergyException(error_msg, result)
    return result


# message generated while trying to update instrument config COM port and serial mode
# to be displayed if initialization fails
update_error_message = None


def load_motionsynergyapi(dll_file=None, auto_update_port=True):
    global update_error_message
    if dll_file is not None:
        if not os.path.isfile(dll_file):
            raise FileNotFoundError(f"Motion synergy DLL file not found: {dll_file}")
        if not dll_file.lower().endswith("motionsynergyapi.dll"):
            raise ValueError(f"Expected a DLL file named MotionSynergyAPI.dll, got {dll_file}")
        path = os.path.dirname(dll_file)
    else:
        path = None

    if auto_update_port:
        update_error_message = update_com_port(path)

    # Both needed to ensure all DLL files can be found
    os.environ["PATH"] = os.environ["PATH"] + ";" + path
    sys.path.append(path)

    clr.AddReference("MotionSynergyAPI")
    from MotionSynergyAPI import MotionSynergyAPINative
    from MotionSynergyAPI import InstrumentSettings

    motionSynergy = MotionSynergyAPINative()

    instrumentSettings = InstrumentSettings()
    instrumentSettings.ApplicationVersionString = "1.0"
    instrumentSettings.SupportFolder = path + "\\SupportFolder"
    instrumentSettings.ProgramDataFolder = path + "\\ProgramDataFolder"
    instrumentSettings.ConfigurationFilename = "Instrument.cfg"

    return motionSynergy, instrumentSettings


def update_com_port(dll_path):
    """Windows likes to reassign USB serial ports to different COM numbers and lose their configuration in the process.
    
    1. Scan available com ports to find any named "Moxa*"
    2. Read the instrument.cfg file in dll_path/SupportFolder to get the saved COM port  (looks like hwid=COM3)
    3. If the saved com port is not found or not a Moxa device, then update the instrument.cfg to use the only Moxa device found (if multiple, then raise an exception)
    4. Update windows registry to set moxa to use RS-485-4W mode
    """

    # command for finding device registry keys:
    #   > wmic path Win32_PnPEntity where "Caption like '%(COM%)'" get DeviceID
    #     DeviceID
    #     ACPI\PNP0501\0
    #     MXUPORT\COM\9&1B23C7F3&0&0000

    # registry settings for moxa ports:
    #   >reg query "HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Enum\MXUPORT\COM\9&1B23C7F3&0&0000\Device Parameters"

    #     HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Enum\MXUPORT\COM\9&1B23C7F3&0&0000\Device Parameters
    #     PortFlag    REG_DWORD    0x0
    #     PortName    REG_SZ    COM7
    #     InstanceID    REG_SZ    9&1b23c7f3&0&0000
    #     CoInstalled    REG_DWORD    0x1
    #     SerInterface    REG_DWORD    0x3

    # SerInterface must be ser to 0x3 for RS-485-4W mode

    import serial.tools.list_ports
    # import configparser -- don't use configparser; it is bad at round-trip
    import winreg

    com_ports = list(serial.tools.list_ports.comports())
    moxa_ports = {p.device:p for p in com_ports if p.description.lower().startswith("moxa")}
    if len(moxa_ports) == 0:
        return  "No Moxa COM ports found"
    config_path = os.path.join(dll_path, "SupportFolder", "Instrument.cfg")
    config = open(config_path, 'r').read()
    hwid_regex = r'^\s*hwid\s*=\s*(\w+)\s*$'
    match = re.search(hwid_regex, config, re.MULTILINE)
    if match:
        saved_com_port = match.group(1)
    else:
        return f"Cannot find saved COM port in {config_path}"

    # verify configured port is a moxa device; update config if possible
    if saved_com_port not in moxa_ports:
        if len(moxa_ports) > 1:
            return f"Instrument config at {config_path} has invalid COM port {saved_com_port}, but multiple Moxa COM ports found {list(moxa_ports.keys())}, cannot select automatically"
        new_com_port = list(moxa_ports.keys())[0]
        # config.set("SerialComms1Options", "hwid", new_com_port)
        # with open(config_path, 'w') as configfile:
        #     config.write(configfile)
        # manually rewrite the config file to preserve formatting
        new_config = re.sub(hwid_regex, f'hwid = {new_com_port}', config, flags=re.MULTILINE)
        with open(config_path, 'w') as configfile:
            configfile.write(new_config)
        logging.info(f"Updated instrument config at {config_path} to use Moxa COM port {new_com_port} instead of saved port {saved_com_port}")
        saved_com_port = new_com_port

    # update registry to set SerInterface to 0x3 for RS-485-4W mode for the selected port
    try:
        # find device registry key
        moxa_port = moxa_ports[saved_com_port]
        hwid = moxa_port.hwid  # e.g. "MXUPORT\COM\9&1B23C7F3&0&0000"
        reg_path = f"SYSTEM\\CurrentControlSet\\Enum\\{hwid}\\Device Parameters"
        # read current SerInterface value
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path, 0, winreg.KEY_READ) as key:
            ser_interface, reg_type = winreg.QueryValueEx(key, "SerInterface")
        if ser_interface != 0x3:
            # update SerInterface to 0x3
            try:
                output = subprocess.check_output([
                    "powershell",
                    "-Command",
                    "Start-Process reg -ArgumentList ",
                    f"'add \"HKEY_LOCAL_MACHINE\\{reg_path}\" /v SerInterface /t REG_DWORD /d 3 /f'",
                    "-Verb RunAs"
                ])
            except subprocess.CalledProcessError as e:
                return f"Error updating registry for Moxa COM port {saved_com_port}: {e}"
            logging.info(f"Updated registry SerInterface to 0x3 for RS-485-4W mode on Moxa COM port {saved_com_port}")
    except Exception as e:
        return f"Error updating registry for Moxa COM port {saved_com_port}: {e}"


def configure(motionSynergy, instrumentSettings):
    # First check the MotionSynergyGUI has been run to select the product and communications settings.
    config_path = os.path.join(instrumentSettings.SupportFolder, instrumentSettings.ConfigurationFilename)
    if not os.path.isfile(config_path):
        sys.exit(
            "The MotionSynergyGUI application must be run to select your product and communications settings "
            f"(checked {config_path}).")

    # Configure the system using the above settings.
    result = motionSynergy.Configure(instrumentSettings).Result
    if result.Success is False:
        raise ValueError(f"Configuration failed: {result}")
    return result


initialized = False


def initialize(run_init: bool = True, progress=None):
    """Commutate motors and home axes. Must be run once when starting up before interacting with the stage.

    **This will move the stage quickly and over long distances**
    
    Initialize will establish a connection to each axis device, initialize the hardware and
    execute the Scripts/Initialize.lua script, which in turn will home each axis for this example.
    """
    global initialized
    if initialized:
        return None

    init_warning_msgbox()

    try:
        result = check(motion_synergy.Initialize(run_init, progress), error_msg="Error initializing MotionSynergyAPI: ")
    except MotionSynergyException as e:
        if update_error_message is not None:
            e.add_note(update_error_message)
        raise
    initialized = True
    return result


motion_synergy = None
instrument_settings = None
smartstage = None
log_viewer = None
log_handler_installed = False
console_window = None
console_widget = None


def get_motionsynergyapi(dll_file=None):
    global motion_synergy, instrument_settings
    if motion_synergy is None:
        motion_synergy, instrument_settings = load_motionsynergyapi(dll_file)
        atexit.register(shutdown)
        configure(motion_synergy, instrument_settings)
    return motion_synergy, instrument_settings


def shutdown():
    # Prior to exiting the application, Shutdown should be called on the MotionSynergyAPI library.
    # This will close all connections to the axis devices and close the log file(s).
    global motion_synergy
    if motion_synergy is not None:
        check(motion_synergy.Shutdown(), error_msg="Error shutting down MotionSynergyAPI: ")


# create a tray icon for the daemon process
def _quit():
    qt.QApplication.quit()


def get_smartstage_icon():
    ss_icon_file = os.path.join(os.path.dirname(__file__), "smartstage_icon.png")
    return qt.QIcon(ss_icon_file)


def init_warning_msgbox():
    if qt.QApplication.instance() is None:
        app = qt.QApplication([])
    msgbox = qt.QMessageBox()
    msgbox.setWindowTitle("MotionSynergy Initialization")
    msgbox.setIcon(qt.QMessageBox.Warning)
    # set window icon
    msgbox.setWindowIcon(get_smartstage_icon())
    msgbox.setText(
        "Beginning stage initialization.\nThis will move the stage quickly and over long distances.\nOk to continue?")
    msgbox.setStandardButtons(qt.QMessageBox.Ok | qt.QMessageBox.Cancel)
    msgbox.setDefaultButton(qt.QMessageBox.Cancel)
    response = msgbox.exec_()
    if response != qt.QMessageBox.Ok:
        raise RuntimeError("MotionSynergy initialization cancelled by user.")


class TrayIcon(qt.QSystemTrayIcon):
    """Tray icon that activates menu on left mouse button"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.activated.connect(self.showMenuOnTrigger)

    def showMenuOnTrigger(self, reason):
        if reason == qt.QSystemTrayIcon.Trigger:
            self.contextMenu().popup(qt.QCursor.pos())


class SmartStageTrayIcon(qt.QObject):
    """Minimal user interface for the SmartStage background process.
    """
    enabled_changed = qt.Signal(object)

    def __init__(self):
        super().__init__()
        self.axis_actions = []
        self.axis_toggle_enable = []
        self.tray_icon = TrayIcon(get_smartstage_icon())

        self.menu = qt.QMenu()

        self.label_action = qt.QAction("SmartStage", self.menu)
        self.label_action.setEnabled(False)
        self.menu.addAction(self.label_action)

        self.menu.addSeparator()

        # Axis-specific enable/disable actions will be added in set_smartstage
        self.enable_all_action = qt.QAction("Enable all", self.menu)
        self.enable_all_action.setEnabled(False)
        self.enable_all_action.triggered.connect(self._enable_all_motors)
        self.menu.addAction(self.enable_all_action)

        self.disable_all_action = qt.QAction("Disable all", self.menu)
        self.disable_all_action.setEnabled(False)
        self.disable_all_action.triggered.connect(self._disable_all_motors)
        self.menu.addAction(self.disable_all_action)

        self.menu.addSeparator()

        self.initialize_action = qt.QAction("Initialize", self.menu)
        self.initialize_action.triggered.connect(initialize)
        self.menu.addAction(self.initialize_action)

        self.log_action = qt.QAction("Show Log", self.menu)
        self.log_action.triggered.connect(self._show_log_window)
        self.menu.addAction(self.log_action)

        self.console_action = qt.QAction("Show Console", self.menu)
        self.console_action.triggered.connect(self._show_console_window)
        self.menu.addAction(self.console_action)

        self.quit_action = qt.QAction("Quit", self.menu)
        self.quit_action.triggered.connect(_quit)
        self.menu.addAction(self.quit_action)

        self.tray_icon.setContextMenu(self.menu)
        self.tray_icon.show()

        self.enabled_changed.connect(self._update_enabled_state, qt.Qt.QueuedConnection)

        self.set_smartstage(smartstage)

    def set_smartstage(self, ss):
        # Remove any existing axis actions
        for action in self.axis_actions:
            self.menu.removeAction(action)
        self.axis_actions = []
        self.axis_toggle_enable = []

        if ss is None:
            self.enable_all_action.setEnabled(False)
            self.disable_all_action.setEnabled(False)
            return

        # Create menu items for each axis
        axis_count = ss.axis_count()
        axis_names = ss.axis_names()

        for i in range(axis_count):
            axis_name = axis_names[i]
            action = qt.QAction(f"Enable {axis_name}", self.menu)
            action.triggered.connect(lambda _, idx=i: self._toggle_axis(idx))
            # Insert the action before the "Enable all" action
            self.menu.insertAction(self.enable_all_action, action)
            self.axis_actions.append(action)
            self.axis_toggle_enable.append(True)  # Default to wanting to enable

        # Add separator after axis actions if we have any
        if axis_count > 0:
            self.menu.insertSeparator(self.enable_all_action)

        self.enable_all_action.setEnabled(True)
        self.disable_all_action.setEnabled(True)
        ss.add_enabled_state_callback(self._on_enabled_state_changed)
        self._update_enabled_state(ss.is_enabled(refresh=True))

    def _toggle_axis(self, axis_index):
        if smartstage is None:
            return
        if self.axis_toggle_enable[axis_index]:
            smartstage.enable_axis(axis_index)
        else:
            smartstage.disable_axis(axis_index)

    def _enable_all_motors(self):
        if smartstage is None:
            return
        smartstage.enable()

    def _disable_all_motors(self):
        if smartstage is None:
            return
        smartstage.disable()

    def _show_log_window(self):
        viewer = _ensure_log_viewer()
        viewer.show()
        viewer.raise_()
        viewer.activateWindow()

    def _show_console_window(self):
        win = _ensure_console_window()
        win.show()
        win.raise_()
        win.activateWindow()

    def _on_enabled_state_changed(self, enabled_state):
        self.enabled_changed.emit(enabled_state)

    def _update_enabled_state(self, enabled_state):
        if smartstage is None:
            return

        # Update each axis action based on its enabled state
        axis_names = smartstage.axis_names()
        for i, (action, is_enabled) in enumerate(zip(self.axis_actions, enabled_state)):
            axis_name = axis_names[i]
            if is_enabled:
                action.setText(f"Disable {axis_name}")
                self.axis_toggle_enable[i] = False
            else:
                action.setText(f"Enable {axis_name}")
                self.axis_toggle_enable[i] = True


tray_icon = None


def install_tray_icon():
    global tray_icon
    _ensure_log_viewer()
    tray_icon = SmartStageTrayIcon()
    # disable closing on last window closed; we quit via the tray icon instead
    qt.QApplication.setQuitOnLastWindowClosed(False)


def set_tray_smartstage(ss):
    """Set the SmartStage used by the tray icon"""
    global smartstage
    smartstage = ss
    if tray_icon is not None:
        tray_icon.set_smartstage(ss)
    _refresh_console_namespace()


def create_smartstage(*args, **kwargs):
    from .smartstage import SmartStage

    ss = SmartStage(*args, **kwargs)
    set_tray_smartstage(ss)
    return ss


def _ensure_log_viewer():
    global log_viewer, log_handler_installed
    if log_viewer is None:
        log_viewer = LogViewer(logger=None)
    if not log_handler_installed:
        root_logger = logging.getLogger()
        log_viewer.handler.setLevel(logging.DEBUG)
        root_logger.addHandler(log_viewer.handler)
        log_handler_installed = True
    return log_viewer


def _refresh_console_namespace():
    if console_widget is None:
        return
    namespace = console_widget.localNamespace
    namespace["smartstage"] = smartstage
    namespace["motion_synergy"] = motion_synergy
    namespace["instrument_settings"] = instrument_settings


def _ensure_console_window():
    global console_window, console_widget
    if console_window is None:
        initial_text = (
            "# Available variables:\n"
            "#   smartstage - SmartStage instance\n"
            "#   motion_synergy - MotionSynergyAPI object\n"
            "#   instrument_settings - MotionSynergyAPI InstrumentSettings\n"
        )
        console_window = pgconsole.ConsoleWidget(
            namespace={
                "smartstage": smartstage,
                "motion_synergy": motion_synergy,
                "instrument_settings": instrument_settings,
            },
            text=initial_text,
        )
        console_window.resize(900, 600)
    else:
        _refresh_console_namespace()
    return console_window
