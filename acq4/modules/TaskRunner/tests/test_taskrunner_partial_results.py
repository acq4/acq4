"""TaskRunner's partial-result plumbing, run against a stand-in manager and fake devices."""

import importlib
import logging
import math
import threading
import time
from types import SimpleNamespace

import pytest

import pyqtgraph.configfile as configfile
from acq4.Manager import Task as ManagerTask
from acq4.devices.Device import DeviceTask
from acq4.modules.TaskRunner.TaskRunner import TaskRunner, TaskThread, partialUpdateReport
from acq4.modules.TaskRunner.analysisModules.AnalysisModule import AnalysisModule
from acq4.util import Qt
from acq4.util.partial_results import SettleSpec

INF = math.inf
taskRunnerModule = importlib.import_module("acq4.modules.TaskRunner.TaskRunner")


# ---- stand-ins -------------------------------------------------------------------------------

class _StreamingDeviceTask(DeviceTask):
    """Emits nPartials partial results from its own reader thread, then finishes."""

    def __init__(self, dev, cmd, parentTask):
        DeviceTask.__init__(self, dev, cmd, parentTask)
        self.nPartials = cmd.get('nPartials', 5)
        self.failPartial = cmd.get('failPartial', False)
        self.result = object()
        self._reader = None

    def settleSpecs(self):
        return {'ch': SettleSpec(0.01, 'causal')}

    def partialResult(self):
        if self.failPartial:
            raise RuntimeError("partial failure")
        return self.result

    def start(self):
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self):
        parent = self.parentTask()
        for _ in range(self.nPartials):
            parent.emitPartialResults()
            time.sleep(0.002)

    def isDone(self):
        return not self._reader.is_alive()

    def stop(self, abort=False):
        if self._reader is not None:
            self._reader.join(5)

    def getResult(self):
        return self.result


class _FakeDevice:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name

    def createTask(self, cmd, parentTask):
        return _StreamingDeviceTask(self, cmd, parentTask)


class _FakeLocker:
    def lock(self):
        pass

    def unlock(self):
        pass


class _FakeManager:
    """The parts of Manager that TaskRunner, UiState and Manager.Task use."""

    def __init__(self, configDir, devNames=()):
        self.configDir = configDir
        self.devices = {n: _FakeDevice(n) for n in devNames}
        self.globalHalt = SimpleNamespace(check=lambda: None)
        self.files = {}
        self.tasks = []

    # Manager.Task
    def getDevice(self, name):
        return self.devices[name]

    def reserveDevices(self, devices, timeout=10.0, reserver=None):
        return _FakeLocker()

    def _taskStarted(self, task):
        pass

    def _taskFinished(self, task):
        pass

    def createTask(self, cmd):
        task = ManagerTask(self, cmd)
        self.tasks.append(task)
        return task

    # TaskRunner / UiState
    def declareInterface(self, *args):
        pass

    def listDevices(self):
        return []

    def readConfigFile(self, fileName, missingOk=True):
        return self.files.get(fileName, {})

    def writeConfigFile(self, data, fileName):
        self.files[fileName] = data

    def moduleHasQuit(self, mod):
        pass


class _RecordingTaskGui(Qt.QWidget):
    """Dock widget that records what TaskRunner hands it."""

    sigSequenceChanged = Qt.Signal(object)

    def __init__(self, cmd=None, fail=False):
        Qt.QWidget.__init__(self)
        self.cmd = cmd or {}
        self.fail = fail
        self.partials = []
        self.results = []

    def handlePartialResult(self, result, params):
        self.partials.append((result, params))
        if self.fail:
            raise RuntimeError("dock failure")

    def handleResult(self, result, params):
        self.results.append((result, params))

    def generateTask(self, params):
        return dict(self.cmd)

    def prepareTaskStart(self):
        pass

    def listSequence(self):
        return {}

    def describe(self, params=None):
        return {}

    def saveState(self):
        return {}

    def quit(self):
        pass


def _addDock(runner, name, gui):
    dock = Qt.QDockWidget(name)
    dock.setWidget(gui)
    runner.docks[name] = dock
    runner.currentTask.addDevice(name)
    return gui


@pytest.fixture
def runner(qtbot, tmp_path, monkeypatch):
    manager = _FakeManager(str(tmp_path), devNames=['Dev'])
    monkeypatch.setattr("acq4.Manager.Manager.single", manager, raising=False)
    taskDir = tmp_path / 'protocols'
    taskDir.mkdir()
    tr = TaskRunner(manager, 'TaskRunner', {'taskDir': str(taskDir)})
    yield tr
    tr.taskThread.wait(5000)
    tr.win.close()


# ---- partialUpdateReport ---------------------------------------------------------------------

def test_report_matches_documented_layout():
    specs = {'Clamp1': {
        'primary': SettleSpec(INF, 'denoise needs the whole record'),
        'secondary': SettleSpec(0.034),
    }}
    assert partialUpdateReport(0.05, specs) == (
        "Clamp1\n"
        "  primary:   no updates until the task ends (denoise needs the whole record)\n"
        "  secondary: 84 ms expected lag"
    )


def test_report_lists_every_device_and_lag_reasons():
    specs = {
        'Clamp1': {'primary': SettleSpec(0.0, 'causal')},
        'Camera': {'frames': SettleSpec(INF, 'waits for the exposure channel')},
    }
    assert partialUpdateReport(0.1, specs) == (
        "Clamp1\n"
        "  primary: 100 ms expected lag (causal)\n"
        "Camera\n"
        "  frames: no updates until the task ends (waits for the exposure channel)"
    )


def test_report_device_level_component_first():
    specs = {'DAQ': {'ai0': SettleSpec(0.0), '': SettleSpec(INF, 'chunk exceeds the record')}}
    assert partialUpdateReport(0.05, specs) == (
        "DAQ\n"
        "  no updates until the task ends (chunk exceeds the record)\n"
        "  ai0: 50 ms expected lag"
    )


@pytest.mark.parametrize('interval, specs', [
    (0.05, {}),
    (0.05, {'Clamp1': {'primary': SettleSpec(0.0), 'secondary': SettleSpec(0.034)}}),
    (None, {'Clamp1': {'primary': SettleSpec(INF, 'denoise')}}),  # updates off
])
def test_report_nothing_to_report(interval, specs):
    assert partialUpdateReport(interval, specs) == ''


def test_report_errors_shown_even_without_spec_problems():
    specs = {'Clamp1': {'primary': SettleSpec(0.0)}}
    text = partialUpdateReport(0.05, specs, ["handler removed", "device disabled"])
    assert text == "Errors\n  handler removed\n  device disabled"
    assert partialUpdateReport(None, {}, ["x"]) == "Errors\n  x"


def test_report_errors_follow_spec_problems():
    specs = {'Clamp1': {'primary': SettleSpec(INF)}}
    assert partialUpdateReport(0.05, specs, ["boom"]) == (
        "Clamp1\n  primary: no updates until the task ends\nErrors\n  boom"
    )


# ---- TaskThread ------------------------------------------------------------------------------

def _runThread(qtbot, manager, cmd):
    thread = TaskThread(SimpleNamespace(manager=manager, _reduceMemoryUsage=False))
    rec = SimpleNamespace(partials=[], partialThreads=set(), specs=[], errors=[], frames=[])

    def onPartial(frame):
        rec.partials.append(frame)
        rec.partialThreads.add(threading.get_ident())

    thread.sigPartialFrame.connect(onPartial, type=Qt.Qt.DirectConnection)
    thread.sigSettleSpecs.connect(lambda interval, specs: rec.specs.append((interval, specs)))
    thread.sigPartialResultErrors.connect(rec.errors.append)
    thread.sigNewFrame.connect(rec.frames.append)
    thread.startTask(cmd)
    assert thread.wait(5000)
    qtbot.waitUntil(lambda: len(rec.frames) == 1, timeout=2000)
    return rec


def _cmd(protocol=None, **devCmd):
    return {'protocol': {'duration': 0.0, 'cycleTime': 0.0, 'timeout': None, **(protocol or {})}, 'Dev': devCmd}


def test_task_thread_emits_partial_frames(qtbot, tmp_path):
    manager = _FakeManager(str(tmp_path), devNames=['Dev'])
    cmd = _cmd({'updateInterval': 0.05}, nPartials=5)
    rec = _runThread(qtbot, manager, cmd)

    devResult = manager.tasks[0].tasks['Dev'].result
    assert len(rec.partials) == 5
    assert threading.get_ident() not in rec.partialThreads  # emitted on the device's reader thread
    for frame in rec.partials:
        assert set(frame) == {'params', 'cmd', 'result'}
        assert frame['params'] == {}
        assert frame['cmd'] is cmd
        assert set(frame['result']) == {'protocol', 'Dev'}
        assert frame['result']['Dev'] is devResult
    assert rec.specs == [(0.05, {'Dev': {'ch': SettleSpec(0.01, 'causal')}})]
    assert rec.frames[0]['result']['Dev'] is devResult
    assert rec.errors == []


def test_task_thread_inert_without_update_interval(qtbot, tmp_path):
    manager = _FakeManager(str(tmp_path), devNames=['Dev'])
    rec = _runThread(qtbot, manager, _cmd(nPartials=5))
    assert manager.tasks[0]._partialHandlers == ()
    assert rec.partials == []
    assert rec.specs == [(None, {})]
    assert rec.errors == []


def test_task_thread_reports_partial_result_errors(qtbot, tmp_path, caplog):
    manager = _FakeManager(str(tmp_path), devNames=['Dev'])
    with caplog.at_level(logging.ERROR, logger='acq4'):
        rec = _runThread(qtbot, manager, _cmd({'updateInterval': 0.05}, nPartials=3, failPartial=True))
    qtbot.waitUntil(lambda: len(rec.errors) == 1, timeout=2000)
    assert len(rec.errors[0]) == 1
    assert "'Dev'" in rec.errors[0][0]
    assert all('Dev' not in f['result'] for f in rec.partials)


# ---- TaskRunner module -----------------------------------------------------------------------

def test_update_controls_and_generate_task(runner):
    ui = runner.ui
    assert not ui.protoUpdateCheck.isChecked()
    assert ui.protoUpdateIntervalSpin.value() == pytest.approx(0.05)
    assert not ui.protoUpdateIntervalSpin.isEnabled()
    assert runner.generateTask(None)['protocol']['updateInterval'] is None

    ui.protoUpdateCheck.setChecked(True)
    assert ui.protoUpdateIntervalSpin.isEnabled()
    assert runner.generateTask(None)['protocol']['updateInterval'] == pytest.approx(0.05)

    ui.protoUpdateIntervalSpin.setValue(0.2)
    assert runner.generateTask(None)['protocol']['updateInterval'] == pytest.approx(0.2)

    ui.protoUpdateCheck.setChecked(False)
    assert runner.generateTask(None)['protocol']['updateInterval'] is None


def test_task_files_round_trip_and_old_files_get_defaults(runner, tmp_path):
    ui = runner.ui
    ui.protoUpdateCheck.setChecked(True)
    ui.protoUpdateIntervalSpin.setValue(0.2)
    path = str(tmp_path / 'withKeys.cfg')
    runner.currentTask.write(path)

    oldPath = str(tmp_path / 'old.cfg')
    conf = configfile.readConfigFile(path)
    del conf['protocol']['conf']['liveUpdate']
    del conf['protocol']['conf']['liveUpdateInterval']
    configfile.writeConfigFile(conf, oldPath)

    runner.loadTask(SimpleNamespace(name=lambda: oldPath))
    assert not ui.protoUpdateCheck.isChecked()
    assert ui.protoUpdateIntervalSpin.value() == pytest.approx(0.05)
    assert not ui.protoUpdateIntervalSpin.isEnabled()
    assert runner.generateTask(None)['protocol']['updateInterval'] is None

    runner.loadTask(SimpleNamespace(name=lambda: path))
    assert ui.protoUpdateCheck.isChecked()
    assert ui.protoUpdateIntervalSpin.isEnabled()
    assert runner.generateTask(None)['protocol']['updateInterval'] == pytest.approx(0.2)

    runner.newTask()
    assert not ui.protoUpdateCheck.isChecked()
    assert ui.protoUpdateIntervalSpin.value() == pytest.approx(0.05)


def test_warning_indicator(qtbot, runner):
    btn = runner.ui.protoUpdateWarnBtn
    assert btn.text() == '!'
    assert not btn.isCheckable()
    assert btn.isHidden()

    problem = {'Clamp1': {'primary': SettleSpec(INF, 'denoise'), 'secondary': SettleSpec(0.034)}}
    runner.taskSettleSpecs(0.05, problem)
    assert not btn.isHidden()
    assert btn.toolTip() == partialUpdateReport(0.05, problem)
    assert 'border: 2px solid #F00' in btn.styleSheet()

    runner.showPartialUpdateReport()
    qtbot.waitUntil(Qt.QToolTip.isVisible, timeout=2000)
    assert Qt.QToolTip.text() == btn.toolTip()
    Qt.QToolTip.hideText()

    fine = {'Clamp1': {'primary': SettleSpec(0.0)}}
    runner.taskSettleSpecs(0.05, fine)  # next task start resets
    assert btn.isHidden()

    runner.taskPartialResultErrors(["handler removed"])
    assert not btn.isHidden()
    assert btn.toolTip() == partialUpdateReport(0.05, fine, ["handler removed"])

    # errors outlive later task starts in the same sequence or loop, without duplicates
    runner.taskSettleSpecs(0.05, fine)
    runner.taskPartialResultErrors(["handler removed", "device disabled"])
    assert btn.toolTip() == partialUpdateReport(0.05, fine, ["handler removed", "device disabled"])

    runner.clearPartialResultErrors()  # the user starts a new run
    assert btn.isHidden()

    runner.taskSettleSpecs(None, {})
    assert btn.isHidden()
    assert btn.toolTip() == ''


def test_partial_result_errors_are_capped(runner):
    msgs = [f"error {i}" for i in range(runner.maxPartialResultErrors + 5)]
    runner.taskSettleSpecs(0.05, {})
    runner.taskPartialResultErrors(msgs)
    assert runner._partialUpdateState[2] == msgs[-runner.maxPartialResultErrors:]


def test_handle_partial_frame_dispatches_every_partial(qtbot, runner, caplog):
    good = _addDock(runner, 'Dev', _RecordingTaskGui())
    bad = _addDock(runner, 'Bad', _RecordingTaskGui(fail=True))
    emitted = []
    runner.sigPartialFrame.connect(emitted.append)

    frames = []
    with caplog.at_level(logging.ERROR, logger='acq4'):
        for i in range(20):
            frame = {'params': {'i': i}, 'cmd': {}, 'result': {'protocol': {}, 'Dev': i, 'Bad': i}}
            frames.append(frame)
            runner.handlePartialFrame(frame)

    assert good.partials == [(i, {'i': i}) for i in range(20)]
    assert len(bad.partials) == 20
    assert emitted == frames
    failures = [r for r in caplog.records if "partial result from device 'Bad'" in r.getMessage()]
    assert len(failures) == 1  # logged once per run

    runner.taskSettleSpecs(None, {})  # next task start re-arms logging
    with caplog.at_level(logging.ERROR, logger='acq4'):
        runner.handlePartialFrame(frames[0])
    failures = [r for r in caplog.records if "partial result from device 'Bad'" in r.getMessage()]
    assert len(failures) == 2


def test_partial_path_never_collects_garbage(runner, monkeypatch):
    calls = []
    monkeypatch.setattr(taskRunnerModule.gc, 'collect', lambda *a: calls.append(a))
    runner._reduceMemoryUsage = True
    _addDock(runner, 'Dev', _RecordingTaskGui())
    frame = {'params': {}, 'cmd': {}, 'result': {'protocol': {}, 'Dev': 1}}
    for _ in range(10):
        runner.handlePartialFrame(frame)
    assert calls == []
    runner.handleFrame(frame)  # the final-frame path still does
    assert len(calls) == 1


def test_partial_frames_queued_to_gui_thread(qtbot, runner):
    gui = _addDock(runner, 'Dev', _RecordingTaskGui())
    threads = []
    gui.handlePartialResult = lambda result, params: threads.append(threading.get_ident())
    frame = {'params': {}, 'cmd': {}, 'result': {'protocol': {}, 'Dev': 1}}
    t = threading.Thread(target=lambda: [runner.taskThread.sigPartialFrame.emit(frame) for _ in range(3)])
    t.start()
    t.join()
    assert threads == []
    qtbot.waitUntil(lambda: len(threads) == 3, timeout=2000)
    assert set(threads) == {threading.get_ident()}


def test_run_single_end_to_end(qtbot, runner):
    gui = _addDock(runner, 'Dev', _RecordingTaskGui(cmd={'nPartials': 4}))
    emitted = []
    runner.sigPartialFrame.connect(emitted.append)
    runner.ui.protoUpdateCheck.setChecked(True)
    runner.ui.protoDurationSpin.setValue(0.001)

    runner.runSingle(store=False)
    qtbot.waitUntil(lambda: len(gui.results) == 1, timeout=5000)

    final = gui.results[0][0]
    assert len(gui.partials) == 4
    assert all(result is final for result, _ in gui.partials)
    assert len(emitted) == 4
    assert runner._partialUpdateState == (0.05, {'Dev': {'ch': SettleSpec(0.01, 'causal')}}, [])
    assert runner.ui.protoUpdateWarnBtn.isHidden()


# ---- AnalysisModule --------------------------------------------------------------------------

class _RecordingAnalysis(AnalysisModule):
    def __init__(self, taskRunner):
        AnalysisModule.__init__(self, taskRunner)
        self.partials = []

    def newPartialFrame(self, frame):
        self.partials.append(frame)


def test_analysis_module_default_is_noop(qtbot, runner):
    module = AnalysisModule(runner)
    qtbot.addWidget(module)
    assert module.newPartialFrame({'params': {}, 'cmd': {}, 'result': {}}) is None
    runner.sigPartialFrame.emit({'params': {}, 'cmd': {}, 'result': {}})
    module.quit()


def test_analysis_module_receives_partial_frames_until_quit(qtbot, runner):
    module = _RecordingAnalysis(runner)
    qtbot.addWidget(module)
    frame = {'params': {}, 'cmd': {}, 'result': {'protocol': {}}}
    runner.handlePartialFrame(frame)
    runner.handlePartialFrame(frame)
    assert module.partials == [frame, frame]

    module.quit()
    runner.handlePartialFrame(frame)
    assert len(module.partials) == 2
