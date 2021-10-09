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
from threading import Lock

# in order to import clr, it is required to install python for .Net (pip install pythonnet) under windows
# running under linux has not been tested yet
import clr

from acq4.util.debug import printExc

# DEFAULT_API_DLL_LOCATION = "C:\Program Files\Carl Zeiss\MTB 2011 - 2.17.0.15\MTB Api\MTBApi.dll"
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
        self._componentsByID = {}
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

    def connect(self):
        self.m_MTBConnection = MTB.Api.MTBConnection()
        self.m_ID = self.m_MTBConnection.Login("en", "")
        self.m_MTBRoot = self.m_MTBConnection.GetRoot(self.m_ID)
        self.threadLock = Lock()

    def getID(self):
        return self.m_ID

    def disconnect(self):
        for dev in self._componentsByID.values():
            dev.disconnect()

        print("Logging out of MTB..")
        self.m_MTBConnection.Logout(self.m_ID)

    def getDevices(self):
        count = self.m_MTBRoot.GetDeviceCount()
        return [self.m_MTBRoot.GetDevice(i) for i in range(count)]

    def getAllComponentsByDevice(self):
        return {
            device: [
                device.GetComponentFullConfig(i)
                for i in range(device.GetComponentCount())
            ]
            for device in self.getDevices()
        }

    def getReflectorChanger(self):
        return self.getComponentByID(ZeissMtbReflectorChanger, "MTBReflectorChanger")

    def getTLLamp(self):
        return self.getComponentByID(ZeissMtbLamp, "MTBTLHalogenLamp")

    def getObjectiveChanger(self):
        return self.getComponentByID(ZeissMtbObjectiveChanger, "MTBObjectiveChanger")

    def getRLLamp(self):
        return self.getComponentByID(ZeissMtbLamp, "MTBRLHalogenLamp")

    def getTLShutter(self):
        return self.getComponentByID(ZeissMtbShutter, "MTBTLShutter")

    def getRLShutter(self):
        return self.getComponentByID(ZeissMtbShutter, "MTBRLShutter")

    def getComponentByID(self, deviceClass, componentID):
        if componentID not in self._componentsByID:
            component = self.m_MTBRoot.GetComponent(componentID)
            assert component is not None, f"No Zeiss component found with ID {componentID}. Components available: {self.getAllComponentsByDevice()}"
            self._componentsByID[componentID] = deviceClass(self, component)
        return self._componentsByID[componentID]


class ZeissMtbComponent(object):
    def __init__(self, sdk, component):
        assert component is not None
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

    def __init__(self, sdk, component):
        super(ZeissMtbContinual, self).__init__(sdk, component)
        self._eventSink = None
        self._onChange = None
        self._onSettle = None
        self._onReachLimit = None

    def registerEventHandlers(self, onChange=None, onSettle=None, onReachLimit=None):
        if self._eventSink is not None:
            self.disconnect()
        self._eventSink = self._createEventSink()

        if onChange is not None:
            self._onChange = self._wrapOnChange(onChange)
            self._eventSink.MTBPositionChangedEvent += self._onChange
        if onSettle is not None:
            self._onSettle = self._wrapOnSettle(onSettle)
            self._eventSink.MTBPositionSettledEvent += self._onSettle
        if onReachLimit is not None and hasattr(self._eventSink, "MTBPHWLimitReachedEvent"):
            # TODO find out how to wrap this
            self._onReachLimit = self._wrapOnReachLimit(onReachLimit)
            self._eventSink.MTBPHWLimitReachedEvent += self._onReachLimit

        self._eventSink.ClientID = self._zeiss.getID()
        self._eventSink.Advise(self._component)

    def _createEventSink(self):
        return MTB.Api.MTBContinualEventSink()

    def _wrapOnChange(self, handler):
        return self._printExceptionsInHandler(handler)

    def _printExceptionsInHandler(self, handler):
        def wrappedHandler(*args, **kwargs):
            try:
                return handler(*args, **kwargs)
            except Exception:
                printExc("")

        return wrappedHandler

    def _wrapOnSettle(self, handler):
        return self._printExceptionsInHandler(handler)

    def _wrapOnReachLimit(self, handler):
        return self._printExceptionsInHandler(handler)

    def disconnect(self):
        if self._eventSink is None:
            return
        self._eventSink.Unadvise(self._component)
        if self._onChange is not None:
            self._eventSink.MTBPositionChangedEvent -= self._onChange
            self._onChange = None
        if self._onSettle is not None:
            self._eventSink.MTBPositionSettledEvent -= self._onSettle
            self._onSettle = None
        if self._onReachLimit is not None:
            self._eventSink.MTBPHWLimitReachedEvent -= self._onReachLimit
            self._onReachLimit = None

        self._eventSink = None

    def getPosition(self):
        return self._component.Position

    def setPosition(self, newPosition):
        with self._zeiss.threadLock:
            self._component.SetPosition(newPosition, MTB.Api.MTBCmdSetModes.Default)


class ZeissMtbChanger(ZeissMtbContinual):
    """
    Positions are 1-based indexes.
    """

    def _createEventSink(self):
        return MTB.Api.MTBChangerEventSink()

    def _wrapOnChange(self, handler):
        if hasattr(inspect, "signature") and len(inspect.signature(handler).parameters) != 1:
            raise ValueError("onChange handler must accept exactly one arg")

        def wrappedHandler(pos):
            return self._printExceptionsInHandler(handler)(pos)

        return MTB.Api.MTBChangerPositionChangedHandler(wrappedHandler)

    def _wrapOnSettle(self, handler):
        if hasattr(inspect, "signature") and len(inspect.signature(handler).parameters) != 1:
            raise ValueError("onSettle handler must accept exactly one arg")

        def wrappedHandler(pos):
            return self._printExceptionsInHandler(handler)(pos)

        return MTB.Api.MTBChangerPositionSettledHandler(wrappedHandler)

    def getElementCount(self):
        return self._component.GetElementCount()


class ZeissMtbLamp(ZeissMtbContinual):
    def _wrapOnChange(self, handler):
        if hasattr(inspect, "signature") and len(inspect.signature(handler).parameters) != 1:
            raise ValueError("onChange handler must accept exactly one arg")

        def wrappedHandler(hashtable):
            return self._printExceptionsInHandler(handler)(hashtable["%"])

        return MTB.Api.MTBContinualPositionChangedHandler(wrappedHandler)

    def _wrapOnSettle(self, handler):
        if hasattr(inspect, "signature") and len(inspect.signature(handler).parameters) != 1:
            raise ValueError("onSettle handler must accept exactly one arg")

        def wrappedHandler(hashtable):
            return self._printExceptionsInHandler(handler)(hashtable["%"])

        return MTB.Api.MTBContinualPositionSettledHandler(wrappedHandler)

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
        return self._component.GetWavelengthArea(index)

    def getWavelengthAreaCount(self):
        return self._component.GetWavelengthAreaCount()

    def contrastMethod(self):
        return self._component.ContrastMethod

    def features(self):
        return self._component.Features


class ZeissMtbShutter(ZeissMtbChanger):
    OPEN = 2
    CLOSED = 1

    def getIsOpen(self):
        return self.getPosition() == self.OPEN

    def setIsOpen(self, isOpen):
        if isOpen:
            self.setPosition(self.OPEN)
        else:
            self.setPosition(self.CLOSED)

    def _wrapOnSettle(self, handler):
        if hasattr(inspect, "signature") and len(inspect.signature(handler).parameters) != 1:
            raise ValueError("onSettle handler must accept exactly one arg")

        def wrappedHandler(pos):
            return self._printExceptionsInHandler(handler)(pos == self.OPEN)

        return MTB.Api.MTBChangerPositionSettledHandler(wrappedHandler)


class ZeissMtbObjectiveChanger(ZeissMtbChanger):
    def __init__(self, root, component):
        ZeissMtbChanger.__init__(self, root, component)

    # def magnification(self):
    #     return self.m_objective.magnification
    #
    # def aperture(self):
    #     return self.m_objective.aperture
    #
    # def contrastMethod(self):
    #     return self.m_objective.contrastMethod
    #
    # def features(self):
    #     return self.m_objective.features
    #
    # def workingDistance(self):
    #     return self.m_objective.workingDistance


# Unfinished below this line


class ZeissMtbFocus:
    def __init__(self, root):
        self.m_component = root.GetComponent("MTBFocus")
