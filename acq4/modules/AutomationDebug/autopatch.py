from __future__ import annotations

from typing import TYPE_CHECKING

from acq4.devices.PatchPipette import PatchPipette
from acq4.logging_config import get_logger
from acq4.util.future import future_wrap
from acq4.util.threadrun import runInGuiThread
from acq4.util.imaging.sequencer import run_image_sequence
from ..TaskRunner import TaskRunner

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
        man = win.module.manager
        multipatch_win = man.getModule('MultiPatch').win
        demo_dir = man.getCurrentDir().mkdir('AutopatchDemo', autoIncrement=True)
        while True:
            cell_dir = demo_dir.mkdir('cell', autoIncrement=True)
            cell_dir.setInfo({'dirType': 'Cell'})
            man.setCurrentDir(cell_dir)
            try:
                if not ppip.isTipClean():
                    _future.setState("Autopatch: cleaning pipette")
                    try:
                        _future.waitFor(ppip.setState("clean"), timeout=600)
                    except Exception:
                        _future.setState("Clean is unsafe to undo; quitting demo")
                        logger.exception("Error during pipette clean - quitting autopatch demo")
                        return
                    if not ppip.isTipClean():
                        _future.setState("Pipette still not clean after clean state; quitting demo")
                        return
                    _future.waitFor(win.scopeDevice.moveDip())

                cell = self._autopatchFindCell(_future)
                _future.setState("Autopatch: cell found")
                ppip.setState("bath")
                ppip.newPatchAttempt()
                runInGuiThread(multipatch_win.recordToggled, True)
                _future.setState("Autopatch: go above target")
                _future.waitFor(ppip.pipetteDevice.goAboveTarget("fast"))
                _future.setState("Autopatch: finding pipette tip")
                ppip.clampDevice.autoPipetteOffset()
                _future.waitFor(win.pipetteDevice.iterativelyFindTip())
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
                cell_dir.setInfo({'important': True})
                _future.setState("Autopatch: Whole cell; running task")
                self._autopatchRunTaskRunner(_future)

                _future.setState("Autopatch: Taking cell images")
                win.scopeDevice.loadPreset('GFP')
                self._saveStack("patched GFP cellfie", _future)
                # win.scopeDevice.loadPreset('tdTomato')
                # self._saveStack("patched tdTomato cellfie", _future)
                win.scopeDevice.loadPreset('brightfield')

                _future.setState("Autopatch: resealing")
                _future.waitFor(ppip.setState("reseal"), timeout=None)
                self._saveStack("resealed nucleus", _future)

                # start nucleus collection
                homeFut = ppip.setState("home with nucleus")

                # check on the resealed cell
                win.scopeDevice.loadPreset('GFP')
                _future.waitFor(
                    win.cameraDevice.moveCenterToGlobal(cell.position, "fast", name="center on resealed cell")
                )
                self._saveStack("GFP cell without nucleus", _future)
                _future.waitFor(homeFut)

                # collect the nucleus
                # TODO once we have motion planning
                # _future.waitFor(ppip.setState("collect"))
                # _future.waitFor(ppip.pipetteDevice.goAboveTarget("fast"))
                # self._saveStack("post-collection", _future)

                _future.waitFor(ppip.pipette.goHome())

            except (_future.StopRequested, _future.Stopped):
                raise
            except Exception:
                logger.exception("Error during protocol:")
                continue
            finally:
                runInGuiThread(multipatch_win.recordToggled, False)

    def _autopatchCellPatch(self, cell, _future):
        win = self._window
        ppip = win.patchPipetteDevice
        ppip.setState("approach")
        detect_finished = False
        while True:
            if (state := ppip.getState().stateName) not in ("approach", "cell detect", "contact cell"):
                if not detect_finished:
                    win.cameraDevice.moveCenterToGlobal(cell.position, "fast", name="center on cell during patching")
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

    def _saveStack(self, name, future):
        start = self.dev.pipetteDevice.targetPosition()[2] - (20e-6 / 2)
        end = start + 20e-6
        save_in = self.dev.dm.getCurrentDir().getDir(f"{name} stack", create=True)
        future.waitFor(
            run_image_sequence(
                self.dev.imagingDevice(),
                z_stack=(start, end, 1e-6),
                storage_dir=save_in,
                name="cellfie",
            )
        )
        future.sleep(5)  # pose for the user
