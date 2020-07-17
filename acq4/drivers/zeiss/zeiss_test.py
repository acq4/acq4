# Sensapex Seizz SDK Python Wrapper
# All Rights Reserved. Copyright (c) Sensapex Oy 2019
# Author: Ari Salmi
# Version: 0.3
from acq4.drivers.zeiss import ZeissMtbSdk


class ss:
    def __init__(self):
        self.zeiss = ZeissMtbSdk.getSingleton()
        self.mtbRoot = self.zeiss.connect()
        self.zeiss.getObjective().registerEventHandlers(self.objectivePosChanged, self.objectivePosSettled)
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
        self.zeiss = ZeissMtbSdk.getSingleton()
        self.mtbRoot = self.zeiss.connect()
        self.zeiss.getObjective().registerEventHandlers(self.objectivePosChanged, self.shutterStateSettled)
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

    def disconnect(self):
        self.zeiss.disconnect()


zeiss = ZeissMtbSdk.getSingleton()

for dev, compos in zeiss.getComponentsByDevice().items():
    print(dev.Name)
    for c in compos:
        print(c.ID, c.Name)

def notice(value):
    print("we have a new value", value)

lamp = zeiss.getTLLamp()
lamp.registerEventHandlers(onChange=notice, onSettle=notice)
print("Transmissive Lamp:")
print(lamp)
print(lamp.getIsActive())
lamp.setBrightness(lamp.getBrightness() / 2)
lamp.setBrightness(lamp.getBrightness() * 2)

reflector = zeiss.getReflectorChanger()
reflector.setPosition(1)
print(reflector.getPosition())

shutter = zeiss.getShutter()
shutter.setRLShutter(0)

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
        print(shutter.getRLShutter())
        print(lamp.getIsActive())

    if inputParam == 1:
        print(shutter.setRLShutter(1))
        print(lamp.setIsActive(True))
    if inputParam == 2:
        print(shutter.setRLShutter(2))
        print(lamp.setIsActive(False))
    if inputParam == 3:
        print(lamp.setIsActive(True))

    if inputParam == 4:
        print(lamp.setIsActive(False))

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
