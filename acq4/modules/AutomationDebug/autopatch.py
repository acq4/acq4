from __future__ import annotations

from typing import TYPE_CHECKING

from acq4.logging_config import get_logger
from acq4.util.future import Future, future_wrap
from acq4.util.threadrun import runInGuiThread

if TYPE_CHECKING:
    from .AutomationDebug import AutomationDebugWindow

logger = get_logger(__name__)


class Autopatcher:
    def __init__(self, window: AutomationDebugWindow):
        self._window = window

    def _handleAutopatchDemoFinish(self, fut):
        self._window.sigWorking.emit(False)

    @future_wrap
    def _autopatchDemo(self, _future):
        win = self._window
        win.sigWorking.emit(win.ui.autopatchDemoBtn)
        ppip: PatchPipette = win.patchPipetteDevice
        cleaning = None
        while True:
            try:
                if not ppip.isTipClean():
                    cleaning = ppip.setState("clean")
                if cleaning is not None:
                    _future.setState("Autopatch: cleaning pipette")
                    _future.waitFor(cleaning, timeout=600)
                    cleaning = None
                cell = self._autopatchFindCell(_future)
                _future.setState("Autopatch: cell found")
                ppip.setState("bath")
                ppip.newPatchAttempt()
                _future.setState("Autopatch: go above target")
                _future.waitFor(ppip.pipetteDevice.goAboveTarget("fast"))
                _future.setState("Autopatch: finding pipette tip")
                ppip.clampDevice.autoPipetteOffset()
                self._autopatchFindPipetteTip(_future)
                _future.setState("Autopatch: go approach")
                _future.waitFor(ppip.pipetteDevice.goApproach("fast"))
                cell.enableTracking()
                try:
                    _future.setState("Autopatch: patch cell")
                    logger.warning("Autopatch: Start cell patching")
                    state = self._autopatchCellPatch(cell, _future)
                except Exception:
                    logger.exception("Autopatch: Exception during cell patching")
                    raise

                logger.warning(f"Autopatch: Cell patching finished: {state}")
                if state != "whole cell":
                    logger.warning("Autopatch: Next cell!")
                    continue
                _future.setState("Autopatch: Whole cell; running task")
                self._autopatchRunTaskRunner(_future)

                _future.setState("Autopatch: Taking cell images")
                win.scopeDevice.loadPreset('GFP')
                _future.sleep(5)
                # win.scopeDevice.loadPreset('tdTomato')
                # _future.sleep(5)
                win.scopeDevice.loadPreset('brightfield')

                _future.setState("Autopatch: resealing")
                _future.waitFor(ppip.setState("reseal"), timeout=None)
                _future.sleep(5)  # pose with nucleus

                # check on the resealed cell
                homeFut = ppip.pipette.goHome()
                win.scopeDevice.loadPreset('GFP')
                _future.waitFor(
                    win.cameraDevice.moveCenterToGlobal(cell.position, "fast")
                )
                _future.sleep(5)  # pose with nucleus
                _future.waitFor(homeFut)

            except (_future.StopRequested, _future.Stopped):
                raise
            except Exception:
                logger.exception("Error during protocol:")
                continue

    def _autopatchCellPatch(self, cell, _future):
        win = self._window
        ppip = win.patchPipetteDevice
        ppip.setState("approach")
        detect_finished = False
        while True:
            if (state := ppip.getState().stateName) not in ("approach", "cell detect", "contact cell"):
                if not detect_finished:
                    win.cameraDevice.moveCenterToGlobal(cell.position, "fast")
                    detect_finished = True
            if state in ("whole cell", "bath", "broken", "fouled"):
                _future.setState(f"Exiting patch loop - ended in state {state}")
                break
            _future.sleep(0.1)
        return state

    def _autopatchFindCell(self, _future):
        win = self._window
        if not win._unranked_cells:
            _future.setState("Autopatch: searching for cells")
            # surf = _future.waitFor(
            #     win.cameraDevice.scopeDev.findSurfaceDepth(win.cameraDevice)
            # ).getResult()
            # _future.waitFor(win.cameraDevice.setFocusDepth(surf - 60e-6, "fast"))
            z_stack = win._detector._detectNeuronsZStack()
            z_stack.sigFinished.connect(win._detector._handleDetectResults)
            _future.waitFor(z_stack, timeout=600)

        _future.setState("Autopatch: checking selected cell")
        cell = win._unranked_cells.pop(0)
        win._ranked_cells.append(cell)
        win.patchPipetteDevice.setCell(cell)
        win._cell = cell
        # cell.sigPositionChanged.connect(win._feature_tracker._updatePipetteTarget)

        # stack = win._current_classification_stack or win._current_detection_stack
        # if (pos - margin) not in stack or (pos + margin) not in stack:
        # stack = None
        try:
            _future.waitFor(cell.initializeTracker(win.cameraDevice))
        except _future.StopRequested:
            raise
        except ValueError as e:
            if win._mockDemo:
                logger.info(f"Autopatch: Mocking cell despite {e}")
                return cell
            logger.info(f"Cell moved too much? {e}\nRetrying")
            return self._autopatchFindCell(_future)
        logger.info(f"Autopatch: Cell found at {cell.position}")
        return cell

    def _autopatchFindPipetteTip(self, _future):
        win = self._window
        if win._mockDemo:
            logger.info("Autopatch: Mock pipette tip detection")
            return
        pip = win.pipetteDevice
        pos = pip.tracker.findTipInFrame()
        _future.waitFor(win.cameraDevice.moveCenterToGlobal(pos, "fast"))
        pos = pip.tracker.findTipInFrame()
        _future.waitFor(win.cameraDevice.moveCenterToGlobal(pos, "fast"))
        pos = pip.tracker.findTipInFrame()
        pip.resetGlobalPosition(pos)
        logger.info(f"Autopatch: Tip found at {pos}")

    def _autopatchRunTaskRunner(self, _future):
        win = self._window
        man = win.module.manager
        ppip = win.patchPipetteDevice
        clampName = ppip.clampDevice.name()
        taskrunner: TaskRunner | None = None
        for mod in man.listInterfaces('taskRunnerModule'):
            mod = man.getModule(mod)
            if clampName in mod.docks:
                taskrunner = mod
                break
        if taskrunner is None:
            logger.warning(f"No task runner found that uses {clampName}")
            return

        expected_duration = (
            taskrunner.sequenceInfo["period"] * taskrunner.sequenceInfo["totalParams"]
        )
        _future.waitFor(
            # runInGuiThread(taskrunner.runSequence, store=True, storeDirHandle=self.dh), timeout=expected_duration
            runInGuiThread(taskrunner.runSequence, store=False),
            timeout=max(30, expected_duration * 20),
        )
        logger.warning("Autopatch: Task runner sequence completed.")
