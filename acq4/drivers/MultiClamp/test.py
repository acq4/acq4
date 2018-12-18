import time
from acq4.drivers.MultiClamp import MultiClamp
mc = MultiClamp.instance()

chans = mc.listChannels()
print("Available channels: %s" % chans)

recordParams = [
    'Holding', 'HoldingEnable', 'PipetteOffset', 'FastCompCap', 'SlowCompCap', 'FastCompTau', 'SlowCompTau', 
    'NeutralizationEnable', 'NeutralizationCap', 'WholeCellCompEnable', 'WholeCellCompCap', 'WholeCellCompResist', 
    'RsCompEnable', 'RsCompBandwidth', 'RsCompCorrection', 'PrimarySignalLPF', 'PrimarySignalHPF', 'OutputZeroEnable', 
    'OutputZeroAmplitude', 'LeakSubEnable', 'LeakSubResist', 'BridgeBalEnable', 'BridgeBalResist']

for ch in chans:
    mcchan = mc.getChannel(ch)
    time.sleep(1.0)
    print("\n========= %s ========" % ch)
    state = mcchan.getState()
    for k, v in state.items():
        print("%s : %s" % (k, v))
    state = mcchan.getParams(recordParams)
    for k, v in state.items():
        print("%s : %s" % (k, v))
