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
datam = DataManager.createDataHandler('junk/data', create=True)

duration = 0.25
protoSettings = {'mode': 'single', 'time': duration, 'name': 'TestProtocol', 'storeData': True, 'writeLocation': '...'}

rate = 10000
nPts = int(duration * rate)
daqSettings = {'rate': rate, 'numPts': nPts, 'triggerDevice': 'Camera'}
#daqSettings = {'rate': rate, 'numPts': nPts}

#cellSig = stim(t=[0.0, 0.01, 0.2], v=[0.0, 10e-3, 0.0])
cellSig = zeros((nPts))
cellSig[1000:1500] = 100.0e-12
cellSig[1700:2000] = 200.0e-12
clampSettings = {'mode': 'IC', 'bridge': 10e6, 'recordState': True, 'cmd': cellSig, 'inp': 'MembranePotential', 'raw': 'MembraneCurrent'}

#stimSig = stim(t=[0.0, 0.009, 0.0091], v=[0.0, 0.1, 0.0])
stimSig = zeros((nPts))
stimSig[1000:1100] = 10e-6

cmd = {
    'protocol': protoSettings,
    'DAQ': daqSettings,
    'Clamp0': clampSettings,
    'Clamp1': clampSettings,
    #'stim': {'cmd': stimSig},
    'Camera': {'record': True, 'trigger': True, 'recordExposeChannel': True},
    'LED-Blue': {'Command': {'preset': 1}},
    'Stim0': {'Command': {'cmd': stimSig}}
}

print "\nRunning protocol.."
data = dm.runProtocol(cmd)

dataDir = datam.mkdir('protocol', autoIndex=True)
#dataDir.writeFile(data, info={'protocol': 'test'})

print "\n== Results =="

for dev in ['Clamp0', 'Clamp1']:
    print "\n", dev, ":"
    for col in data[dev]._info[0]['cols']:
        cn = col['name']
        print cn, ":"
        print data[dev][cn][::100]
    print "STATE:"
    print data[dev]._info[-1]
    
print "\nCamera:"
print "Acquired %d frames" % len(data['Camera']['frames'])
print "Frame 0 info:", data['Camera']['frames'][0][1]
print "Expose signal:", data['Camera']['expose'][::10]

#ui.plot(data['clamp0'], pos=0)
#ui.plot(cellSig, pos=1)


print "\nShutting down.."
dm.quit()