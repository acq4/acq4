# -*- coding: utf-8 -*-
from __future__ import division, print_function

import gc
import os
import sys
import time
from collections import OrderedDict
from functools import reduce

import numpy as np
import pyqtgraph as pg
import pyqtgraph.configfile as configfile
import six
from six.moves import map
from six.moves import range
from six.moves import reduce

import acq4.util.DirTreeWidget as DirTreeWidget
import acq4.util.ptime as ptime
from acq4.Manager import getManager
from acq4.util import Qt
from acq4.util.HelpfulException import HelpfulException
from acq4.util.SequenceRunner import runSequence
from acq4.util.StatusBar import StatusBar
from acq4.util.Thread import Thread
from acq4.util.debug import printExc, Profiler, logMsg, Mutex
from acq4.util.future import Future
from . import analysisModules
from ..Module import Module

Ui_MainWindow = Qt.importTemplate('.TaskRunnerTemplate')


class Window(Qt.QMainWindow):
    def __init__(self, pr):
        Qt.QMainWindow.__init__(self)
        mp = os.path.dirname(__file__)
        self.setWindowIcon(Qt.QIcon(os.path.join(mp, 'icon.png')))
        self.pr = pr

        self.stateFile = os.path.join('modules', self.pr.name + '_ui.cfg')
        uiState = getManager().readConfigFile(self.stateFile)
        if 'geometry' in uiState:
            geom = Qt.QRect(*uiState['geometry'])
            self.setGeometry(geom)

    def closeEvent(self, ev):
        geom = self.geometry()
        uiState = {'geometry': [geom.x(), geom.y(), geom.width(), geom.height()]}
        getManager().writeConfigFile(uiState, self.stateFile)
        self.pr.quit()


class Loader(DirTreeWidget.DirTreeLoader):
    def __init__(self, host, baseDir):
        DirTreeWidget.DirTreeLoader.__init__(self, baseDir, create=True)
        self.host = host

    def new(self):
        self.host.newTask()
        return True

    def load(self, handle):
        self.host.loadTask(handle)
        return True

    def save(self, handle):
        self.host.saveTask(handle)
        return True


class TaskRunner(Module):
    moduleDisplayName = "Task Runner"
    moduleCategory = "Acquisition"

    sigTaskPaused = Qt.Signal()
    sigTaskFinished = Qt.Signal()  ## emitted when the task thread exits (end of task, end of sequence, or exit due to error)
    sigNewFrame = Qt.Signal(object)  ## emitted at the end of each individual task
    sigTaskSequenceStarted = Qt.Signal(object)  ## called whenever single task OR task sequence has started
    sigTaskStarted = Qt.Signal(object)  ## called at start of EVERY task, including within sequences
    sigTaskChanged = Qt.Signal(object, object)

    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)

        # On systems with low memory, this flag can be set to improve memory usage at the cost of performance.
        # Works by running garbage collection between consecutive task runs to avoid accumulation of large garbage objects.
        # Since most modern systems have adequate memory, this is now disabled by default.
        self._reduceMemoryUsage = config.get('reduceMemoryUsage', False)

        self.lastProtoTime = None
        self.loopEnabled = False
        self.devListItems = {}

        self.docks = {}
        self.firstDock = None  # all new docks should stack here
        self.analysisDocks = {}
        self.deleteState = 0
        self.ui = Ui_MainWindow()
        self.win = Window(self)

        g = self.win.geometry()
        self.ui.setupUi(self.win)
        self.win.setGeometry(g)
        self.win.setStatusBar(StatusBar())

        self.ui.protoDurationSpin.setOpts(dec=True, bounds=[1e-3, None], step=1, minStep=1e-3, suffix='s',
                                          siPrefix=True)
        self.ui.protoLeadTimeSpin.setOpts(dec=True, bounds=[0, None], step=1, minStep=10e-3, suffix='s', siPrefix=True)
        self.ui.protoCycleTimeSpin.setOpts(dec=True, bounds=[0, None], step=1, minStep=1e-3, suffix='s', siPrefix=True)
        self.ui.seqCycleTimeSpin.setOpts(dec=True, bounds=[0, None], step=1, minStep=1e-3, suffix='s', siPrefix=True)
        self.protoStateGroup = pg.WidgetGroup([
            (self.ui.protoContinuousCheck, 'continuous'),
            (self.ui.protoDurationSpin, 'duration'),
            (self.ui.protoLeadTimeSpin, 'leadTime'),
            (self.ui.protoLoopCheck, 'loop'),
            (self.ui.protoCycleTimeSpin, 'loopCycleTime'),
            (self.ui.seqCycleTimeSpin, 'cycleTime'),
            (self.ui.seqRepetitionSpin, 'repetitions', 1),
        ])

        try:
            try:
                taskDir = config['taskDir']
            except KeyError:
                taskDir = os.path.join(self.manager.configDir, "protocols")
            self.taskList = Loader(self, taskDir)
        except KeyError:
            raise HelpfulException("Config is missing 'taskDir'; cannot load task list.")

        self.ui.LoaderDock.setWidget(self.taskList)

        self.currentTask = None  ## pointer to current task object

        for m in analysisModules.MODULES:
            item = Qt.QListWidgetItem(m, self.ui.analysisList)
            item.setFlags(Qt.Qt.ItemIsSelectable | Qt.Qt.ItemIsEnabled | Qt.Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Qt.Unchecked)

        self.taskThread = TaskThread(self)

        self.newTask()

        self.ui.testSingleBtn.clicked.connect(self.testSingleClicked)
        self.ui.runTaskBtn.clicked.connect(self.runSingleClicked)
        self.ui.testSequenceBtn.clicked.connect(self.testSequence)
        self.ui.runSequenceBtn.clicked.connect(self.runSequenceClicked)
        self.ui.stopSingleBtn.clicked.connect(self.stopSingle)
        self.ui.stopSequenceBtn.clicked.connect(self.stopSequence)
        self.ui.pauseSequenceBtn.toggled.connect(self.pauseSequence)
        self.ui.deviceList.itemClicked.connect(self.deviceItemClicked)
        self.taskList.sigCurrentFileChanged.connect(self.fileChanged)  ## called if loaded task file is renamed or moved
        self.taskThread.finished.connect(self.taskThreadStopped)
        self.taskThread.sigNewFrame.connect(self.handleFrame)
        self.taskThread.sigPaused.connect(self.taskThreadPaused)
        self.taskThread.sigTaskStarted.connect(self.taskStarted)
        self.taskThread.sigExitFromError.connect(self.taskErrored)
        self.protoStateGroup.sigChanged.connect(self.protoGroupChanged)
        self.win.show()
        self.ui.sequenceParamList.itemChanged.connect(self.updateSeqReport)
        self.ui.analysisList.itemClicked.connect(self.analysisItemClicked)

    def protoGroupChanged(self, param, value):
        self.sigTaskChanged.emit(param, value)
        if param == 'repetitions':
            self.updateSeqParams()
        if param in ['duration', 'cycleTime', 'leadTime']:
            self.updateSeqReport()

    def getDevice(self, dev):
        """Return the taskGui for dev. Used by some devices to detect changes in others."""
        ## Create or re-enable the device if needed
        try:
            item = self.ui.deviceList.findItems(dev, Qt.Qt.MatchExactly)[0]
        except:
            raise Exception('Requested device %s does not exist!' % dev)
        item.setCheckState(Qt.Qt.Checked)
        self.deviceItemClicked(item)

        return self.docks[dev].widget()

    def getParam(self, param):
        """Return the value of a named task parameter"""
        return self.protoStateGroup.state()[param]

    def updateDeviceList(self, task=None):
        """Update the device list to reflect only the devices that exist in the system or are referenced by the current task. Update the color and checkstate of each item as well."""
        devList = self.manager.listDevices()

        if task is not None:
            protList = list(task.devices.keys())
        elif self.currentTask is not None:
            protList = list(self.currentTask.devices.keys())
        else:
            protList = []

        ## Remove all devices that do not exist and are not referenced by the task
        rem = []
        for d in self.devListItems:
            if d not in devList and d not in protList:
                # print "    ", d
                self.ui.deviceList.takeItem(self.ui.deviceList.row(self.devListItems[d]))
                rem.append(d)
        for d in rem:
            del self.devListItems[d]

        ## Add all devices that exist in the current system
        for d in devList:
            if d not in self.devListItems:
                self.devListItems[d] = Qt.QListWidgetItem(d, self.ui.deviceList)
                # self.devListItems[d].setData(32, Qt.QVariant(d))
                self.devListItems[d].setData(32, d)
            self.devListItems[d].setForeground(Qt.QBrush(Qt.QColor(0, 0, 0)))

        ## Add all devices that are referenced by the task but do not exist
        for d in protList:
            if d not in self.devListItems:
                self.devListItems[d] = Qt.QListWidgetItem(d, self.ui.deviceList)
                self.devListItems[d].setForeground(Qt.QBrush(Qt.QColor(150, 0, 0)))

        ## Make sure flags and checkState are correct for all items
        for d in self.devListItems:
            self.devListItems[d].setFlags(Qt.Qt.ItemIsSelectable | Qt.Qt.ItemIsEnabled | Qt.Qt.ItemIsUserCheckable)
            if d in protList:
                self.devListItems[d].setCheckState(Qt.Qt.Checked)
            else:
                self.devListItems[d].setCheckState(Qt.Qt.Unchecked)

    def deviceItemClicked(self, item):
        """Respond to clicks in the device list. Add/remove devices from the current task and update docks."""
        name = str(item.text())
        if item.checkState() == Qt.Qt.Unchecked:
            self.currentTask.removeDevice(name)
        else:
            self.currentTask.addDevice(name)
        self.updateDeviceDocks([name])

    def analysisItemClicked(self, item):
        name = str(item.text())
        if item.checkState() == Qt.Qt.Checked:
            if self.createAnalysisDock(name) is False:
                item.setCheckState(Qt.Qt.Unchecked)
        else:
            self.removeAnalysisDock(name)

    def createAnalysisDock(self, mod):
        try:
            m = analysisModules.createAnalysisModule(mod, self)
            dock = Qt.QDockWidget(mod)
            dock.setFeatures(dock.AllDockWidgetFeatures)
            dock.setAllowedAreas(Qt.Qt.BottomDockWidgetArea | Qt.Qt.TopDockWidgetArea)
            dock.setObjectName(mod)
            dock.setWidget(m)
            dock.setAutoFillBackground(True)

            self.analysisDocks[mod] = dock
            self.win.addDockWidget(Qt.Qt.BottomDockWidgetArea, dock)
            if self.firstDock is None:
                self.firstDock = dock
            else:
                # by default, docks are tabbed. 
                # if dock state is stored, this will be corrected later.
                Qt.QApplication.sendPostedEvents(dock, 0)  # required to ensure new tab is visible
                self.win.tabifyDockWidget(self.firstDock, dock)

            items = self.ui.analysisList.findItems(mod, Qt.Qt.MatchExactly)
            items[0].setCheckState(Qt.Qt.Checked)

            return True
        except:
            printExc("Analysis module creation failed:")
            return False

    def removeAnalysisDock(self, mod):
        if mod not in self.analysisDocks:
            return
        try:
            self.analysisDocks[mod].widget().quit()
        except:
            printExc("Error closing analysis dock:")
        dock = self.analysisDocks[mod]
        if self.firstDock is dock:
            self.firstDock = None
        self.win.removeDockWidget(dock)
        del self.analysisDocks[mod]
        items = self.ui.analysisList.findItems(mod, Qt.Qt.MatchExactly)
        items[0].setCheckState(Qt.Qt.Unchecked)

    def fileChanged(self, handle, change, args):
        if change == 'renamed' or change == 'moved':
            self.currentTask.fileName = handle.name()

    def updateSeqParams(self, dev='protocol'):
        """Update the list of available sequence parameters."""
        if dev == 'protocol':
            rep = self.protoStateGroup.state()['repetitions']
            if rep == 0:
                params = {}
            else:
                params = {'repetitions': range(int(rep))}
        elif dev not in self.currentTask.enabledDevices():
            return
        else:
            params = self.docks[dev].widget().listSequence()
        # print "New parameter lst:", params
        self.ui.sequenceParamList.updateList(dev, params)

        self.updateSeqReport()

    def updateSeqReport(self):
        s = self.protoStateGroup.state()
        period = max(s['duration'] + s['leadTime'], s['cycleTime'])
        items = self.ui.sequenceParamList.listParams()[:]
        if len(items) == 0:
            self.ui.paramSpaceLabel.setText('0')
            self.ui.seqTimeLabel.setText('0')
            tot = 0
        else:
            psi = [len(i[2]) for i in items]
            ps = list(map(str, psi))
            tot = reduce(lambda x, y: x * y, psi)
            self.ui.paramSpaceLabel.setText(' x '.join(ps) + ' = %d' % tot)
            self.ui.seqTimeLabel.setText('%0.3f sec' % (period * tot))

        if tot == 0:
            self.ui.testSequenceBtn.setEnabled(False)
            self.ui.runSequenceBtn.setEnabled(False)
        else:
            self.ui.testSequenceBtn.setEnabled(True)
            self.ui.runSequenceBtn.setEnabled(True)

    def hideDock(self, dev):
        self.docks[dev].hide()
        self.docks[dev].widget().disable()
        self.ui.sequenceParamList.removeDevice(dev)

    def showDock(self, dev):
        self.docks[dev].show()
        self.docks[dev].widget().enable()
        self.updateSeqParams(dev)

    def updateDeviceDocks(self, devNames=None):
        """Create/unhide new docks if they are needed and hide old docks if they are not.
        If a list of device names is given, only those device docks will be affected."""
        task = self.currentTask
        # print "update docks", task.name()
        # print "  devices:", task.enabledDevices()

        ## (un)hide docks as needed
        for d in self.docks:
            if devNames is not None and d not in devNames:
                continue
            # print "  check", d
            if self.docks[d] is None:
                continue
            if d not in task.enabledDevices():
                # print "  hide", d
                self.hideDock(d)
            else:
                # print "  show", d
                self.showDock(d)

        ## Create docks that don't exist
        # pdb.set_trace()
        for d in task.enabledDevices():
            if devNames is not None and d not in devNames:
                continue

            if d not in self.docks:
                if d not in self.manager.listDevices():
                    continue
                self.docks[d] = None  ## Instantiate to prevent endless loops!
                # print "  Create", d
                try:
                    dev = self.manager.getDevice(d)
                    dw = dev.taskInterface(self)
                except:
                    printExc("Error while creating dock '%s':" % d)
                    del self.docks[d]

                if d in self.docks:
                    dock = Qt.QDockWidget(d)
                    dock.setFeatures(dock.AllDockWidgetFeatures)
                    dock.setAllowedAreas(Qt.Qt.BottomDockWidgetArea | Qt.Qt.TopDockWidgetArea)
                    dock.setObjectName(d)
                    dock.setWidget(dw)
                    dock.setAutoFillBackground(True)
                    dw.setSizePolicy(Qt.QSizePolicy.Expanding, Qt.QSizePolicy.Expanding)
                    self.docks[d] = dock
                    self.win.addDockWidget(Qt.Qt.BottomDockWidgetArea, dock)
                    if self.firstDock is None:
                        self.firstDock = dock
                    else:
                        Qt.QApplication.sendPostedEvents(dock, 0)  # required to ensure new tab is visible
                        self.win.tabifyDockWidget(self.firstDock, dock)
                    dock.widget().sigSequenceChanged.connect(self.updateSeqParams)
                    self.updateSeqParams(d)

    def clearDocks(self):
        for d in self.docks:
            try:
                # print "request dock %s quit" % d
                self.docks[d].widget().quit()
            except:
                printExc("Error while requesting dock '%s' quit:" % d)
            try:
                if self.firstDock is self.docks[d]:
                    self.firstDock = None
                self.win.removeDockWidget(self.docks[d])
                self.docks[d].close()
            except:
                printExc("Error while closing dock '%s':" % d)
        self.docks = {}

        for d in list(self.analysisDocks.keys()):
            self.removeAnalysisDock(d)

        self.ui.sequenceParamList.clear()

        ## now's a good time to free up some memory.
        Qt.QApplication.instance().processEvents()
        gc.collect()

    def quit(self):
        self.stopSequence()
        self.stopSingle()
        self.clearDocks()
        Module.quit(self)

    def newTask(self):
        self.stopSequence()
        self.stopSingle()

        ## Remove all docks
        self.clearDocks()

        ## Create new empty task object
        self.currentTask = Task(self)

        self.protoStateGroup.setState({
            'continuous': False,
            'duration': 0.2,
            'leadTime': 0.01,
            'loop': False,
            'loopCycleTime': 0.3,
            'cycleTime': 0.3,
            'repetitions': 0
        })

        ## Clear extra devices in dev list
        self.updateDeviceList()

        ## Clear sequence parameters, disable sequence dock
        self.updateSeqParams()

    def loadTask(self, handle):
        prof = Profiler('TaskRunner.loadTask', disabled=True)
        try:
            Qt.QApplication.setOverrideCursor(Qt.QCursor(Qt.Qt.WaitCursor))
            self.stopSequence()
            self.stopSingle()

            prof.mark('stopped')

            fn = handle.name()

            ## Remove all docks
            self.clearDocks()
            prof.mark('cleared')

            ## Create task object from requested file
            prot = Task(self, fileName=fn)
            ## Set current task
            self.currentTask = prot
            prof.mark('made task')

            # print "Docks cleared."

            ## Update task parameters
            self.protoStateGroup.setState(prot.conf['conf'])
            prof.mark('set state')

            ## update dev list
            self.updateDeviceList()
            prof.mark('update dev list')

            ## Update sequence parameters, dis/enable sequence dock

            ## Create new docks
            self.updateDeviceDocks()
            prof.mark('update docks')

            ## Configure docks
            for d in prot.devices:
                if d in self.docks:
                    try:
                        self.docks[d].widget().restoreState(prot.devices[d])
                        prof.mark('configured dock: ' + d)
                    except:
                        printExc("Error while loading task dock:")

            ## create and configure analysis docks
            if 'analysis' in prot.conf:
                for k in prot.conf['analysis']:
                    try:
                        self.createAnalysisDock(k)
                        conf = prot.conf['analysis'][k]
                        self.analysisDocks[k].widget().restoreState(conf)
                        prof.mark('configured dock: ' + k)
                    except:
                        printExc("Error while loading analysis dock:")

            ## Load sequence parameter state (must be done after docks have loaded)
            self.ui.sequenceParamList.loadState(prot.conf['params'])
            self.updateSeqParams('protocol')
            prof.mark('load seq params')

            ## Configure dock positions
            winState = prot.conf['windowState']
            if winState is not None:
                self.win.restoreState(winState)

            prof.mark('position docks')

        finally:
            Qt.QApplication.restoreOverrideCursor()
            prof.finish()

    def saveTask(self, fileHandle=None):
        ## Write task config to file
        self.currentTask.write(fileHandle.name())

    def testSingleClicked(self):
        self.testSingle()

    def runSingleClicked(self):
        self.runSingle(store=True)

    def testSingle(self):
        return self.runSingle(store=False)

    def runSingle(self, store=True, storeDirHandle=None):
        """Start a single task run (using default values for all sequence parameters).

        Return a TaskFuture instance that can be used to monitor progress and results.
        """

        if self.protoStateGroup.state()['loop']:
            self.loopEnabled = True

        # good time to collect garbage
        if self._reduceMemoryUsage:
            gc.collect()

        self.lastProtoTime = ptime.time()
        ## Disable all start buttons
        self.setStartBtnsEnable(False)

        ## Set storage dir
        try:
            if store:
                if storeDirHandle is None:
                    storeDirHandle = self.manager.getCurrentDir()
                name = self.currentTask.name()
                if name is None:
                    name = 'protocol'
                info = self.taskInfo()
                info['dirType'] = 'Protocol'
                ## Create storage directory with all information about the task to be executed
                dh = storeDirHandle.mkdir(name, autoIncrement=True, info=info)
            else:
                dh = None

            ## Tell devices to prepare for task start.
            for d in self.currentTask.devices:
                if self.currentTask.deviceEnabled(d):
                    self.docks[d].widget().prepareTaskStart()

            ## Generate executable conf from task object
            prot = self.generateTask(dh)
            # print prot
            self.sigTaskSequenceStarted.emit({})
            # print "runSingle: Starting taskThread.."
            future = self.taskThread.startTask(prot)
            # print "runSingle: taskThreadStarted"
        except:
            exc = sys.exc_info()
            self.setStartBtnsEnable(True)
            self.loopEnabled = False
            # print "Error starting task. "
            raise HelpfulException("Error occurred while starting task", exc=exc)

        return future

    def runSequenceClicked(self):
        self.runSequence(store=True)

    def testSequence(self):
        return self.runSequence(store=False)

    def runSequence(self, store=True, storeDirHandle=None):
        """Start a sequence task run.

        Return a TaskFuture instance that can be used to monitor progress and results.
        """
        ## Disable all start buttons
        self.setStartBtnsEnable(False)

        # good time to collect garbage
        if self._reduceMemoryUsage:
            gc.collect()

        ## Find all top-level items in the sequence parameter list
        try:
            ## make sure all devices are reporting their correct sequence lists
            items = self.ui.sequenceParamList.listParams()
            ## Generate parameter space
            params = OrderedDict()
            paramInds = OrderedDict()
            linkedParams = {}
            pLen = 1
            for i in items:
                key = i[:2]
                params[key] = i[2]
                paramInds[key] = list(range(len(i[2])))
                pLen *= len(i[2])
                linkedParams[key] = i[3]

            ## Set storage dir
            if store:
                if storeDirHandle is None:
                    storeDirHandle = self.manager.getCurrentDir()
                name = self.currentTask.name()
                if name is None:
                    name = 'protocol'
                info = self.taskInfo(params)
                info['dirType'] = 'ProtocolSequence'
                dh = storeDirHandle.mkdir(name, autoIncrement=True, info=info)
            else:
                dh = None

            ## Tell devices to prepare for task start.
            for d in self.currentTask.devices:
                if self.currentTask.deviceEnabled(d):
                    self.docks[d].widget().prepareTaskStart()

            # print params, linkedParams
            ## Generate the complete array of command structures. This can take a long time, so we start a progress dialog.
            with pg.ProgressDialog("Generating task commands..", 0, pLen) as progressDlg:
                self.lastQtProcessTime = ptime.time()
                prot = runSequence(lambda p: self.generateTask(dh, p, progressDlg), paramInds, list(paramInds.keys()),
                                   linkedParams=linkedParams)
            if dh is not None:
                dh.flushSignals()  ## do this now rather than later when task is running

            self.sigTaskSequenceStarted.emit({})
            logMsg('Started %s task sequence of length %i' % (self.currentTask.name(), pLen), importance=6)
            # print 'PR task positions:
            future = self.taskThread.startTask(prot, paramInds)

        except:
            self.setStartBtnsEnable(True)
            raise

        return future

    def generateTask(self, dh, params=None, progressDlg=None):
        # prof = Profiler("Generate Task: %s" % str(params))
        ## Never put {} in the function signature
        if params is None:
            params = {}
        prot = {'protocol': self.protoStateGroup.state()}

        # Disable timeouts for these tasks because we don't know how long to wait
        # for external triggers. TODO: use the default timeout, but also allow devices
        # in the task to modify the default.
        prot['protocol']['timeout'] = None

        # prof.mark('protocol state')
        store = (dh is not None)
        prot['protocol']['storeData'] = store
        if store:
            if params != {}:
                name = '_'.join(['%03d' % i for i in list(params.values())])
                # print "mkdir", name
                info = params.copy()
                info['dirType'] = 'Protocol'
                dh1 = dh.mkdir(name, info=info)
                # prof.mark('create storage dir')
            else:
                dh1 = dh
            prot['protocol']['storageDir'] = dh1
        # prof.mark('selected storage dir.')
        prot['protocol']['name'] = self.currentTask.fileName

        for d in self.currentTask.devices:
            if self.currentTask.deviceEnabled(d):
                ## select out just the parameters needed for this device
                p = dict([(i[1], params[i]) for i in params.keys() if i[0] == d])
                ## Ask the device to generate its task command
                if d not in self.docks:
                    raise HelpfulException("The device '%s' currently has no dock loaded." % d,
                                           reasons=[
                                               "This device name does not exist in the system's configuration",
                                               "There was an error when creating the device at program startup",
                                           ],
                                           tags={},
                                           importance=8,

                                           docSections=['userGuide/modules/TaskRunner/loadingNonexistentDevices']
                                           )
                prot[d] = self.docks[d].widget().generateTask(p)
                # prof.mark("get task from %s" % d)
        # print prot['protocol']['storageDir'].name()

        if progressDlg is not None:
            progressDlg.setValue(progressDlg.value() + 1)
            ## only do UI updates every 1 sec.
            now = ptime.time()
            if now - self.lastQtProcessTime > 1.0:
                self.lastQtProcessTime = now
                Qt.QApplication.processEvents()
            if progressDlg.wasCanceled():
                raise Exception("Target sequence computation canceled by user.")
        # prof.mark('done')
        return prot

    def taskInfo(self, params=None):
        """
        Generate a complete description of the task.
        This data is stored with the results of each task run.
        """
        conf = self.saveState()
        del conf['windowState']
        conf['params'] = self.ui.sequenceParamList.listParams()

        devs = {}
        ## store individual dock states
        for d in self.docks:
            if self.currentTask.deviceEnabled(d):
                devs[d] = self.docks[d].widget().describe(params=params)

        desc = {'protocol': conf, 'devices': devs}  # , 'winState': self.winState}

        if params is not None:
            desc['sequenceParams'] = params
        return desc

    def setStartBtnsEnable(self, val):
        btns = [self.ui.testSingleBtn, self.ui.runTaskBtn, self.ui.testSequenceBtn, self.ui.runSequenceBtn]
        for b in btns:
            if not val or self.canEnableBtn(b):
                b.setEnabled(val)

    def canEnableBtn(self, btn):
        if btn == self.ui.testSequenceBtn or btn == self.ui.runSequenceBtn:
            return len(self.ui.sequenceParamList.listParams()) > 0
        else:
            return True

    def taskThreadStopped(self):
        self.sigTaskFinished.emit()
        if not self.loopEnabled:  ## what if we quit due to error?
            self.setStartBtnsEnable(True)

    def taskErrored(self):
        self.setStartBtnsEnable(True)

    def taskThreadPaused(self):
        self.sigTaskPaused.emit()

    def stopSingle(self):
        self.loopEnabled = False
        if self.taskThread.isRunning():
            self.taskThread.abort()
        self.ui.pauseSequenceBtn.setChecked(False)

    def stopSequence(self):
        self.loopEnabled = False
        if self.taskThread.isRunning():
            self.taskThread.stop()
        self.ui.pauseSequenceBtn.setChecked(False)

    def pauseSequence(self, pause):
        self.taskThread.pause(pause)

    def taskStarted(self, params):
        cur = 'Current iteration:\n'
        plist = self.ui.sequenceParamList.listParams()
        try:
            nums = [str(params[p[:2]] + 1) for p in plist]
        except:
            nums = []
        cur += ',  '.join(nums)
        self.ui.seqCurrentLabel.setText(cur)

        # check for co-sequenced parameters and re-insert here.
        # (the task runner thread does not know about these)
        params = params.copy()
        for p in plist:
            for subp in p[3]:
                if p[:2] in params:
                    params[subp] = params[p[:2]]

        self.sigTaskStarted.emit(params)

    def handleFrame(self, frame):

        ## Request each device handles its own data
        ## Note that this is only used to display results; data storage is handled by Manager and the individual devices.
        # print "got frame", frame
        prof = Profiler('TaskRunner.handleFrame', disabled=True)
        for d in frame['result']:
            try:
                if d != 'protocol':
                    self.docks[d].widget().handleResult(frame['result'][d], frame['params'])
                    prof.mark('finished %s' % d)
            except:
                printExc("Error while handling result from device '%s'" % d)

        self.sigNewFrame.emit(frame)
        prof.mark('emit newFrame')

        ## If this is a single-mode task and looping is turned on, schedule the next run
        if self.loopEnabled:
            ct = self.protoStateGroup.state()['loopCycleTime']
            t = max(0, ct - (ptime.time() - self.lastProtoTime))
            Qt.QTimer.singleShot(int(t * 1000.), self.loop)
        prof.finish()

        # good time to collect garbage
        if self._reduceMemoryUsage:
            gc.collect()

    def loop(self):
        """Run one iteration when in loop mode"""
        if not self.loopEnabled:
            self.setStartBtnsEnable(True)
            return

        if self.taskThread.isRunning():  ## If a task is still running, delay 10ms and try again
            Qt.QTimer.singleShot(10, self.loop)
        else:
            self.testSingle()

    def saveState(self):
        ## Returns a description of the current window state -- dock positions, parameter list order, and analysis dock states.
        conf = self.protoStateGroup.state()

        ## store window state
        ws = bytes(self.win.saveState().toPercentEncoding()).decode()

        ## store parameter order/state
        params = self.ui.sequenceParamList.saveState()

        adocks = {}
        for d in self.analysisDocks:
            adocks[d] = self.analysisDocks[d].widget().saveState()

        return {'conf': conf, 'params': params, 'windowState': ws, 'analysis': adocks}


class Task:
    def __init__(self, ui, fileName=None):
        self.ui = ui

        if fileName is not None:
            self.fileName = fileName
            conf = configfile.readConfigFile(fileName)
            if 'protocol' not in conf:
                self.conf = conf
            else:
                self.conf = conf['protocol']
            if 'params' not in self.conf:
                self.conf['params'] = []

            if 'winState' in conf:
                self.conf['windowState'] = conf['winState']
            self.conf['windowState'] = Qt.QByteArray.fromPercentEncoding(six.b(self.conf['windowState']))

            self.devices = conf['devices']
            self.enabled = list(self.devices.keys())
        else:
            self.fileName = None
            self.enabled = []
            self.conf = {}
            self.devices = {}
            self.winState = None

    def deviceEnabled(self, dev):
        return dev in self.enabled

    def write(self, fileName=None):
        ## Write this task to a file. Called by TaskRunner.saveTask()
        info = self.saveState()

        if fileName is None:
            if self.fileName is None:
                raise Exception("Can not write task--no file name specified")
            fileName = self.fileName
        self.fileName = fileName
        configfile.writeConfigFile(info, fileName)

    def name(self):
        if self.fileName is None:
            return None
        return os.path.split(self.fileName)[1]

    def saveState(self):
        ## Generate a description of this task. The description 
        ## can be used to save/reload the task (calls saveState on all devices). 

        self.conf = self.ui.saveState()

        ## store individual dock states
        for d in self.ui.docks:
            if self.deviceEnabled(d):
                self.devices[d] = self.ui.docks[d].widget().saveState()

        conf = self.conf.copy()
        devs = self.devices.copy()

        ## Remove unused devices before writing
        rem = [d for d in devs if not self.deviceEnabled(d)]
        for d in rem:
            del devs[d]
        return {'protocol': conf, 'devices': devs}

    def enabledDevices(self):
        return self.enabled[:]

    def removeDevice(self, dev):
        if dev in self.enabled:
            self.enabled.remove(dev)

    def addDevice(self, dev):
        if dev not in self.devices:
            self.devices[dev] = {}
        if dev not in self.enabled:
            self.enabled.append(dev)

    def renameDevice(self, oldName, newName):
        if oldName not in self.conf['devices']:
            return
        self.devices[newName] = self.devices[oldName]
        del self.devices[oldName]
        if oldName in self.enabled:
            self.enabled.append(newName)
            self.enabled.remove(oldName)
        else:
            if newName in self.enabled:
                self.enabled.remove(newName)


class TaskThread(Thread):
    sigPaused = Qt.Signal()
    sigNewFrame = Qt.Signal(object)
    sigExitFromError = Qt.Signal()
    sigTaskStarted = Qt.Signal(object)

    def __init__(self, ui):
        Thread.__init__(self)
        self.ui = ui
        self.dm = self.ui.manager
        self.lock = Mutex(Qt.QMutex.Recursive)
        self.stopThread = True
        self.abortThread = False
        self.paused = False
        self._currentTask = None
        self._currentFuture = None
        self._systrace = None

    def startTask(self, task, paramSpace=None):
        with self.lock:
            self._systrace = sys.gettrace()
            while self.isRunning():
                raise Exception("Already running another task")
            self.task = task

            paramSize = 1
            if paramSpace is not None:
                for param, inds in paramSpace.items():
                    paramSize *= len(inds)

            self._currentFuture = TaskFuture(self, task, paramSize)
            self.paramSpace = paramSpace
            self.lastRunTime = None
            self.start()  ### causes self.run() to be called from new thread
            logMsg("Task started.", importance=1)

            return self._currentFuture

    def pause(self, pause):
        with self.lock:
            self.paused = pause

    def run(self):
        # If main thread uses a systrace, we probably want it too.
        sys.settrace(self._systrace)

        self.objs = None
        try:
            with self.lock:
                self.stopThread = False
                self.abortThread = False

            if self.paramSpace is None:
                try:
                    self.runOnce()
                except Exception as e:
                    if e.args[0] != 'stop':
                        raise
            else:
                runSequence(self.runOnce, self.paramSpace, list(self.paramSpace.keys()))

        except Exception as exc:
            self.task = None  ## free up this memory
            self.paramSpace = None
            printExc("Error in task thread, exiting.")
            self._currentFuture._taskDone(interrupted=True, error=str(exc))
            self._currentFuture = None
            self.sigExitFromError.emit()
        else:
            self._currentFuture._taskDone()
            self._currentFuture = None

    def runOnce(self, params=None):
        # good time to collect garbage
        if self.ui._reduceMemoryUsage:
            gc.collect()

        prof = Profiler("TaskRunner.TaskThread.runOnce", disabled=True, delayed=False)
        startTime = ptime.time()
        if params is None:
            params = {}

        ## Select correct command to execute
        cmd = self.task
        if params is not None:
            for p in params:
                cmd = cmd[p: params[p]]
        prof.mark('select command')

        ## Wait before starting if we've already run too recently
        while (self.lastRunTime is not None) and (ptime.time() < self.lastRunTime + cmd['protocol']['cycleTime']):
            with self.lock:
                if self.abortThread or self.stopThread:
                    # print "Task run aborted by user"
                    return
            time.sleep(1e-3)
        prof.mark('sleep')

        emitSig = True
        while True:
            with self.lock:
                if self.abortThread or self.stopThread:
                    return
                pause = self.paused
            if not pause:
                break
            if emitSig:
                emitSig = False
                self.sigPaused.emit()
            time.sleep(10e-3)

        prof.mark('pause')

        if type(cmd) is not dict:
            print("========= TaskRunner.runOnce cmd: ==================")
            print(cmd)
            print("========= TaskRunner.runOnce params: ==================")
            print("Params:", params)
            print("===========================")
            raise TypeError(
                "TaskRunner.runOnce failed to generate a proper command structure. Object type was '%s', should have been 'dict'." % type(
                    cmd))

        task = self.dm.createTask(cmd)
        prof.mark('create task')

        self.lastRunTime = ptime.time()

        try:
            with self.lock:
                self._currentTask = task
            task.execute(block=False)
            # record estimated end time
            endTime = time.time() + cmd['protocol']['duration']
            self.sigTaskStarted.emit(params)
            prof.mark('execute')
        except:
            with self.lock:
                self._currentTask = None
            try:
                task.stop(abort=True)
            except:
                pass
            printExc("\nError starting task:")
            exc = sys.exc_info()
            raise HelpfulException("\nError starting task:", exc)

        prof.mark('start task')
        ### Do not put code outside of these try: blocks; may cause device lockup

        try:
            ## wait for finish, watch for abort requests
            while True:
                if task.isDone():
                    prof.mark('task done')
                    break
                with self.lock:
                    if self.abortThread:
                        # should be taken care of in TaskThread.abort()
                        # NO -- task.stop() is not thread-safe.
                        task.stop(abort=True)
                        return
                # adjust sleep time based on estimated time remaining in the task.
                sleep = np.clip((endTime - time.time()) * 0.5, 1e-3, 20e-3)
                time.sleep(sleep)

            result = task.getResult()
        except:
            ## Make sure the task is fully stopped if there was a failure at any point.
            # printExc("\nError during task execution:")
            print("\nStopping task..")
            task.stop(abort=True)
            print("")
            raise HelpfulException("\nError during task execution:", sys.exc_info())
        finally:
            with self.lock:
                self._currentTask = None
            self._currentFuture._taskCount += 1
        prof.mark('getResult')

        frame = {'params': params, 'cmd': cmd, 'result': result}
        self._currentFuture.newFrame(frame)
        self.sigNewFrame.emit(frame)
        prof.mark('emit newFrame')
        if self.stopThread:
            raise Exception('stop', result)

        ## Give everyone else a chance to catch up
        Qt.QThread.yieldCurrentThread()
        prof.mark('yield')
        prof.finish()

    def checkStop(self):
        with self.lock:
            if self.stopThread:
                raise Exception('stop')

    def stop(self, block=False, task=None):
        with self.lock:
            if task is not None and self._currentTask is not task:
                return
            self.stopThread = True
        if block:
            if not self.wait(10000):
                raise Exception("Timed out while waiting for thread exit!")

    def abort(self):
        with self.lock:
            if self._currentTask is not None:
                # bad idea -- task.stop() is not thread-safe; must ask the task thread to stop.
                # self._currentTask.stop(abort=True)
                self.abortThread = True


class TaskFuture(Future):
    """Used to check on progress for a running task or task sequence.

    Instances of this class are returned from TaskRunner.runSingle() and .runSequence().

    Results are stored in self.results if the future is initialized with
    collectResults=True (this is False by default to avoid memory overuse).
    """

    def __init__(self, thread, task, nTasks, collectResults=False):
        self._taskThread = thread
        self._task = task
        self._nTasks = nTasks
        self._taskCount = 0
        self._collectResults = collectResults
        self.results = []
        Future.__init__(self)

    def percentDone(self):
        return self._taskCount / self._nTasks

    def stop(self):
        self._taskThread.stop(task=self._task)
        return Future.stop(self)

    def newFrame(self, frame):
        if self._collectResults:
            self.results.append(frame)
