import time
import numpy as np
from PyQt4 import QtGui, QtCore

from acq4.modules.Module import Module
import acq4.pyqtgraph as pg


class NoiseMonitor(Module):
    """ Used to monitor electrical noise over long time periods.
    """
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config) 
        
        self.recordDir = None
        
        self.win = pg.LayoutWidget()
        
        self.startBtn = QtGui.QPushButton('Start')
        self.stopBtn = QtGui.QPushButton('Stop')
        self.win.addWidget(self.startBtn, 0, 0)
        self.win.addWidget(self.stopBtn, 0, 1)
        self.startBtn.clicked.connect(self.start)
        self.stopBtn.clicked.connect(self.stop)
        
        self.plot1 = pg.PlotWidget(labels={'left': ('Channel 1', 'V'), 'bottom': ('Time', 's')})
        self.plot2 = pg.PlotWidget(labels={'left': ('Channel 2', 'V'), 'bottom': ('Time', 's')})
        self.win.addWidget(self.plot1, 1, 0, 1, 2)
        self.win.addWidget(self.plot2, 2, 0, 1, 2)
        
        self.spectrogram = pg.ImageView()
        self.envelopePlot = pg.PlotWidget()
        self.win.addWidget(self.spectrogram, 0, 2, 2, 1)
        self.win.addWidget(self.envelopePlot, 2, 2, 1, 1)
        self.win.show()
        
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.runOnce)
        
        
    def start(self):
        self.recordDir = self.manager.getCurrentDir().mkdir('NoiseMonitor', autoIncrement=True)
        
        self.rawDataFile = None
        self.envelopeFile = None
        self.spectrogramFile = None
        self.startTime = time.time()
        
        self.timer.start(1000)
        
    def stop(self):
        self.timer.stop()

    def runOnce(self):
        dur = 0.02
        rate = 10000
        npts = int(dur * rate)
        cmd = {
            'protocol': {'duration': dur},
            'DAQ': {'rate': rate, 'numPts': npts},
            'Clamp1': {'mode': 'vc', 'holding': 0, 'command': np.zeros(npts)},
        }
        task = self.manager.createTask(cmd)
        task.execute()
        result = task.getResult()
        
        
        # Raw data plot/storage
        data = result['Clamp1']['Channel': 'primary']
        dataArr = data.asarray() + np.random.normal(size=data.shape[0], scale=1e-9)
        self.plot1.plot(data.xvals('Time'), dataArr, clear=True)
        trialArr = np.array([time.time() - self.startTime])
        ma = pg.metaarray.MetaArray(dataArr[np.newaxis, :], info=[
            {'name': 'Trial', 'units': 's', 'values': trialArr}] + data._info)

        if self.rawDataFile is None:
            self.rawDataFile = self.recordDir.writeFile(ma, 'rawData', appendAxis='Trial', newFile=True)
        else:
            ma.write(self.rawDataFile.name(), appendAxis='Trial')


        # Envelope analysis
        envData = np.array([[dataArr.min(), dataArr.mean(), dataArr.max(), dataArr.std()]])
        env = pg.metaarray.MetaArray(envData, info=[
            {'name': 'Trial', 'units': 's', 'values': trialArr},
            {'name': 'Metric', 'units': 'V'}])
        if self.envelopeFile is None:
            self.envelopeFile = self.recordDir.writeFile(env, 'envelope', appendAxis='Trial', newFile=True)
        else:
            env.write(self.envelopeFile.name(), appendAxis='Trial')

        envelope = self.envelopeFile.read()
        envArr = envelope.asarray()
        self.envelopePlot.clear()
        grey = (255, 255, 255, 100)
        c1 = self.envelopePlot.plot(envelope.xvals('Trial'), envArr[:,0], pen=grey)  # min
        c2 = self.envelopePlot.plot(envelope.xvals('Trial'), envArr[:,2], pen=grey)  # max
        fill = pg.FillBetweenItem(c1, c2, grey)
        self.envelopePlot.addItem(fill)
        c1 = self.envelopePlot.plot(envelope.xvals('Trial'), envArr[:,1] + envArr[:,3], pen=grey)  # +std
        c2 = self.envelopePlot.plot(envelope.xvals('Trial'), envArr[:,1] - envArr[:,3], pen=grey)  # -std
        fill = pg.FillBetweenItem(c1, c2, grey)
        self.envelopePlot.addItem(fill)

        self.envelopePlot.plot(envelope.xvals('Trial'), envArr[:,1])  # mean

        # Spectrum analysis
        fft = np.abs(np.fft.fft(dataArr))
        fft = fft[:len(fft)/2]
        freqArr = np.linspace(0, rate/2., len(fft))
        spec = pg.metaarray.MetaArray(fft[np.newaxis, :], info=[
            {'name': 'Trial', 'units': 's', 'values': trialArr},
            {'name': 'Frequency', 'units': 'Hz', 'values': freqArr}])
        if self.spectrogramFile is None:
            self.spectrogramFile = self.recordDir.writeFile(spec, 'spectrogram', appendAxis='Trial', newFile=True)
            auto = True
        else:
            spec.write(self.spectrogramFile.name(), appendAxis='Trial')
            auto = False
            
        specArr = self.spectrogramFile.read().asarray()
        self.spectrogram.setImage(specArr, autoLevels=auto)

        
    def quit(self):
        self.stop()
        Module.quit(self)

    


