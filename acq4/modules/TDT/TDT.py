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
                
                {'name': 'FreqStep', 'type': 'float', 'value': 2.5, 'step': 10e-3, 'limits': [1e-3, 100e-3]},
                
                {'name': 'NumberOfSteps', 'type': 'int', 'value': 10, 'limits': [1, None]},

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
        fstep = self.params['FreqStep']
        numsteps = self.params['NumberOfSteps']
        # rate = 50e3
        # samples = int(duration * rate)
        
        # # Make stimulus waveform with a pulse in the middle
        # stim = np.zeros(samples, dtype='float32')
        # stim[samples//3:2*samples//3] = amp
        
        cmd = {
            'protocol': {'duration': 0, 'store': False},
            # 'DAQ':      {'rate': rate, 'numPts': samples},
            'TDTDevice':{}
        }
        
        manager = Manager.getManager()
        task = manager.createTask(cmd)
        print("execute")
        task.execute(block=False)
        
        # Wait until task completes and process Qt events to keep the GUI
        # responsive during that time 
        while not task.isDone():
            print("not done yet")
            QtGui.QApplication.processEvents()
            time.sleep(0.05)

        # Plot the results
        result = task.getResult()
        # result = task.getResult()['Clamp1']
        # x = result.xvals('Time')
        # y = result['Channel': 'primary']
        # self.plot.plot(x, y, clear=True)
        # 