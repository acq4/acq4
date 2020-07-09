# Sensapex Seizz SDK Python Wrapper
# All Rights Reserved. Copyright (c) Sensapex Oy 2019
# Author: Ari Salmi
# Version: 0.3
from acq4.drivers.zeiss import ZeissMtbSdk


class ss:
    def __init__(self):
        self.zeiss = ZeissMtbSdk()
        self.mtbRoot = self.zeiss.connect()
        self.zeiss.getObjective().registerEvents(self.objectivePosChanged, self.objectivePosSettled)
        print("Started Zeiss Objective Switch")

    def objectivePosChanged(self, position):
        print("Objective changed: ")

    def objectivePosSettled(self, position):
        print("Objective settled: ")

    def quit(self):
        print("Disconnecting Zeiss")
        self.zeiss.disconnect()

    def getSwitch(self, name):
        print("Get Switch:" + str(name))
        return 0


class ZeissObjectiveSwitch:

    def __init__(self):
        self.zeiss = ZeissMtbSdk()
        self.mtbRoot = self.zeiss.connect()
        self.zeiss.getObjective().registerEvents(self.objectivePosChanged, self.shutterStateSettled)
        # self.zeiss.GetReflector().registerEvents(None, None)
        # self.zeiss.GetShutter().registerEvents(self.shutterStateChanged, self.shutterStateSettled)
        # self.zeiss.GetShutter().RegisterRLShutterEvents(self.rlShutterStateChanged)

    def objectivePosChanged(self, position):
        print("Objective Changed: " + str(position))

    def shutterStateChanged(self, position):
        print("shutter pos settled: " + str(position))

    def shutterStateSettled(self, position):
        print("shutter pos settled: " + str(position))

    def rlShutterStateChanged(self, position):
        print(" RL shutter pos changes: " + str(position))

    def Disconnect(self):
        self.zeiss.disconnect()


class SensapexZeissRLShutter:

    def __init__(self):
        self.zeiss = ZeissMtbSdk()
        self.mtbRoot = self.zeiss.connect()
        self.m_shutter = self.zeiss.getShutter()
        self.zeiss.getShutter().registerEvents(self.shutterStateChanged, self.shutterStateSettled)
        self.zeiss.getShutter().RegisterRLShutterEvents(self.rlShutterStateChanged)

    def shutterStateChanged(self, position):
        print("shutterswitch pos change: " + str(position))

    def shutterStateSettled(self, position):
        print("shutterswitch pos settled: " + str(position))

    def rlShutterStateChanged(self, position):
        print(" RL shutter pos changes: " + str(position))

    def SetRLShutter(self, state):
        self.m_shutter.SetRLShutter(state)

    def GetRLShutter(self):
        return self.m_shutter.GetRLShutter()

    def SetTLShutter(self, state):
        return self.m_shutter.SetRLTLSwitch(state)

    def Disconnect(self):
        self.zeiss.disconnect()


class SensapexZeissTLLamp:

    def __init__(self):
        self.zeiss = ZeissMtbSdk()
        self.mtbRoot = self.zeiss.connect()
        self.m_tl = self.zeiss.getTLLamp()
        self.m_tl.registerEvents(self.tlStateChanged, self.tlStateSettled)

    def tlStateChanged(self, position):
        print("TL switch pos change: " + str(position))

    def tlStateSettled(self, position):
        print("TL switch pos settled: " + str(position))

    def SetTLLamp(self, state):
        self.m_tl.SetTLLamp(state)

    def GetTLLamp(self):
        return self.m_tl.getTLLamp()

    def Disconnect(self):
        self.zeiss.disconnect()


# MAI
# objective = ss()


# shutter = SensapexZeissShutter()

zeiss = ZeissMtbSdk()

root = zeiss.connect()
reflector = zeiss.getReflector()
reflector.SetPosition(1)
print(reflector.GetPosition())

shutter = SensapexZeissRLShutter()  # zeiss.GetShutter()
shutter.SetRLShutter(0)
lamp = SensapexZeissTLLamp()  # zeiss.GetShutter()
print("Changer:")
print(lamp)
print(lamp.GetTLLamp())

devs = zeiss.getDevices()
print(devs)
for d in devs:
    print(d.Name)
    combos = zeiss.getDeviceComponents(d)
    for c in combos:
        print(c.Name)

# def posChanged(position):
#     # in case, the changer position has changed, the current position is printed
#     # a position of "0" indicates an invalid state
#     print("Oma pos changed "+str(position))


# # define changer position settled event
# def posSettled(position):
#     # in case, the changer position is settled, its current position is printed
#     print("Oma pos settled: "+str(position))

# changer =zeiss.GetObjectiveChanger()
# changer.registerEvents(posChanged, posSettled)

# changer.SetPosition(2)
# print (changer.GetPosition())
# print (changer.GetName())
# focus = zeiss.GetFocus()
# print (focus.Name)
# pos = focus.GetPosition("nm")


# #rlshutter = zeiss.GetShutter("MTBRLShutter")
# #tlshutter = zeiss.GetShutter("MTBTLShutter")
# #rltlSwitch = zeiss.GetShutterSwitch()
# #print (rltlSwitch.Position)

loop = 1

while loop:
    print("Waiting")
    print('(0): to exit')
    inputParam = int(input('Input: '))
    if inputParam == 0:
        loop = 0
    if inputParam == 9:
        print(shutter.GetRLShutter())
        print(lamp.GetTLLamp())

    if inputParam == 1:
        print(shutter.SetRLShutter(1))
        print(lamp.SetTLLamp(1))
    if inputParam == 2:
        print(shutter.SetRLShutter(2))
        print(lamp.SetTLLamp(2))
    if inputParam == 3:
        print(lamp.SetTLLamp(1))

    if inputParam == 4:
        print(lamp.SetTLLamp(2))

    # objective = int(input("Stop with 0, Change objective (1-3), Move focus > 100 (100+1 = 1nm):"))
    # if objective <= 3 and objective >=1:
    #    changer.SetPosition(int(objective),32,2000)
    # if objective > 100:
    #    focus.SetPosition(objective-100,"nm",32,5000)
    # if objective == -1:
    #     rlshutter.Expose(1000,0,1)
    # if objective == -2:
    #     tlshutter.Expose(1000,0,1)

    # if int(objective) == 0:
    #    loop = False
    #    break;
print("Disconnecting..")
zeiss.disconnect()
# shutter.Disconnect()
# reflector.Disconnect()
# shutter.Disconnect()
