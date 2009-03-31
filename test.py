#!/usr/bin/python
# -*- coding: utf-8 -*-

from lib.DeviceManager import *
import lib.DataManager as DataManager
import os, sys
from numpy import *

config = 'config/default.cfg'
if len(sys.argv) > 1:
    config = sys.argv[1]
config = os.path.abspath(config)

dm = DeviceManager(config)
datam = DataManager.createDataHandler('junk/data')

duration = 0.25
protoSettings = {'mode': 'single', 'time': duration, 'name': 'TestProtocol', 'storeData': True, 'writeLocation': '...'}

rate = 10000
nPts = int(duration * rate)
daqSettings = {'rate': rate, 'numPts': nPts, 'triggerDevice': 'Camera'}
#daqSettings = {'rate': rate, 'numPts': nPts}

#cellSig = stim(t=[0.0, 0.01, 0.2], v=[0.0, 10e-3, 0.0])
cellSig = zeros((nPts))
cellSig[3000:5000] = 100.0e-12
cellSig[5000:7000] = 200.0e-12
clampSettings = {'mode': 'IC', 'bridge': 10e6, 'recordState': True, 'cmd': cellSig, 'inp': 'MembranePotential', 'raw': 'MembraneCurrent'}

#stimSig = stim(t=[0.0, 0.009, 0.0091], v=[0.0, 0.1, 0.0])

cmd = {
    'protocol': protoSettings,
    'DAQ': daqSettings,
    'Clamp0': clampSettings,
    'Clamp1': clampSettings,
    #'stim': {'cmd': stimSig},
    'Camera': {'record': True, 'trigger': True, 'recordExposeChannel': True},
    #'led-blue': {'on': True, 'duty': 0.6},
}

print "\nRunning protocol.."
data = dm.runProtocol(cmd)

dataDir = datam.getDir('protocol', autoIncrement=True)
dataDir.write(data, info={'protocol': 'test'})

print "\n== Results =="
for dev in ['Clamp0', 'Clamp1']:
    print "\n", dev, ":"
    print "Command:"
    print data[dev]['cmd']['data'][::100].round()
    print "Input:"
    print data[dev]['inp']['data'][::100].round()
    print "Raw:"
    print data[dev]['raw']['data'][::100].round()
    print "MultiClamp state:"
    print data[dev]['info']
    print "Start time:"
    print data[dev]['startTime'] + dm.startTime

print "\nCamera:"
print "Acquired %d frames" % len(data['Camera']['frames'])
print "Frame 0 info:", data['Camera']['frames'][0][1]
print "Expose signal:", data['Camera']['expose']['data'][::10]
#ui.plot(data['clamp0'], pos=0)
#ui.plot(cellSig, pos=1)


print "\nShutting down.."
dm.quit()