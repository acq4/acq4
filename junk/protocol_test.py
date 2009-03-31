# -*- coding: utf-8 -*-


RunProtocol():
    duration = 0.25
    protoSettings = {'mode': 'single', 'time': duration, 'name': 'TestProtocol', 'storeData': True, 'writeLocation': '...', 'startOrder': ['daq', 'cam']}
    
    rate = 40000
    daqSettings = {'rate': rate, 'numPts': duration * rate, 'startTriggerDev': 'cam'}
    
    cellSig = stim(t=[0.0, 0.01, 0.2], v=[0.0, 10e-3, 0.0])
    clampSettings = {'mode': 'ic', 'bridge': 10e6, 'recordState': True, cmd=cellSig, 'record': 'MembranePotential'}
    
    stimSig = stim(t=[0.0, 0.009, 0.0091], v=[0.0, 0.1, 0.0])

    cmd = {
        'protocol': protoSettings,
        'daq': daqSettings,
        'Clamp0': clampSettings,
        'stim': {'cmd': stimSig},
        'cam': {'record': True, 'trigger': True},
        'led-blue': {'on': True, 'duty': 0.6},
    }
    
    data = mgr.runProtocol(cmd)

    ui.plot(data['clamp0'], pos=0)
    ui.plot(cellSig, pos=1)
}
