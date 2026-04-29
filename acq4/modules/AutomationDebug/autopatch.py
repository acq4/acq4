from __future__ import annotations

from typing import TYPE_CHECKING, Any

from acq4.devices.PatchPipette import PatchPipette
from acq4.logging_config import get_logger
from acq4.util.future import Future, Stopped, sleep
from acq4.util.threadrun import runInGuiThread
from acq4.util.imaging.sequencer import run_image_sequence
from ..TaskRunner import TaskRunner
from ...Manager import Manager
from ...util.DataManager import DirHandle

if TYPE_CHECKING:
    from .AutomationDebug import AutomationDebugWindow

logger = get_logger(__name__)


class Autopatcher:
    def __init__(self, window: AutomationDebugWindow):
        self._window = window

    def _handleAutopatchDemoFinish(self, fut):
        win = self._window
        win.sigWorking.emit(False)
        win.ui.reuseLastCellBtn.setEnabled(win._cell is not None)

    def _autopatchDemo(self):
        win = self._window
        win.sigWorking.emit(win.ui.autopatchDemoBtn)
        ppip: PatchPipette = win.patchPipetteDevice
        man = win.module.manager
        data_manager = runInGuiThread(man.getModule, "Data Manager")
        multipatch_win = runInGuiThread(man.getModule, 'MultiPatch').win
        demo_dir = self._makeValidDemoDir()
        man.setCurrentDir(demo_dir)
        win.cameraDevice.scopeDev.findSurfaceDepth(win.cameraDevice)
        try:
            while True:
                cell_dir = runInGuiThread(data_manager.createNewFolder, "Cell")
                try:
                    started_clean = ppip.isTipClean()
                    if not started_clean:
                        logger.debug("Autopatch: cleaning pipette")
                        try:
                            ppip.setState("clean", nextState="bath").wait(timeout=600)
                        except Exception:
                            logger.exception("Error during pipette clean - quitting autopatch demo")
                            return
                        if not ppip.isTipClean():
                            logger.debug("Pipette still not clean after clean state; quitting demo")
                            return
                        win.scopeDevice.moveDip().wait()

                    cell = self._autopatchFindCell()
                    if cell is None:
                        logger.debug("No cells found; quitting demo")
                        return
                    logger.debug("Autopatch: cell found")
                    ppip.newPatchAttempt()
                    runInGuiThread(multipatch_win.ui.recordBtn.setChecked, True)
                    logger.debug("Autopatch: go above target")
                    ppip.pipetteDevice.goAboveTarget("fast").wait()
                    logger.debug("Autopatch: finding pipette tip")
                    ppip.clampDevice.autoPipetteOffset()
                    win.pipetteDevice.iterativelyFindTip()
                    if started_clean:
                        logger.debug("Quick clean")
                        ppip.sonicatorDevice.doProtocol("quick clean")

                    logger.debug("Autopatch: go approach")
                    ppip.pipetteDevice.goApproach("fast").wait()
                    try:
                        logger.debug("Autopatch: patch cell")
                        logger.warning("Autopatch: Start cell patching")
                        state = self._autopatchCellPatch(cell)
                    except Exception:
                        logger.exception("Autopatch: Exception during cell patching")
                        raise

                    logger.warning(f"Autopatch: Cell patching finished: {state}")
                    if state != "whole cell":
                        logger.warning("Autopatch: Next cell!")
                        continue
                    cell_dir.setInfo({'important': True})
                    logger.debug("Autopatch: Whole cell; running task")
                    self._autopatchRunTaskRunner()

                    logger.debug("Autopatch: Taking cell images")
                    win.scopeDevice.loadPreset('GFP')
                    self._saveStack("patched GFP cellfie")
                    # win.scopeDevice.loadPreset('tdTomato')
                    # self._saveStack("patched tdTomato cellfie")
                    win.scopeDevice.loadPreset('brightfield')

                    # TODO too slow for today's demo
                    # logger.debug("Autopatch: resealing")
                    # ppip.setState("reseal").wait(timeout=None)
                    # self._saveStack("resealed nucleus")
                    #
                    # # start nucleus collection
                    # homeFut = ppip.setState("home with nucleus")
                    #
                    # # check on the resealed cell
                    # win.scopeDevice.loadPreset('GFP')
                    # win.cameraDevice.moveCenterToGlobal(cell.position, "fast", name="center on resealed cell").wait()
                    # self._saveStack("GFP cell without nucleus")
                    # homeFut.wait()

                    # collect the nucleus
                    # TODO once we have motion planning
                    # ppip.setState("collect").wait()
                    # ppip.pipetteDevice.goAboveTarget("fast").wait()
                    # self._saveStack("post-collection")

                    ppip.pipetteDevice.goHome().wait()
                    ppip.setState("bath")

                except Stopped:
                    raise
                except Exception:
                    logger.exception("Error during protocol:")
                    continue
                finally:
                    man.setCurrentDir(cell_dir.parent())
                    runInGuiThread(multipatch_win.ui.recordBtn.setChecked, False)
        finally:
            man.setCurrentDir(demo_dir.parent())

    def _makeValidDemoDir(self) -> DirHandle:
        man = self._window.module.manager
        parent = man.getCurrentDir()
        inappropriate_parents = ("autopatchdemo", "cell")
        while any(name in parent.name().lower() for name in inappropriate_parents):
            parent = parent.parent()
        return parent.mkdir('AutopatchDemo', autoIncrement=True)

    def _autopatchCellPatch(self, cell):
        win = self._window
        ppip = win.patchPipetteDevice
        ppip.setState("approach", startANewCell=False)
        detect_finished = False
        while True:
            if (state := ppip.getState().stateName) not in ("approach", "cell detect", "contact cell"):
                if not detect_finished:
                    win.cameraDevice.moveCenterToGlobal(
                        cell.position, "fast", name="center on cell during patching"
                    ).wait()
                    detect_finished = True
            if state in ("whole cell", "bath", "broken", "fouled"):
                logger.debug(f"Exiting patch loop - ended in state {state}")
                break
            sleep(0.1)
        return state

    def _autopatchFindCell(self):
        win = self._window
        if not win._unranked_cells:
            logger.debug("Autopatch: searching for cells")
            return None
            # surf = win.cameraDevice.scopeDev.findSurfaceDepth(win.cameraDevice)
            # win.cameraDevice.setFocusDepth(surf - 60e-6, "fast").wait()
            z_stack = Future(win._detector._detectNeuronsZStack)
            z_stack.sigFinished.connect(win._detector._handleDetectResults)
            z_stack.wait(timeout=600)

        logger.debug("Autopatch: checking selected cell")
        cell = win._unranked_cells.pop(0)
        win._ranked_cells.append(cell)
        win.patchPipetteDevice.setCell(cell)
        win._cell = cell
        # cell.sigPositionChanged.connect(win._feature_tracker._updatePipetteTarget)

        # stack = win._current_classification_stack or win._current_detection_stack
        # if (pos - margin) not in stack or (pos + margin) not in stack:
        # stack = None
        try:
            cell.initializeTracker(win.cameraDevice).wait()
        except Stopped:
            raise
        except ValueError as e:
            if win._mockDemo:
                logger.info(f"Autopatch: Mocking cell despite {e}")
                return cell
            logger.info(f"Cell moved too much? {e}\nRetrying")
            return self._autopatchFindCell()
        logger.info(f"Autopatch: Cell found at {cell.position}")
        return cell

    def _autopatchRunTaskRunner(self):
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
        runInGuiThread(taskrunner.runSequence, store=False).wait(
            timeout=max(30, expected_duration * 20),
        )
        logger.warning("Autopatch: Task runner sequence completed.")

    def _saveStack(self, name):
        ppip = self._window.patchPipetteDevice
        start = ppip.pipetteDevice.targetPosition()[2] - (20e-6 / 2)
        end = start + 20e-6
        save_in = ppip.dm.getCurrentDir().getDir(f"{name} stack", create=True)
        Future(
            run_image_sequence,
            (ppip.imagingDevice(),),
            dict(z_stack=(start, end, 1e-6), storage_dir=save_in, name="cellfie"),
        ).wait()
        sleep(5)  # pose for the user
