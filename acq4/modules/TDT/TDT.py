"""
A simple example module.
"""
import time
import numpy as np
from PyQt4 import QtCore, QtGui

from ..Module import Module
from ...import Manager
from ...import pyqtgraph as pg
from ...pyqtgraph import parametertree



class TDT(Module):
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        
        self.win = pg.LayoutWidget()
        
        # Make a panel with a few parameters for the user to configure
        self.params = parametertree.Parameter.create(name='params', type='group',
            children=[
                {'name': 'MinimumFrequency', 'type': 'float', 'value': 4000, 'suffix': 'Hz',
                 'siPrefix': True, 'step': 10e2, 'limits': [1000, 200000]},
                
                {'name': 'FreqStep', 'type': 'float', 'value': 2**0.25, 'step': 0.1, 'limits': [1, 10]},
                
                {'name': 'NumberOfPips', 'type': 'int', 'value': 10, 'limits': [1, None]},
                {'name': 'Direction', 'type': 'list', 'values': ['up', 'down']}
            ])
        self.ptree = parametertree.ParameterTree()
        self.ptree.setParameters(self.params)
        self.win.addWidget(self.ptree, 0, 0)
        
        # Make a button to start
        self.startBtn = QtGui.QPushButton('Start')
        self.win.addWidget(self.startBtn, 1, 0)
        self.startBtn.clicked.connect(self.start)
        
        # Make a plot to display the results
        self.plot = pg.PlotWidget(labels={'left': ('Current', 'A'), 'bottom': ('Time', 's')})
        self.win.addWidget(self.plot, 0, 1, rowspan=2)
        
        self.win.show()
        
    def start(self):
        # The task will control a patch clamp to generate a voltage clamp 
        # pulse and record the membrane current
        
        # Get all the basic parameters we need for this task
        minfreq = self.params['MinimumFrequency']
        fratio = self.params['FreqStep']
        numpips = self.params['NumberOfPips']
        # rate = 50e3
        # samples = int(duration * rate)
        
        # # Make stimulus waveform with a pulse in the middle
        # stim = np.zeros(samples, dtype='float32')
        # stim[samples//3:2*samples//3] = amp

        #Set relevant timing values
        tdur = 50
        # tipi = 200
        # nreps = 1

        # fmin=0.1
        # fstep=0.25
        # fmax = fstep*10
        # flist=np.arange(fmin,fmax,fstep)
        # if flist[9]<fmax:
        #     flist=np.append(flist,fmax)
        # freqs=1000*2**flist
        

        # npip=len(freqs)
        # print('npip = ', npip)
        # schtime=npip*(tdur + tipi)
        # print('schtime = ', schtime)
        # cyctime=schtime + (tdur+tipi)*npip
        # print('cyctime = ', cyctime)

        # print(freqs)
        #direction=input('please enter "up" or "down":')
        #Set the tag values
        #If ascending tone pips:  Set Basefreq to fmin, Stepsize to fstep and Maxfreq to fmax
        #If descending tone pips:  Set Basefreq to fmax, Stepsize to -fstep and MaxFreq to fmin

        # circuit calculates frequencies as 1000 * 2^(base + step*i)
        base = np.log2(minfreq/1000.)
        fstep = np.log2(fratio)
        fmax = (base + fstep * (numpips-1))

        freqs = 1000 * 2**(base + fstep * np.arange(numpips))
        print("Expected frequencies: ", freqs)

        direction = 'up'
        if direction=='up':
            tags = {
            'BaseFreq': base, 
            'StepSize': fstep,
            'MaxFreq': fmax,
            'PipDuration': tdur,
            'NPip': numpips,
            }
        elif direction=='down':
            tags = {
            'BaseFreq': fmax, 
            'StepSize': -1*fstep,
            'MaxFreq': base,  
            'PipDuration': tdur,
            'NPip': numpips,
            }
        else:
            raise ValueError("direction must be 'up' or 'down'.")
  
        
        cmd = {
            'protocol': {'duration': 0, 'store': False},
            # 'DAQ':      {'rate': rate, 'numPts': samples},
            'TDTDevice': {

                'RP2.1': {'circuit': 'C:\Users\Experimenters\Desktop\ABR_Code\FreqStaircase3.rcx', 'tags': tags},
                'PA5.1': {'attenuation': 50}
            }
        }
        
        manager = Manager.getManager()
        task = manager.createTask(cmd)
        print("execute")
        task.execute(block=False)
        
        # Wait until task completes and process Qt events to keep the GUI
        # responsive during that time 
        while not task.isDone():
            print("not done yet", task.tasks['TDTDevice'].circuit.get_tag('freqout'))
            QtGui.QApplication.processEvents()
            time.sleep(0.05)

        # Plot the results
        result = task.getResult()
        # result = task.getResult()['Clamp1']
        # x = result.xvals('Time')
        # y = result['Channel': 'primary']
        # self.plot.plot(x, y, clear=True)
        # 