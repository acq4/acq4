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
import threading
import time
from threading import Thread, Lock

# in order to import clr, it is required to install python for .Net (pip install pythonnet) under windows
# running under linux has not been tested yet
import clr

DEFAULT_API_DLL_LOCATION = "C:\Program Files\Carl Zeiss\MTB 2011 - 2.16.0.9\MTB Api\MTBApi.dll"
MTB = None


def defaultOnPositionChanged(position):
    # in case, the changer position has changed, the current position is printed
    # a position of "0" indicates an invalid state
    print("Changer moved, current position: " + str(position))


def defaultOnPositionSettled(position):
    # in case, the changer position is settled, its current position is printed
    print("Changer settled on position: " + str(position))


def defaultOnHWLimitReached(state, limit):
    print("Continual HW limit reached (state, limit): %1,%2", str(state), str(limit))


# Main
class ZeissMtbSdk:
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
        self._devicesToDisconnect = []
        self.threadLock = None
        self.m_MTBConnection = None
        self.m_MTBRoot = None
        self.m_MTBDevice = None
        self.m_ID = ""
        self.m_MTBBaseEvents = None
        self.m_MTBChangerEvents = None
        self.m_devices = []
        self.m_components = []
        self.m_reflector = None
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
        for dev in self._devicesToDisconnect:
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

    def getReflector(self):
        if self.m_reflector is None:
            # self.m_devices[self.m_selected_device_index]
            self.m_reflector = ZeissMtbReflector(self.m_MTBRoot, self.m_ID)
            self._devicesToDisconnect.append(self.m_reflector)

        return self.m_reflector

    def getTLLamp(self):
        if self._tl_lamp is None:
            self._tl_lamp = ZeissMtbLamp(self, self.m_MTBRoot.GetComponent("MTBTLHalogenLamp"))
            self._devicesToDisconnect.append(self._tl_lamp)

        return self._tl_lamp

    def getRLLamp(self):
        if self._rl_lamp is None:
            self._rl_lamp = ZeissMtbLamp(self, self.m_MTBRoot.GetComponent("MTBIDontKnowLamp"))
            self._devicesToDisconnect.append(self._rl_lamp)

        return self._rl_lamp

    def getObjective(self):
        if self.m_objective is None:
            # self.m_devices[self.m_selected_device_index]
            self.m_objective = ZeissMtbObjective(self.m_MTBRoot, self.m_ID)
            self._devicesToDisconnect.append(self.m_objective)

        return self.m_objective

    def getFocus(self):
        if self.m_focus is None:
            self.m_focus = self.m_MTBRoot.GetComponent("MTBFocus")
            self._devicesToDisconnect.append(self.m_focus)
        return self.m_focus

    def getShutter(self):
        if self.m_shutter is None:
            self.m_shutter = ZeissMtbShutter(self.m_MTBRoot, self.m_ID)
            self._devicesToDisconnect.append(self.m_shutter)
        return self.m_shutter


class ZeissMtbComponent:
    def __init__(self, sdk, device):
        self._zeiss = sdk
        self._device = device

    def getID(self):
        return self._device.ID

    def getName(self):
        return self._device.Name


class ZeissMtbContinual(ZeissMtbComponent):
    """
    "Continual" refers to the general concept of hardware which can be set to a value in a range. Used here
     primarily to encapsulate the event listeners.
    """

    def __init__(self, sdk, device):
        super(ZeissMtbContinual, self).__init__(sdk, device)
        self._eventSink = None
        self._onChange = None
        self._onSettle = None
        self._onReachLimit = None

    def registerEventHandlers(self, onChange=None, onSettle=None, onReachLimit=None):
        # TODO this code doesn't give us event callbacks ever. where's the problem?
        if self._eventSink is not None:
            self.disconnect()
        self._eventSink = MTB.Api.MTBContinualEventSink()

        if onChange is not None:
            self._onChange = onChange
            self._eventSink.MTBPositionChangedEvent += MTB.Api.MTBContinualPositionChangedHandler(onChange)
        if onSettle is not None:
            self._onSettle = onSettle
            self._eventSink.MTBPositionSettledEvent += MTB.Api.MTBContinualPositionSettledHandler(onSettle)
        if onReachLimit is not None and hasattr(self._eventSink, "MTBPHWLimitReachedEvent"):
            self._onReachLimit = onReachLimit
            self._eventSink.MTBPHWLimitReachedEvent += MTB.Api.MTBContinualHWLimitReachedHandler(onReachLimit)

        self._eventSink.ClientID = self._zeiss.getID()
        self._eventSink.Advise(self._device)

    def disconnect(self):
        self._eventSink.Unadvise(self._device)
        if self._onChange is not None:
            self._eventSink.MTBPositionChangedEvent -= MTB.Api.MTBContinualPositionChangedHandler(self._onChange)
        if self._onSettle is not None:
            self._eventSink.MTBPositionSettledEvent -= MTB.Api.MTBContinualPositionSettledHandler(self._onSettle)
        if self._onReachLimit is not None:
            self._eventSink.MTBPHWLimitReachedEvent -= MTB.Api.MTBContinualHWLimitReachedHandler(self._onReachLimit)

        self._eventSink = None

    def getPosition(self):
        # TODO check this for correctness, if it ends up being used
        return self._device.Position

    def setPosition(self, newposition):
        # TODO this probably needs units? if it ends up being used.
        with self._zeiss.threadLock:
            self._device.setPosition(newposition, MTB.Api.MTBCmdSetModes.Default)


class ZeissMtbChanger:
    def __init__(self, root, mtbId, changerName):
        self.m_MTBRoot = root
        self.m_changer = root.GetComponent(changerName)
        self.m_changerName = changerName
        self.m_ID = mtbId
        self.m_changerEvents = None

    def getChanger(self):
        return self.m_changer

    def registerEvents(self, changeEventFunc=defaultOnPositionChanged,
                       positionSettledFunc=defaultOnPositionSettled):
        if self.m_changer is None:
            return

        # Register to Changer events

        if self.m_changerEvents is None:
            self.m_changerEvents = MTB.Api.MTBChangerEventSink()
        else:
            self.disconnect()
            self.m_changerEvents = MTB.Api.MTBChangerEventSink()

        self.onChangerPositionChanged = changeEventFunc
        self.onChangerPositionSettled = positionSettledFunc

        self.m_changerEvents.MTBPositionChangedEvent += MTB.Api.MTBChangerPositionChangedHandler(changeEventFunc)
        self.m_changerEvents.MTBPositionSettledEvent += MTB.Api.MTBChangerPositionSettledHandler(positionSettledFunc)

        self.m_changerEvents.ClientID = self.m_ID
        self.m_changerEvents.Advise(self.m_changer)

    def disconnect(self):
        # print ("Deregistering changer events")
        try:
            self.m_changerEvents.Unadvise(self.m_changer)
            self.m_changerEvents.MTBPositionChangedEvent -= MTB.Api.MTBChangerPositionChangedHandler(
                self.onChangerPositionChanged)
            self.m_changerEvents.MTBPositionSettledEvent -= MTB.Api.MTBChangerPositionSettledHandler(
                self.onChangerPositionSettled)
        except:
            pass

        self.m_changerEvents = None

    def getElementCount(self):
        return self.m_changer.getElementCount()

    def getElement(self, position):
        return self.m_changer.getElement(position)

    def getPosition(self):
        return self.m_changer.Position

    def setPosition(self, newposition):
        with self._zeiss.threadLock:
            self.m_changer.setPosition(newposition, MTB.Api.MTBCmdSetModes.Default)


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
                self._device.SetOnOff(MTB.Api.MTBOnOff.On, MTB.Api.MTBCmdSetModes.Default)
            else:
                self._device.SetOnOff(MTB.Api.MTBOnOff.Off, MTB.Api.MTBCmdSetModes.Default)

    def getIsActive(self):
        return self._device.GetOnOff() == MTB.Api.MTBOnOff.On

    def setBrightness(self, percent):
        with self._zeiss.threadLock:
            self._device.SetPosition(float(percent), "%", MTB.Api.MTBCmdSetModes.Default)

    def getBrightness(self):
        return self._device.GetPosition("%")


class ZeissMtbReflector(ZeissMtbChanger):
    def __init__(self, root, mtbId):
        self.m_MTBRoot = root
        self.m_reflector = root.GetComponent("IMTBReflector")
        self.m_ID = mtbId
        ZeissMtbChanger.__init__(self, root, mtbId, "MTBReflectorChanger")
        self.registerEvents(self.onReflectorPositionChanged, self.onReflectorPositionSettled)

    def onReflectorPositionChanged(self, position):
        print(" Reflector position changed to " + position)

    def onReflectorPositionSettled(self, position):
        print(" Reflector position settled to " + position)

    def getWavelengthArea(self, index):
        return self.m_reflector.getWavelengthArea(index)

    def getWavelengthAreaCount(self):
        return self.m_reflector.getWavelengthAreaCount()

    def contrastMethod(self):
        return self.m_reflector.contrastMethod

    def features(self):
        return self.m_reflector.features


# EVENT HANDLERS
# Not functional yet
""" class ZeissChangerEventSink (ZeissMtbCommon):

    def __init__(self, clientID, changer):
        ZeissMtbCommon.__init__(self)
        #MTB.Api.IMTBChangerEvents.__init__(self, changer)
        self.__dict__["m_changer"] =  changer
        self.__dict__["clientID"] = clientID
        self.m_sink = MTB.Api.MTBChangerEventSink()
        self.m_sink.ClientID = clientID 
        self.m_sink.OnMTBPositionChangedEvent = self.OnMTBPositionChangedEvent
        self.m_sink.OnMTBElementConfigurationChangedEvent = self.OnMTBElementConfigurationChangedEvent
        self.m_sink.OnMTBElementConfigurationFinishedEvent = self.OnMTBElementConfigurationFinishedEvent
        self.m_sink.OnMTBPositionChangedEvent = self.OnMTBPositionChangedEvent
        #self.m_sink.Advise(changer)
        
    def Disconnect(self):
        self.m_sink.Unadvise(self.m_changer)

    def OnMTBPositionChangedEvent(self, Position):
        print ("Position changed: " + Position)

    def OnMTBTargetPositionChangedEvent(self, targetPosition):
        print (targetPosition)

    def OnMTBPositionSettledEvent(self, Position):
        print ("Position changed: " + Position)

    def OnMTBElementConfigurationChangedEvent(self):
        print ("config changed")


    def OnMTBElementConfigurationFinishedEvent(self):
        print ("config finished") """
