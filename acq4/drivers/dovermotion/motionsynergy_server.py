import os, sys, atexit
import teleprox.qt as qt


isLinux = sys.platform.startswith("linux")
if isLinux:
    # Use Microsoft's dotnet, rather than Mono
    from pythonnet import load
    load("coreclr")

import clr
from System.Collections import *
from System.Collections.Generic import List
from System import String


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
        sys.exit(f"The MotionSynergyGUI application must be run to select your product and communications settings (checked {config_path}).")

    # Configure the system using the above settings.
    result = motionSynergy.Configure(instrumentSettings).Result
    if result.Success is False:
        raise Exception(f"Configuration failed: {result}")
    return result


def initialize(run_init: bool=True, progress=None):
    """Commutate motors and home axes. Must be run once when starting up before interacting with the stage.

    **This will move the stage quickly and over long distances**
    
    Initialize will establish a connection to each axis device, initialize the hardware and
    execute the Scripts/Initialize.lua script, which in turn will home each axis for this example.
    """
    msgbox = qt.QMessageBox()
    msgbox.setText("Beginning stage initialization.\nThis will move the stage quickly and over long distances.\nOk to continue?")
    msgbox.setStandardButtons(qt.QMessageBox.Ok | qt.QMessageBox.Cancel)
    msgbox.setDefaultButton(qt.QMessageBox.Cancel)
    response = msgbox.exec_()
    if response != qt.QMessageBox.Ok:
        return None

    result = motionSynergy.Initialize(run_init, progress).Result
    if result.Success is False:
        raise Exception(f"Initialization failed: {result}")
    
    return result


motionSynergy = None
instrumentSettings = None

def get_motionsynergyapi(dll_file=None):
    global motionSynergy, instrumentSettings
    if motionSynergy is None:
        motionSynergy, instrumentSettings = load_motionsynergyapi(dll_file)
        atexit.register(shutdown)
        configure(motionSynergy, instrumentSettings)
    return motionSynergy, instrumentSettings


def shutdown():
    # Prior to exiting the application, Shutdown should be called on the MotionSynergyAPI library.
    # This will close all connections to the axis devices and close the log file(s).
    global motionSynergy
    if motionSynergy is not None:
        result = motionSynergy.Shutdown()
        if not result.Success:
            raise Exception(f"MotionSynergy shutdown failed: {result}")


# create a tray icon for the daemon process
def quit():
    qt.QApplication.quit()

ss_icon_file = os.path.join(os.path.dirname(__file__), "smartstage_icon.png")
tray_icon = qt.QSystemTrayIcon(qt.QIcon(ss_icon_file))
menu = qt.QMenu()
action = qt.QAction("Quit", menu)
action.triggered.connect(quit)
menu.addAction(action)
tray_icon.setContextMenu(menu)
tray_icon.show()


# if __name__ == "__main__":
#     import argparse

#     parser = argparse.ArgumentParser(description="Start a teleprox server for the MotionSynergyAPI")
#     parser.add_argument("--dll", type=str, help="Path to the MotionSynergyAPI.dll file")
#     parser.add_argument("--port", type=int, default=60738, help="Port to listen on")
#     parser.add_argument("--no-init", action="store_true", help="Do not initialize the MotionSynergyAPI")
#     args = parser.parse_args()

#     path = "C:\\Users\\lukec\\Desktop\\Devices\\Dover Stages\\MotionSynergyAPI_SourceCode_3.6.12025\\"
#     motionSynergy, instrumentSettings = get_motionsynergyapi(path + "MotionSynergyAPI.dll")
#     configure(motionSynergy, instrumentSettings)
#     if not args.no_init:
#         initialize()

#     server = teleprox.RPCServer(address=f"tcp://127.0.0.1:{args.port}")
#     server['motionSynergy'] = motionSynergy
#     server['instrumentSettings'] = instrumentSettings
#     server.run_forever()



# def axes():
#     return list(motionSynergy.AxisList)

# def pos():
#     return [axis.GetActualPosition().Value for axis in axes()]



# print("Current position:", pos())


# product = motionSynergy.GetFirstProduct()
# productType = product.ProductType
# axisNames = product.AxisNames
# axes =  [axis for axisName in axisNames for axis in motionSynergy.AxisList if axis.Name == axisName]

# Perform a series of moves, appropriate for the selected product.
# These moves are wrapped in a try / catch block to ensure Shutdown is called prior to
# exit, ensuring each axis is disabled on exit.
# try:
#     if productType == "SmartStageLinear":
#         from SmartStageLinear import *
#         smartStage = SmartStageLinear(axes[0], motionSynergy.Diagnostics)
#         smartStage.PerformMoves()
#     elif productType == "SmartStageXY":
#         from SmartStageXY import *
#         smartStage = SmartStageXY(axes[0], axes[1], motionSynergy.Diagnostics)
#         smartStage.PerformMoves()
#     elif productType == "DOF5":
#         from DOF5 import *
#         dof5 = DOF5(axes[0], motionSynergy.Diagnostics)
#         dof5.PerformMoves()
#     elif productType == "DMCM":
#         from DMCM import *
#         dmcm = DMCM(axes[0], motionSynergy.Diagnostics)
#         dmcm.PerformMoves()
#     else:
#         print(
#             f"Unknown ProductType {productType} specified in configuration file {instrumentSettings.ConfigurationFilename}.")
# except Exception as e:
#     print(repr(e))


# Things we can do with axes  (all methods return a future-like object)

# result = axis.MoveAbsolute(mm)
# result.Wait()
# result.Alert  # cause of failure
# result.Success  # bool
# result.ToString()  # for debugging
# axis.MoveContinuous  # move to absolute position; can be called while already in motion
# axis.GetActualPosition().Value
# axis.Stop()
# axis.Get/SetVelocity  # max velocity, not current velocity
# axis.Get/SetAcceleration
# axis.Get/SetDeceleration
# axis.Get/SetJerk
# axis.GetMotorCurrent
# axis.Disable()  # de-energize motor
# axis.Enable()   # energize motor

