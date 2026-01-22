"""
Loads motionsynergy API with minimal UI for initialization and shutdown.
This is meant to be run from a server process that can stay alive to avoid the need to reinitialize the stage.
Clients can connect to the server process to interact with the stage. (see motionsynergy_client.py)
"""

import atexit
import logging
import os
import sys

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
    if isinstance(result, System.Threading.Tasks.Task):
        result = result.Result
    if not result.Success:
        raise MotionSynergyException(error_msg, result)
    return result


def load_motionsynergyapi(dll_file=None):
    if dll_file is not None:
        if not os.path.isfile(dll_file):
            raise FileNotFoundError(f"Motion synergy DLL file not found: {dll_file}")
        if not dll_file.lower().endswith("motionsynergyapi.dll"):
            raise ValueError(f"Expected a DLL file named MotionSynergyAPI.dll, got {dll_file}")
        path = os.path.dirname(dll_file)
    else:
        path = None

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

    result = check(motion_synergy.Initialize(run_init, progress), error_msg="Error initializing MotionSynergyAPI: ")
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


class SmartStageTrayIcon(qt.QObject):
    """Minimal user interface for the SmartStage background process.
    """
    enabled_changed = qt.Signal(object)

    def __init__(self):
        super().__init__()
        self._toggle_enable = False
        self.tray_icon = qt.QSystemTrayIcon(get_smartstage_icon())

        self.menu = qt.QMenu()

        self.label_action = qt.QAction("SmartStage", self.menu)
        self.label_action.setEnabled(False)
        self.menu.addAction(self.label_action)

        self.energize_action = qt.QAction("Energize motors", self.menu)
        self.energize_action.setEnabled(False)
        self.energize_action.triggered.connect(self._toggle_motors)
        self.menu.addAction(self.energize_action)

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
        if ss is None:
            self.energize_action.setEnabled(False)
            return
        self.energize_action.setEnabled(True)
        ss.add_enabled_state_callback(self._on_enabled_state_changed)
        self._update_enabled_state(ss.is_enabled(refresh=True))

    def _toggle_motors(self):
        if smartstage is None:
            return
        if self._toggle_enable:
            smartstage.enable()
        else:
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
        if all(state is False for state in enabled_state):
            text = "Enable motors"
            self._toggle_enable = True
        else:
            text = "Disable motors"
            self._toggle_enable = False
        self.energize_action.setText(text)


tray_icon = None


def install_tray_icon():
    global tray_icon
    _ensure_log_viewer()
    tray_icon = SmartStageTrayIcon()


def set_smartstage(ss):
    global smartstage
    smartstage = ss
    if tray_icon is not None:
        tray_icon.set_smartstage(ss)
    _refresh_console_namespace()


def create_smartstage(*args, **kwargs):
    from .smartstage import SmartStage

    ss = SmartStage(*args, **kwargs)
    set_smartstage(ss)
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
