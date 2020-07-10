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

# Thread lock for device change info
ZeissDeviceThreadLock = None


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
        self.mainLoopRunning = 0

    def mainLoop(self):
        self.mainLoopRunning = 1
        while self.mainLoopRunning == 1:
            time.sleep(0.1)

    def onMTBServerLoggerEvent(self, logMessage):
        print(logMessage)

    def connect(self):
        global ZeissDeviceThreadLock
        self.m_MTBConnection = MTB.Api.MTBConnection()
        self.m_ID = self.m_MTBConnection.Login("en", "")
        self.m_MTBRoot = self.m_MTBConnection.GetRoot(self.m_ID)
        self.getDevices()
        self.getObjective()
        self.getReflector()
        self.getShutter()

        ZeissDeviceThreadLock = Lock()
        self.m_deviceThread = Thread(target=self.mainLoop)

        # start the thread
        self.m_deviceThread.start()

        return self.m_MTBRoot

    def getID(self):
        return self.m_ID

    def disconnect(self):
        self.m_reflector.disconnect()
        self.m_objective.disconnect()
        self.m_shutter.disconnect()

        print("Logging out..")
        self.m_MTBConnection.Logout(self.m_ID)
        self.mainLoopRunning = 0
        self.m_deviceThread.join()

    def getDevices(self):
        self.m_devices = []
        count = self.m_MTBRoot.GetDeviceCount()
        for i in range(0, count):
            zdevice = self.m_MTBRoot.GetDevice(i)  # ZeissMtbDevice(self.m_MTBRoot, i)
            self.m_devices.append(zdevice)

        return self.m_devices

    def getDeviceComponents(self, device):
        self.m_components = []
        for x in range(0, device.GetComponentCount()):
            self.m_components.append(device.GetComponentFullConfig(x))

        return self.m_components

    def getReflector(self):
        if self.m_reflector is None:
            # self.m_devices[self.m_selected_device_index]
            self.m_reflector = ZeissMtbReflector(self.m_MTBRoot, self.m_ID)

        return self.m_reflector

    def getTLLamp(self):
        if self._tl_lamp is None:
            self._tl_lamp = ZeissMtbLamp(self.m_MTBRoot, self.m_ID, "MTBTLHalogenLamp")

        return self._tl_lamp

    def getRLLamp(self):
        if self._rl_lamp is None:
            self._rl_lamp = ZeissMtbLamp(self.m_MTBRoot, self.m_ID, "MTBIDontKnowLamp")

        return self._rl_lamp

    def getObjective(self):
        if self.m_objective is None:
            # self.m_devices[self.m_selected_device_index]
            self.m_objective = ZeissMtbObjective(self.m_MTBRoot, self.m_ID)

        return self.m_objective

    def getFocus(self):
        if self.m_focus is None:
            self.m_focus = self.m_MTBRoot.GetComponent("MTBFocus")
        return self.m_focus

    def getShutter(self):
        if self.m_shutter is None:
            self.m_shutter = ZeissMtbShutter(self.m_MTBRoot, self.m_ID)
        return self.m_shutter


class ZeissMtbCommon:
    def __init__(self, zeissClass):
        # To extend makepy COM class's internal variables,
        # variables need to be defined into __dict__ in order
        # to be able to use then with self.attr
        self.m_zeissclass = zeissClass
        try:
            self.m_name = zeissClass.Name
        except:
            self.m_name = "Noname"

    def getName(self):
        return self.m_name


class ZeissMtbComponent(ZeissMtbCommon):
    def __init__(self, component):
        # self.m_component = MTB.Api.IMTBComponent()
        self.m_component = component
        ZeissMtbCommon.__init__(self, self.m_component)
        # MTB.Api.IMTBComponent.__init__(self, component)


class ZeissMtbChanger(ZeissMtbCommon):
    def __init__(self, root, mtbId, changerName):
        self.m_MTBRoot = root
        self.m_changer = root.GetComponent(changerName)
        self.m_changerName = changerName
        self.m_ID = mtbId
        self.m_changerEvents = None
        ZeissMtbCommon.__init__(self, self.m_changer)

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
        with ZeissDeviceThreadLock:
            self.m_changer.setPosition(newposition, MTB.Api.MTBCmdSetModes.Default)


class ZeissMtbContinual(ZeissMtbCommon):
    def __init__(self, root, mtbId, continualName):
        self.m_MTBRoot = root
        self.m_continual = root.GetComponent(continualName)
        self.m_continualName = continualName
        self.m_ID = mtbId
        self.m_continualEvents = None
        ZeissMtbCommon.__init__(self, self.m_continual)

    def getContinual(self):
        return self.m_continual

    def registerEvents(self, changeEventFunc=defaultOnPositionChanged,
                       positionSettledFunc=defaultOnPositionSettled,
                       hwLimitReachedFunc=defaultOnHWLimitReached):
        if self.m_continual is None:
            return

        # Register to Changer events

        if self.m_continualEvents is None:
            self.m_continualEvents = MTB.Api.MTBContinualEventSink()
        else:
            self.disconnect()
            self.m_continualEvents = MTB.Api.MTBContinualEventSink()

        self.onContinualPositionChanged = changeEventFunc
        self.onContinualPositionSettled = positionSettledFunc
        self.onContinualHWLimitReached = hwLimitReachedFunc

        self.m_continualEvents.MTBPositionChangedEvent += MTB.Api.MTBContinualPositionChangedHandler(changeEventFunc)
        self.m_continualEvents.MTBPositionSettledEvent += MTB.Api.MTBContinualPositionSettledHandler(
            positionSettledFunc)
        self.m_continualEvents.MTBPHWLimitReachedEvent += MTB.Api.MTBContinualHWLimitReachedHandler(hwLimitReachedFunc)

        self.m_continualEvents.ClientID = self.m_ID
        self.m_continualEvents.Advise(self.m_continual)

    def disconnect(self):
        # print ("Deregistering changer events")
        try:
            self.m_continualEvents.Unadvise(self.m_continual)
            self.m_continualEvents.MTBPositionChangedEvent -= MTB.Api.MTBContinualPositionChangedHandler(
                self.onContinualPositionChanged)
            self.m_continualEvents.MTBPositionSettledEvent -= MTB.Api.MTBContinualPositionSettledHandler(
                self.onContinualPositionSettled)
            self.m_continualEvents.MTBPHWLimitReachedEvent -= MTB.Api.MTBContinualHWLimitReachedHandler(
                self.onContinualHWLimitReached)
        except:
            pass

        self.m_continualEvents = None

    def getElement(self, position):
        return self.m_continual.getElement(position)

    def getPosition(self):
        return self.m_continual.Position

    def setPosition(self, newposition):
        with ZeissDeviceThreadLock:
            self.m_continual.setPosition(newposition, MTB.Api.MTBCmdSetModes.Default)


class ZeissMtbFocus(ZeissMtbCommon):
    def __init__(self, root):
        self.m_component = root.GetComponent("MTBFocus")
        ZeissMtbCommon.__init__(self, self.m_component)

    # ------- ZEISS OBJECTIVE ------


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


class ZeissMtbLamp:
    # MTBRLShutter
    # MTBTLShutter 
    def __init__(self, root, mtbId, lampName):
        self.m_MTBRoot = root
        self.m_ID = mtbId
        self._lamp = root.GetComponent(lampName)

        # self.registerEvents(self.onIsActiveChanged, self.onIsActiveSettled)

    #     self._lampEvents = None
    #     self._registerLampEvents()
    #
    # def _registerLampEvents(self):
    #     if self._lamp is None:
    #         return
    #
    #     # Register to Changer events
    #
    #     if self._lampEvents is None:
    #         self._lampEvents = MTB.Api.MTBLampEventSink()
    #     else:
    #         self.disconnect()
    #         self._lampEvents = MTB.Api.MTBLampEventSink()
    #
    #     self._lampEvents.handleMTBOnOffChangedEvent += MTB.Api.MTBOnOffChangedHandler(lambda state: print(state))
    #     self._lampEvents.MTBLampActiveChangedEvent += MTB.Api.handleMTBLampActiveChanged(lambda active: print(active))
    #     self._lampEvents.MTBPHWLimitReachedEvent += MTB.Api.MTBContinualHWLimitReachedHandler(
    #         defaultOnHWLimitReached)
    #
    #     self.m_continualEvents.ClientID = self.m_ID
    #     self.m_continualEvents.Advise(self.m_continual)

    # def onIsActiveChanged(self, position):
    #     print("{} Lamp changed state to {}".format(self.m_name, position))
    #
    # def onIsActiveSettled(self, position):
    #     print("{} Lamp settled state to {}".format(self.m_name, position))

    def setIsActive(self, isActive):
        if isActive:
            self._lamp.SetOnOff(MTB.Api.MTBOnOff.On, MTB.Api.MTBCmdSetModes.Default)
        else:
            self._lamp.SetOnOff(MTB.Api.MTBOnOff.Off, MTB.Api.MTBCmdSetModes.Default)

    def getIsActive(self):
        return self._lamp.GetOnOff()


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
