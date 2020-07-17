#  Seizz SDK Python Wrapper
# All Rights Reserved. Copyright (c)  Oy 2019
# Author: Ari Salmi
# Version: 0.3
# Date: 20-01-2019

# REQUIREMENTS:
# pywin32 (conda install pywin32)
# pip install pythonnet
# pip uninstall clr (as it is coming from pythonnet)
# Zeiss RDK package + Zeiss MTB Service needs to run as windows service


# Importing MTB.Api generated with makepy
import atexit
import inspect
import threading
import time
from threading import Thread, Lock

# in order to import clr, it is required to install python for .Net (pip install pythonnet) under windows
# running under linux has not been tested yet
import clr

DEFAULT_API_DLL_LOCATION = "C:\Program Files\Carl Zeiss\MTB 2011 - 2.16.0.9\MTB Api\MTBApi.dll"
MTB = None


class ZeissMtbSdk(object):
    _instance = None

    @classmethod
    def getSingleton(cls, dllLocation=None):
        if cls._instance is None:
            global MTB
            clr.AddReference(dllLocation or DEFAULT_API_DLL_LOCATION)
            import ZEISS
            MTB = ZEISS.MTB

            cls._instance = ZeissMtbSdk()
            cls._instance.connect()
            atexit.register(cls._instance.disconnect)

        return cls._instance

    def __init__(self):
        self._devicesByID = {}
        self.threadLock = None
        self.m_MTBConnection = None
        self.m_MTBRoot = None
        self.m_MTBDevice = None
        self.m_ID = ""
        self.m_MTBBaseEvents = None
        self.m_MTBChangerEvents = None
        self.m_devices = []
        self.m_components = []
        self._reflectorChanger = None
        self.m_objective = None
        self.m_focus = None
        self.m_shutter = None
        self.m_shutter_switch = None
        self._tl_lamp = None
        self._rl_lamp = None
        # By default selected device is first
        self.m_selected_device_index = 0
        self.m_selected_component_index = 0
        self.m_selected_element_index = 0
        self.device_busy = threading.Event()

    def connect(self):
        self.m_MTBConnection = MTB.Api.MTBConnection()
        self.m_ID = self.m_MTBConnection.Login("en", "")
        self.m_MTBRoot = self.m_MTBConnection.GetRoot(self.m_ID)
        self.threadLock = Lock()

    def getID(self):
        return self.m_ID

    def disconnect(self):
        for dev in self._devicesByID.values():
            dev.disconnect()

        print("Logging out of MTB..")
        self.m_MTBConnection.Logout(self.m_ID)

    def getDevices(self):
        count = self.m_MTBRoot.GetDeviceCount()
        return [self.m_MTBRoot.GetDevice(i) for i in range(0, count)]

    def getComponentsByDevice(self):
        return {
            device: [device.GetComponentFullConfig(i) for i in range(0, device.GetComponentCount())]
            for device in self.getDevices()}

    def getReflectorChanger(self):
        if self._reflectorChanger is None:
            self._reflectorChanger = ZeissMtbReflectorChanger(self, self.m_MTBRoot.GetComponent("MTBReflectorChanger"))
            self._devicesByID[self._reflectorChanger.getID()] = self._reflectorChanger

        return self._reflectorChanger

    def getTLLamp(self):
        return self.getSpecificLamp("MTBTLHalogenLamp")

    def getRLLamp(self):
        return self.getSpecificLamp("MTBRLHalogenLamp")

    def getSpecificLamp(self, componentID):
        if componentID not in self._devicesByID:
            self._devicesByID[componentID] = ZeissMtbLamp(self, self.m_MTBRoot.GetComponent(componentID))
        return self._devicesByID[componentID]

    def getObjective(self):
        if self.m_objective is None:
            # self.m_devices[self.m_selected_device_index]
            self.m_objective = ZeissMtbObjective(self.m_MTBRoot, self.m_ID)
            self._devicesByID[self.m_objective.getID()] = self.m_objective

        return self.m_objective

    def getFocus(self):
        if self.m_focus is None:
            self.m_focus = self.m_MTBRoot.GetComponent("MTBFocus")
            self._devicesByID[self.m_focus.getID()] = self.m_focus
        return self.m_focus

    def getShutter(self):
        if self.m_shutter is None:
            self.m_shutter = ZeissMtbShutter(self.m_MTBRoot, self.m_ID)
            self._devicesByID[self.m_shutter.getID()] = self.m_shutter
        return self.m_shutter


class ZeissMtbComponent(object):
    def __init__(self, sdk, component):
        self._zeiss = sdk
        self._component = component

    def getID(self):
        return self._component.ID

    def getName(self):
        return self._component.Name


class ZeissMtbContinual(ZeissMtbComponent):
    """
    "Continual" refers to the general concept of hardware which can be set to a value in a range. Used here
     primarily to encapsulate the event listeners.
    """

    def __init__(self, sdk, component, units="%"):
        super(ZeissMtbContinual, self).__init__(sdk, component)
        self._eventSink = None
        self._onChange = None
        self._onSettle = None
        self._onReachLimit = None
        self._units = units

    def registerEventHandlers(self, onChange=None, onSettle=None, onReachLimit=None):
        if self._eventSink is not None:
            self.disconnect()
        self._eventSink = MTB.Api.MTBContinualEventSink()

        if onChange is not None:
            if hasattr(inspect, "signature") and len(inspect.signature(onChange).parameters) != 1:
                raise ValueError("onChange handler must accept exactly one arg")
            self._onChange = self._wrapEventHandler(onChange)
            self._eventSink.MTBPositionChangedEvent += MTB.Api.MTBContinualPositionChangedHandler(self._onChange)
        if onSettle is not None:
            if hasattr(inspect, "signature") and len(inspect.signature(onSettle).parameters) != 1:
                raise ValueError("onSettle handler must accept exactly one arg")
            self._onSettle = self._wrapEventHandler(onSettle)
            self._eventSink.MTBPositionSettledEvent += MTB.Api.MTBContinualPositionSettledHandler(self._onSettle)
        if onReachLimit is not None and hasattr(self._eventSink, "MTBPHWLimitReachedEvent"):
            # TODO find out what args this needs
            self._onReachLimit = onReachLimit
            self._eventSink.MTBPHWLimitReachedEvent += MTB.Api.MTBContinualHWLimitReachedHandler(onReachLimit)

        self._eventSink.ClientID = self._zeiss.getID()
        self._eventSink.Advise(self._component)

    def _wrapEventHandler(self, handler):
        def wrappedHandler(hashtable):
            return handler(hashtable[self._units])

        return wrappedHandler

    def disconnect(self):
        if self._eventSink is None:
            return
        self._eventSink.Unadvise(self._component)
        if self._onChange is not None:
            self._eventSink.MTBPositionChangedEvent -= MTB.Api.MTBContinualPositionChangedHandler(self._onChange)
            self._onChange = None
        if self._onSettle is not None:
            self._eventSink.MTBPositionSettledEvent -= MTB.Api.MTBContinualPositionSettledHandler(self._onSettle)
            self._onSettle = None
        if self._onReachLimit is not None:
            self._eventSink.MTBPHWLimitReachedEvent -= MTB.Api.MTBContinualHWLimitReachedHandler(self._onReachLimit)
            self._onReachLimit = None

        self._eventSink = None

    def getPosition(self):
        return self._component.Position

    def setPosition(self, newPosition):
        with self._zeiss.threadLock:
            self._component.SetPosition(newPosition, MTB.Api.MTBCmdSetModes.Default)


class ZeissMtbChanger(ZeissMtbContinual):
    def __init__(self, sdk, component):
        super(ZeissMtbChanger, self).__init__(sdk, component, units=None)

    def getElementCount(self):
        return self._component.getElementCount()

    def getPosition(self):
        """
        Returns
        -------
        int
            1-based index of the current filter
        """
        return super(ZeissMtbChanger, self).getPosition()

    def setPosition(self, newPosition):
        """
        Parameters
        ----------
        newPosition : int
            1-based index of the filter to change to.

        """
        super(ZeissMtbChanger, self).setPosition(newPosition)


class ZeissMtbFocus:
    def __init__(self, root):
        self.m_component = root.GetComponent("MTBFocus")


class ZeissMtbObjective(ZeissMtbChanger):
    def __init__(self, root, mtbId):
        self.m_MTBRoot = root
        self.m_objective = root.GetComponent("IMTBObjective")
        self.m_ID = mtbId
        ZeissMtbChanger.__init__(self, root, mtbId, "MTBObjectiveChanger")
        self.registerEvents(self.onObjectivePositionChanged, self.onObjectivePositionSettled)

    def onObjectivePositionChanged(self, position):
        print(" Objective position changed to " + position)

    def onObjectivePositionSettled(self, position):
        print(" Objective position settled to " + position)

    def magnification(self):
        return self.m_objective.magnification

    def aperture(self):
        return self.m_objective.aperture

    def contrastMethod(self):
        return self.m_objective.contrastMethod

    def features(self):
        return self.m_objective.features

    def workingDistance(self):
        return self.m_objective.workingDistance


class ZeissMtbShutter(ZeissMtbChanger):
    # MTBRLShutter
    # MTBTLShutter 
    def __init__(self, root, mtbId):
        self.m_MTBRoot = root
        self.m_rlShutter = ZeissMtbChanger(root, mtbId, "MTBRLShutter")
        self.m_tlShutter = ZeissMtbChanger(root, mtbId, "MTBLamp")
        self.m_shutterSwitch = ZeissMtbChanger(root, mtbId, "MTBRLTLSwitch")
        self.m_ID = mtbId

        ZeissMtbChanger.__init__(self, root, mtbId, "MTBRLShutter")
        self.registerEvents(self.onShutterPositionChanged, self.onShutterPositionSettled)

    def registerRLShutterEvents(self, positionChanged):
        if self.m_rlShutter:
            self.m_rlShutter.registerEvents(positionSettledFunc=positionChanged)

    def registerTLShutterEvents(self, positionChanged):
        if self.m_tlShutter:
            self.m_tlShutter.registerEvents(positionSettledFunc=positionChanged)

    def setRLShutter(self, state):
        self.m_rlShutter.setPosition(state)

    def getRLShutter(self):
        return self.m_rlShutter.getPosition()

    def getTLShutter(self, state):
        self.m_tlShutter.setPosition(state)

    def setRLTLSwitch(self, state):
        self.m_shutterSwitch.setPosition(state)

    def onShutterPositionChanged(self, position):
        print("%1 shutter position changed to %2", "self.m_shutterName", position)

    def onShutterPositionSettled(self, position):
        print("%1 shutter position settled to %2", "self.m_shutterName", position)

    def getState(self):
        # ReflectedLight = 1,
        # TransmittedLight = 2,
        # Observation = 4,
        # Left = 8,
        # Right = 16
        return self.m_shutterSwitch.State


class ZeissMtbLamp(ZeissMtbContinual):
    def setIsActive(self, isActive):
        with self._zeiss.threadLock:
            if isActive:
                self._component.SetOnOff(MTB.Api.MTBOnOff.On, MTB.Api.MTBCmdSetModes.Default)
            else:
                self._component.SetOnOff(MTB.Api.MTBOnOff.Off, MTB.Api.MTBCmdSetModes.Default)

    def getIsActive(self):
        return self._component.GetOnOff() == MTB.Api.MTBOnOff.On

    def setBrightness(self, percent):
        with self._zeiss.threadLock:
            self._component.SetPosition(float(percent), "%", MTB.Api.MTBCmdSetModes.Default)

    def getBrightness(self):
        return self._component.GetPosition("%")


class ZeissMtbReflectorChanger(ZeissMtbChanger):
    def getWavelengthArea(self, index):
        return self._component.getWavelengthArea(index)

    def getWavelengthAreaCount(self):
        return self._component.getWavelengthAreaCount()

    def contrastMethod(self):
        return self._component.contrastMethod

    def features(self):
        return self._component.features
