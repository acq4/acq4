import time
import numpy as np
from PyQt4 import QtGui, QtCore

from acq4.modules.Module import Module
from acq4.util.DataManager import getDirHandle
import acq4.pyqtgraph as pg


class NoiseMonitor(Module):
    """ Used to monitor electrical noise over long time periods.
    """
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config) 
        
        self.recordDir = None
        self.recordWritable = False
        self.resetDisplay = False
        self.showNewRecords = True
        self.interval = 0.5
        
        self.win = QtGui.QSplitter()
        
        self.ctrlWidget = pg.LayoutWidget()
        self.win.addWidget(self.ctrlWidget)
        self.newBtn = QtGui.QPushButton('New Record')
        self.loadBtn = QtGui.QPushButton('Load Record')
        self.startBtn = QtGui.QPushButton('Start')
        self.startBtn.setCheckable(True)
        self.fileLabel = QtGui.QLabel()
        self.ctrlWidget.addWidget(self.newBtn, 0, 0)
        self.ctrlWidget.addWidget(self.loadBtn, 1, 0)
        self.ctrlWidget.addWidget(self.startBtn, 2, 0)
        self.ctrlWidget.addWidget(self.fileLabel, 3, 0)
        self.newBtn.clicked.connect(self.newRecord)
        self.loadBtn.clicked.connect(self.loadClicked)
        self.startBtn.toggled.connect(self.startToggled)
        
        self.channelLayout = pg.LayoutWidget()
        self.win.addWidget(self.channelLayout)
        
        self.channelSplitter = QtGui.QSplitter(QtCore.Qt.Vertical)
        self.channelLayout.addWidget(self.channelSplitter, 0, 0)
        
        self.plot = pg.PlotWidget(labels={'left': ('Channel 1', 'A'), 'bottom': ('Time', 's')})
        self.channelSplitter.addWidget(self.plot)
        
        self.envelopePlot = pg.PlotWidget(labels={'left': ('Channel 1', 'A'), 'bottom': ('Time', 's')})
        self.channelSplitter.addWidget(self.envelopePlot)
        
        self.specView = pg.PlotItem(labels={'left': ('Frequency', 'Hz'), 'bottom': ('Time', 's')})
        self.spectrogram = pg.ImageView(view=self.specView)
        self.specView.setAspectLocked(False)
        self.spectrogram.imageItem.setAutoDownsample(True)
        self.channelSplitter.addWidget(self.spectrogram)
        
        self.channelSplitter.setStretchFactor(0, 10)
        self.channelSplitter.setStretchFactor(1, 15)
        self.channelSplitter.setStretchFactor(2, 30)
        
        self.specLine = pg.InfiniteLine()
        self.spectrogram.addItem(self.specLine)
        
        self.envLine = pg.InfiniteLine(movable=True)
        self.envelopePlot.addItem(self.envLine)
        self.envLine.sigDragged.connect(self.lineDragged)
        
        self.win.show()
        
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.runOnce)
        
    def startToggled(self, start):
        if start:
            try:
                if self.recordDir is None or not self.recordWritable:
                    self.newRecord()
                self.timer.start(self.interval * 1000)
            except:
                self.startBtn.setChecked(False)
                raise
            
            self.startBtn.setText('Stop')
        else:
            self.timer.stop()
            self.startBtn.setText('Start')

    def newRecord(self):
        self.recordDir = self.manager.getCurrentDir().mkdir('NoiseMonitor', autoIncrement=True)
        self.recordWritable = True
        self.rawDataFile = None
        self.envelopeFile = None
        self.spectrogramFile = None
        self.startTime = time.time()
        self.resetDisplay = True
        
    def loadClicked(self):
        self.recordWritable = False
        try:
            startDir = self.manager.getCurrentDir()
        except Exception:
            startDir = self.manager.getBaseDir()
        dirname = QtGui.QFileDialog.getExistingDirectory(self.win, "Open Record", startDir.name())
        if dirname == '':
            return
        self.recordDir = getDirHandle(dirname)
        self.rawDataFile = self.recordDir['rawData.ma']
        self.envelopeFile = self.recordDir['envelope.ma']
        self.spectrogramFile = self.recordDir['spectrogram.ma']
        self.resetDisplay = True
        self.plotAnalysis()
        self.envLine.setValue(0)

    def lineDragged(self):
        self.showNewRecords = self.envLine.value() >= self.envLine.bounds()[1]
        data = self.rawDataFile.read(readAllData=False)
        tvals = data.xvals('Trial')
        ind = np.argwhere(tvals >= self.envLine.value())[0,0]
        self.specLine.setValue(tvals[-1] * ind / len(tvals))
        self.plotRawData(data['Trial': ind])
        
        # workaround for h5py bug that leaves file handles open
        data._data.file.close()

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
        
        trialArr = np.array([time.time() - self.startTime])
        
        # Raw data plot/storage
        data = result['Clamp1']['Channel': 'primary']
        dataArr = data.asarray()
        
        # inject random noise for testing
        dataArr += np.random.normal(size=len(dataArr), scale=1e-9)
        if np.random.random() > 0.9:
            dataArr += np.sin(np.linspace(0, 1000 * np.random.random(), len(dataArr))) * 1e-9

        # plot raw data only if envelope line is at max position
        if self.showNewRecords:
            self.plotRawData(data)
            self.envLine.setValue(trialArr[0])
            self.specLine.setValue(trialArr[0])
        
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


        # Spectrum analysis
        fft = np.abs(np.fft.fft(dataArr))
        fft = fft[:len(fft)/2]
        freqArr = np.linspace(0, rate/2., len(fft))
        spec = pg.metaarray.MetaArray(fft[np.newaxis, :], info=[
            {'name': 'Trial', 'units': 's', 'values': trialArr},
            {'name': 'Frequency', 'units': 'Hz', 'values': freqArr}])
        if self.spectrogramFile is None:
            self.spectrogramFile = self.recordDir.writeFile(spec, 'spectrogram', appendAxis='Trial', newFile=True)
        else:
            spec.write(self.spectrogramFile.name(), appendAxis='Trial')
                        
        self.plotAnalysis()
            
    def plotRawData(self, data=None):
        if data is None:
            data = self.rawDataFile.read()['Trial': -1]
        self.plot.plot(data.xvals('Time'), data.asarray(), clear=True)
        
    def plotAnalysis(self):
        self.fileLabel.setText(self.recordDir.shortName() + (' (rw)' if self.recordWritable else ' (ro)'))

        # update envelope
        envelope = self.envelopeFile.read()
        trials = envelope.xvals('Trial')
        envArr = envelope.asarray()
        self.envelopePlot.clear()
        self.envelopePlot.addItem(self.envLine)
        grey = (255, 255, 255, 100)
        c1 = self.envelopePlot.plot(trials, envArr[:,0], pen=grey)  # min
        c2 = self.envelopePlot.plot(trials, envArr[:,2], pen=grey)  # max
        fill = pg.FillBetweenItem(c1, c2, grey)
        self.envelopePlot.addItem(fill)
        c1 = self.envelopePlot.plot(trials, envArr[:,1] + envArr[:,3], pen=grey)  # +std
        c2 = self.envelopePlot.plot(trials, envArr[:,1] - envArr[:,3], pen=grey)  # -std
        fill = pg.FillBetweenItem(c1, c2, grey)
        self.envelopePlot.addItem(fill)

        self.envelopePlot.plot(trials, envArr[:,1])  # mean

        # update spectrogram
        specData = self.spectrogramFile.read()
        specArr = specData.asarray()
        self.spectrogram.setImage(specArr, autoLevels=self.resetDisplay, autoRange=True, 
                                  scale=(trials[-1] / specArr.shape[0], specData.xvals('Frequency')[-1] / specArr.shape[1]))
        
        self.envLine.setBounds([0, trials[-1]])
        
        self.resetDisplay = False
        
    def quit(self):
        self.startBtn.setChecked(False)
        Module.quit(self)

    


