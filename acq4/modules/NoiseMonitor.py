from __future__ import print_function
import time, weakref, collections
import numpy as np
from acq4.util import Qt

from acq4.modules.Module import Module
import acq4.util.InterfaceCombo  # just to register 'interface' parameter type
from acq4.util.DataManager import getDirHandle
import acq4.pyqtgraph as pg


class NoiseMonitor(Module):
    """ Used to monitor electrical noise over long time periods.
    """
    moduleDisplayName = "Noise Monitor"
    moduleCategory = "Utilities"

    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config) 
        
        self.recordDir = None
        self.recordWritable = False
        self.running = False
        
        self.win = Qt.QSplitter()
        
        self.ctrlWidget = pg.LayoutWidget()
        self.win.addWidget(self.ctrlWidget)
        self.newBtn = Qt.QPushButton('New Record')
        self.loadBtn = Qt.QPushButton('Load Record')
        self.startBtn = Qt.QPushButton('Start')
        self.startBtn.setCheckable(True)
        self.fileLabel = Qt.QLabel()
        self.ctrlWidget.addWidget(self.newBtn, 0, 0)
        self.ctrlWidget.addWidget(self.loadBtn, 1, 0)
        self.ctrlWidget.addWidget(self.startBtn, 2, 0)
        self.ctrlWidget.addWidget(self.fileLabel, 3, 0)
        self.newBtn.clicked.connect(self.newRecord)
        self.loadBtn.clicked.connect(self.loadClicked)
        self.startBtn.toggled.connect(self.startToggled)

        self.params = pg.parametertree.Parameter.create(name='params', type='group', children=[
            dict(name='interval', type='float', value=10, suffix='s', siPrefix=True, limits=[0.001, None], step=1.0),
            dict(name='trace duration', type='float', value=1.0, suffix='s', siPrefix=True, limits=[0.001, None], step=0.1),
            dict(name='sample rate', type='int', value=1e6, suffix='Hz', siPrefix=True, limits=[100, None], step=1e5),
        ])
        self.ptree = pg.parametertree.ParameterTree()
        self.ptree.setParameters(self.params)
        self.ctrlWidget.addWidget(self.ptree, 4, 0)

        self.channelLayout =Qt.QSplitter()
        self.win.addWidget(self.channelLayout)
        
        self.channels = collections.OrderedDict()

        self.win.show()
        
        self.timer = Qt.QTimer()
        self.timer.timeout.connect(self.runOnce)

    def runOnce(self):
        if self.running:
            return
        self.running = True
        try:
            for w in self.channels.values():
                w.runOnce()
        finally:
            self.running = False

    def startToggled(self, start):
        if start:
            try:
                if self.recordDir is None or not self.recordWritable:
                    self.newRecord()
                if self.startTime is None:
                    self.startTime = time.time()
                self.timer.start(self.params['interval'] * 1000)
                self.runOnce()
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
        self.updateFileLabel()
        self.clearChannels()
        self.startTime = None

        for dev in self.config['devices']:
            w = self.addChannel(dev, mode=self.config['devices'][dev]['mode'], recordDir=self.recordDir)
        
    def loadClicked(self):
        try:
            startDir = self.manager.getCurrentDir()
        except Exception:
            startDir = self.manager.getBaseDir()
        dirname = Qt.QFileDialog.getExistingDirectory(self.win, "Open Record", startDir.name())
        if dirname == '':
            return
        self.recordDir = getDirHandle(dirname)
        self.recordWritable = False
        self.updateFileLabel()
        self.clearChannels()

        for dev in self.recordDir.ls():
            w = self.addChannel(dev, mode=None, recordDir=self.recordDir)

    def updateFileLabel(self):
        self.fileLabel.setText(self.recordDir.shortName() + (' (rw)' if self.recordWritable else ' (ro)'))

    def addChannel(self, dev, mode, recordDir):
        w = ChannelRecorder(self, dev, mode, recordDir)
        self.channels[dev] = w
        self.channelLayout.addWidget(w)

    def clearChannels(self):
        for w in self.channels.values():
            w.hide()
            w.setParent(None)
        self.channels = collections.OrderedDict()


class ChannelRecorder(Qt.QSplitter):
    def __init__(self, mod, dev, mode, recordDir):
        self.mod = weakref.ref(mod)
        self.dev = dev
        self.mode = mode
        self.writable = mode != None
        self.recordDir = recordDir.getDir(self.dev, create=self.writable)
        if self.writable:
            self.recordDir.setInfo(mode=mode)
        else:
            mode = self.recordDir.info()['mode']

        if mode[0] == 'v':
            self.units = 'A'
        else:
            self.units = 'V'

        self.rawDataFile = None
        self.envelopeFile = None
        self.spectrogramFile = None
        self.resetDisplay = True
        self.showNewRecords = True

        Qt.QSplitter.__init__(self, Qt.Qt.Vertical)

        self.plot = pg.PlotWidget(labels={'left': ('Primary', self.units), 'bottom': ('Time', 's')}, title="%s (%s)" % (dev, mode))
        self.plot.setDownsampling(auto=True)
        self.plot.setClipToView(True)
        self.addWidget(self.plot)
        
        self.envelopePlot = pg.PlotWidget(labels={'left': ('Mean, Stdev, Peaks', self.units), 'bottom': ('Time', 's')})
        self.addWidget(self.envelopePlot)
        
        self.specView = pg.PlotItem(labels={'left': ('Frequency', 'Hz'), 'bottom': ('Time', 's')})
        self.spectrogram = pg.ImageView(view=self.specView)
        self.specView.setAspectLocked(False)
        self.spectrogram.imageItem.setAutoDownsample(True)
        self.addWidget(self.spectrogram)
        
        self.setStretchFactor(0, 10)
        self.setStretchFactor(1, 15)
        self.setStretchFactor(2, 30)
        
        self.specLine = pg.InfiniteLine()
        self.spectrogram.addItem(self.specLine)
        
        self.envLine = pg.InfiniteLine(movable=True)
        self.envelopePlot.addItem(self.envLine)
        self.envLine.sigDragged.connect(self.lineDragged)

        if not self.writable:
            # Load previously collected data
            self.loadRecord()

    def loadRecord(self):
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
        dev = self.dev
        mode = self.mode
        dur = self.mod().params['trace duration']
        rate = self.mod().params['sample rate']
        npts = int(dur * rate)
        cmd = {
            'protocol': {'duration': dur},
            'DAQ': {'rate': rate, 'numPts': npts},
            dev: {'mode': mode, 'holding': 0, 'command': np.zeros(npts), 'recordSecondary': False},
        }
        task = self.mod().manager.createTask(cmd)
        task.execute()
        result = task.getResult()
        
        trialArr = np.array([time.time() - self.mod().startTime])
        
        # Raw data plot/storage
        data = result[dev]['Channel': 'primary']
        dataArr = data.asarray()
        
        # inject random noise for testing
        # dataArr += np.random.normal(size=len(dataArr), scale=1e-9)
        # if np.random.random() > 0.9:
        #     dataArr += np.sin(np.linspace(0, 1000 * np.random.random(), len(dataArr))) * 1e-9

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
            {'name': 'Metric', 'units': self.units}])
        if self.envelopeFile is None:
            self.envelopeFile = self.recordDir.writeFile(env, 'envelope', appendAxis='Trial', newFile=True)
        else:
            env.write(self.envelopeFile.name(), appendAxis='Trial')


        # Spectrum analysis
        fft = np.abs(np.fft.fft(dataArr))
        fft = fft[:len(fft)/2]
        freqArr = np.linspace(0, rate/2., len(fft))

        # downsample spectrogram
        ds = len(fft) // 1000
        fft = fft[:ds*1000].reshape(1000, ds).max(axis=1)
        freqArr = freqArr[:ds*1000:ds]

        # log scale for pretty
        fft = np.log10(fft)

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

    


