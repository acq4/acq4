from __future__ import print_function
import os, sys, user
md = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(md, '..'))

import acq4.pyqtgraph as pg
import acq4.util.SequenceRunner as SequenceRunner
from acq4.util import Qt
if not hasattr(QtCore, 'Signal'):
    Qt.Signal = Qt.pyqtSignal
from .StimGenerator import *
app = Qt.QApplication([])
sg = StimGenerator()
sg.show()

sg.setMeta('x', units='s', dec=True, minStep=1e-6, step=0.5, siPrefix=True)
sg.setMeta('y', units='W', dec=True, minStep=1e-3, step=0.5, siPrefix=True)
sg.setMeta('xy', units='J', dec=True, minStep=1e-9, step=0.5, siPrefix=True)

plot = pg.PlotWidget()
plot.show()

def plotData():
    rate = 1e3
    nPts = 100
    plot.clear()

    params = {}
    paramSpace = sg.listSequences()
    for k in paramSpace:
        params[k] = range(len(paramSpace[k]))

    global seqPlots
    seqPlots = []
    SequenceRunner.runSequence(lambda p: seqPlots.append(sg.getSingle(rate, nPts, p)), params, list(params.keys()))
    
    for i, w in enumerate(seqPlots):
        if w is not None:
            plot.plot(w, pen=pg.intColor(i, len(seqPlots)*1.5))

    data = sg.getSingle(rate, nPts)
    plot.plot(data, pen=pg.mkPen('w', width=2))


sg.sigDataChanged.connect(plotData)


sg.loadState({
    'advancedMode': True,
    'function': 'pulse(30*ms, 15*ms, amp)',
    'params': {
        'amp':  {
            'default': '10*mV',
            'sequence': 'range',
            'start': '20*mV',
            'stop': '30*mV',
            'steps': 5
        }
    }
})
state1 = sg.saveState()

sg.loadState({
    'advancedMode': False,
    'stimuli': {
        'pulse': {
            'type': 'pulseTrain',
            'start': {
                'value': 0.0,
                'sequence': 'off'},
            'length': {
                'value': 0.002,
                'sequence': 'off'},
            'amplitude': {
                'value': 0.1,
                'sequence': 'off'},
            'interpulse_length': {
                'value': 0.01,
                'sequence': 'off',
                },
            'pulse_number': {
                'value': 3,
                'sequence': 'range',
                'start': 3,
                'stop': 8,
                'steps': 6
                }
            }
            
        }
    }
)
                



if sys.flags.interactive == 0:
    app.exec_()