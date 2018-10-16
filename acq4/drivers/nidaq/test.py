#!/cygdrive/c/Python25/python.exe
# -*- coding: utf-8 -*-
## Workaround for symlinks not working in windows
from __future__ import print_function
print("Starting up..")

import sys, time, os
import numpy as np
modPath = os.path.split(__file__)[0]
acq4Path = os.path.abspath(os.path.join(modPath, '..', '..', '..'))
utilPath = os.path.join(acq4Path, 'lib', 'util')
sys.path = [acq4Path, utilPath] + sys.path
from .nidaq import LIB as lib
import acq4.util.ptime as ptime


if sys.argv[-1] == 'mock':
    from .mock import NIDAQ as n
else:
    from .nidaq import NIDAQ as n


print("Assert num devs > 0:")
assert(len(n.listDevices()) > 0)
print("  OK")
print("devices: %s" % n.listDevices())
dev = n.listDevices()[0]

print("\nAnalog Channels:")
print("  AI: ", n.listAIChannels(dev))
print("  AO: ", n.listAOChannels(dev))

print("\nDigital ports:")
print("  DI: ", n.listDIPorts(dev))
print("  DO: ", n.listDOPorts(dev))

print("\nDigital lines:")
print("  DI: ", n.listDILines(dev))
print("  DO: ", n.listDOLines(dev))


def finiteReadTest():
    print("::::::::::::::::::  Analog Input Test  :::::::::::::::::::::")
    task = n.createTask()
    task.CreateAIVoltageChan("/Dev1/ai0", "", n.Val_RSE, -1., 1., n.Val_Volts, None)
    task.CreateAIVoltageChan("/Dev1/ai1", "", n.Val_Cfg_Default, -10., 10., n.Val_Volts, None)
    
    task.CfgSampClkTiming(None, 10000.0, n.Val_Rising, n.Val_FiniteSamps, 1000)
    task.start()
    data = task.read()
    task.stop()
    
    return data



def contReadTest():
    print("::::::::::::::::::  Continuous Read Test  :::::::::::::::::::::")
    task = n.createTask()
    task.CreateAIVoltageChan("/Dev1/ai0", "", n.Val_RSE, -10., 10., n.Val_Volts, None)
    task.CfgSampClkTiming(None, 10000.0, n.Val_Rising, n.Val_ContSamps, 4000)
    task.start()
    t = ptime.time()
    for i in range(0, 10):
        data, size = task.read(1000)
        print("Cont read %d - %d samples, %fsec" % (i, size, ptime.time() - t))
        t = ptime.time()
    task.stop()


## Output task

def outputTest():
    print("::::::::::::::::::  Analog Output Test  :::::::::::::::::::::")
    task = n.createTask()
    task.CreateAOVoltageChan("/Dev1/ao0", "", -10., 10., n.Val_Volts, None)
    task.CfgSampClkTiming(None, 10000.0, n.Val_Rising, n.Val_FiniteSamps, 1000)
    
    data = np.zeros((1000,), dtype=np.float64)
    data[200:400] = 5.0
    data[600:800] = 5.0
    task.write(data)
    task.start()
    time.sleep(0.2)
    task.stop()
    



## Synchronized tasks

def syncADTest():
    print("::::::::::::::::::  A/D  Test  :::::::::::::::::::::")
    task1 = n.createTask()
    task1.CreateAIVoltageChan("/Dev1/ai0", "", n.Val_RSE, -10., 10., n.Val_Volts, None)
    task1.CfgSampClkTiming(None, 10000.0, n.Val_Rising, n.Val_FiniteSamps, 100)
    task2 = n.createTask()
    task2.CreateDIChan("/Dev1/port0", "", n.Val_ChanForAllLines)
    task2.CfgSampClkTiming("/Dev1/ai/SampleClock", 10000.0, n.Val_Rising, n.Val_FiniteSamps, 100)
    
    print(task2.GetTaskChannels())
    task2.start()
    task1.start()
    data1 = task1.read()
    data2 = task2.read()
    task2.stop()
    task1.stop()
    
    print(data1[0].shape, data1[0].dtype)
    print(data1)
    print(data2[0].shape, data2[0].dtype)
    print(data2)

def syncAIOTest():
    print("::::::::::::::::::  Sync Analog I/O Test  :::::::::::::::::::::")
    task1 = n.createTask()
    task1.CreateAIVoltageChan("/Dev1/ai0", "", n.Val_RSE, -10., 10., n.Val_Volts, None)
    task1.CfgSampClkTiming("/Dev1/ao/SampleClock", 10000.0, n.Val_Rising, n.Val_FiniteSamps, 100)

    task2 = n.createTask()
    task2.CreateAOVoltageChan("/Dev1/ao0", "", -10., 10., n.Val_Volts, None)
    #task2.CfgSampClkTiming(None, 10000.0, nidaq.Val_Rising, nidaq.Val_FiniteSamps, 1000)
    task2.CfgSampClkTiming(None, 10000.0, n.Val_Rising, n.Val_FiniteSamps, 100)
    #task2.CfgDigEdgeStartTrig("ai/StartTrigger", nidaq.Val_Rising)
    


    data1 = np.zeros((100,), dtype=np.float64)
    data1[20:40] = 7.0
    data1[60:80] = 5.0
    print("  Wrote ao samples:", task2.write(data1))
    task1.start()
    task2.start()
    
    data2 = task1.read()
    #time.sleep(1.0)
    task1.stop()
    task2.stop()
    
    print("  Data acquired:", data2[0].shape)
    return data2


def syncIOTest():
    print("::::::::::::::::::  Sync I/O Test  :::::::::::::::::::::")
    task1 = n.createTask()
    task1.CreateAIVoltageChan("/Dev1/ai0", "", n.Val_RSE, -10., 10., n.Val_Volts, None)
    task1.CfgSampClkTiming(None, 10000.0, n.Val_Rising, n.Val_FiniteSamps, 100)

    task2 = n.createTask()
    task2.CreateAOVoltageChan("/Dev1/ao0", "", -10., 10., n.Val_Volts, None)
    #task2.CfgSampClkTiming(None, 10000.0, nidaq.Val_Rising, nidaq.Val_FiniteSamps, 1000)
    task2.CfgSampClkTiming("/Dev1/ai/SampleClock", 10000.0, n.Val_Rising, n.Val_FiniteSamps, 100)
    #task2.CfgDigEdgeStartTrig("ai/StartTrigger", nidaq.Val_Rising)
    
    task3 = n.createTask()
    task3.CreateDIChan("/Dev1/port0/line0", "", n.Val_ChanForAllLines)
    task3.CfgSampClkTiming("/Dev1/ai/SampleClock", 10000.0, n.Val_Rising, n.Val_FiniteSamps, 100)
    
    task4 = n.createTask()
    task4.CreateDOChan("/Dev1/port0/line4", "", n.Val_ChanForAllLines)
    task4.CfgSampClkTiming("/Dev1/ai/SampleClock", 10000.0, n.Val_Rising, n.Val_FiniteSamps, 100)
    
    
    
    #task1.SetRefClkSrc("PXI_Clk10")
    #task2.SetRefClkSrc("PXI_Clk10")
    #print task1.GetSampClkTimebaseSrc()
    #print task2.GetSampClkTimebaseSrc()
    #task2.SetSampClkTimebaseSrc("SampleClockTimebase")
    #task2.SetSyncPulseSrc("/Dev1/SyncPulse")


    data1 = np.zeros((100,), dtype=np.float64)
    data1[20:40] = 7.0
    data1[60:80] = 5.0
    print("Wrote ao samples:", task2.write(data1))
    print("Wrote do samples:", task4.write(data1.astype(uint32)))
    task2.start()
    task3.start()
    task1.start()
    data2 = task1.read()
    data3 = task3.read()
    #time.sleep(1.0)
    task1.stop()
    task2.stop()
    task3.stop()
    
    print("Data acquired:")
    print(data2[0].shape)
    print(data3[0].shape)
    return data2



def triggerTest():
    task = n.createTask()
    task.CreateAIVoltageChan("/Dev1/ai0", "", n.Val_RSE, -1., 1., n.Val_Volts, None)
    task.CreateAIVoltageChan("/Dev1/ai1", "", n.Val_Cfg_Default, -10., 10., n.Val_Volts, None)
    
    task.CfgSampClkTiming(None, 10000.0, n.Val_Rising, n.Val_FiniteSamps, 1000)
    task.CfgDigEdgeStartTrig("/Dev1/PFI5", n.Val_Rising)
    print("Waiting for trigger..")
    
    task.start()
    data = task.read()
    task.stop()
    
    return data

  

st = n.createSuperTask()
def superTaskTest():
    print("::::::::::::::::::  SuperTask  Test  :::::::::::::::::::::")

    st.addChannel('/Dev1/ai8', 'ai')
    st.addChannel('/Dev1/ai9', 'ai')
    st.addChannel('/Dev1/ao0', 'ao')
    st.addChannel('/Dev1/ao1', 'ao')
    st.addChannel('/Dev1/port0/line2', 'di')
    st.addChannel('/Dev1/port0/line3', 'di')
    st.addChannel('/Dev1/port0/line4', 'do')
    st.addChannel('/Dev1/port0/line5', 'do')

    ao = zeros((2, 1000))
    ao[0, 200:300] = 1.0
    ao[1, 400:500] = 2.0
    st.setWaveform('/Dev1/ao0', ao[0])
    st.setWaveform('/Dev1/ao1', ao[1])

    do = zeros((2, 1000), dtype=uint32)
    do[0, 600:700] = 15
    do[1, 700:800] = 15
    st.setWaveform('/Dev1/port0/line4', do[0])
    st.setWaveform('/Dev1/port0/line5', do[1])

    st.configureClocks(rate=10000, nPts=1000)
    
    #st.setTrigger('/Dev1/PFI5')
    
    
    data = st.run()
    print("waiting for trigger..")
    
    #for ch in data['chans']:
        #print "Channel:", ch
        #task = data['chans'][ch]['task']
        #ind = data['chans'][ch]['index']
        #print "Data:", data[task]['data'][0][ind]
    
    for k in data:
        print("=====Output", k)
        #print data
        #print data[k][0][:, ::20].round()
        print(data[k]['data'])
    return data

def analogSuperTaskTest():
    print("::::::::::::::::::  Analog SuperTask  Test  :::::::::::::::::::::")

    st.addChannel('/Dev1/ai8', 'ai')
    st.addChannel('/Dev1/ai9', 'ai')
    st.addChannel('/Dev1/ao0', 'ao')
    st.addChannel('/Dev1/ao1', 'ao')

    ao = np.zeros((2, 1000))
    ao[0, 200:300] = 1.0
    ao[1, 400:500] = 2.0
    st.setWaveform('/Dev1/ao0', ao[0])
    st.setWaveform('/Dev1/ao1', ao[1])

    st.configureClocks(rate=10000, nPts=1000)
    
    #st.setTrigger('/Dev1/PFI5')
    
    
    data = st.run()
    print("waiting for trigger..")
    
    for k in data:
        print("=====Output", k)
        #print data
        #print data[k][0][:, ::20].round()
        print(data[k]['data'])
    return data
    

data = finiteReadTest()
outputTest()
syncAIOTest()
contReadTest()
#syncIOTest()
#syncADTest()
#triggerTest()
#data = superTaskTest()
analogSuperTaskTest()


