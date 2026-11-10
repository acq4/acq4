import json
import os
import re

from collections import OrderedDict
from typing import List

import numpy as np
import pyqtgraph as pg
from acq4 import getManager
from acq4.devices.ControlSurface import (
    ControlInUse,
    ControlSurface,
    UnsupportedControlFeature,
)
from acq4.devices.PatchPipette import PatchPipette
from acq4.logging_config import get_logger
from acq4.modules.Module import Module
from acq4.util import Qt, ptime
from acq4.util.multipatch_log_writer import MultiPatchLogWriter, eventToRecord
from acq4.util.ui_state import UiState
from .mockPatch import MockPatch
from .pipetteControl import PipetteControl
from ...devices.PatchPipette.statemanager import PatchPipetteStateManager
from ...util.task import MultiFuture, asynch, raise_errors, run_in_gui_thread, throughline
from ...util.json_encoder import ACQ4JSONEncoder

Ui_MultiPatch = Qt.importTemplate('.multipatchTemplate')

logger = get_logger(__name__)

#: Default control-surface layout for the fixed (not per-pipette) buttons, as
#: ``{name of a button on self.ui: (row, col)}``. These are the positions MultiPatch has
#: always used on an X-Keys, and are the default of the ``actions:`` config option.
DEFAULT_ACTION_KEYS = {
    'sealBtn': (0, 0),
    'setTargetBtn': (0, 2),
    'cellDetectBtn': (1, 0),
    'hideMarkersBtn': (1, 2),
    'coarseSearchBtn': (2, 0),
    'fineSearchBtn': (2, 1),
    'setTipBtn': (2, 2),
    'aboveTargetBtn': (3, 1),
    'approachBtn': (3, 2),
    'slowBtn': (4, 1),
    'fastBtn': (4, 2),
    'reSealBtn': (5, 0),
    'cleanBtn': (5, 2),
    'homeBtn': (6, 2),
    'recordBtn': (7, 2),
}

#: Fixed buttons whose control lights while the button is checked.
CHECKABLE_ACTIONS = frozenset(
    {'setTargetBtn', 'hideMarkersBtn', 'setTipBtn', 'slowBtn', 'fastBtn', 'recordBtn'}
)

#: Per-pipette buttons, by row within the per-pipette block. One column per pipette.
PIPETTE_ROW_ACTIONS = ('activeBtn', 'lockBtn', 'selectBtn', 'tipBtn', 'targetBtn')

#: First grid column of the per-pipette block; lower columns hold the fixed buttons.
PIPETTE_COLUMN_OFFSET = 4

#: Colours standing in for a two-LED backlight state on a surface that takes a colour
#: instead. Both LEDs lit is spelled magenta because that is what a blue and a red LED lit
#: together look like, and because an X-Keys key can show it -- white, with its green
#: component, cannot be shown by two such LEDs at all. Flash is lost; the indicator is not.
BACKLIGHT_COLORS = {(False, False): 'k', (True, False): 'b', (False, True): 'r', (True, True): 'm'}


class MultiPatch(Module):
    """
    Config
    ----------
    enableMockPatch : bool
        Whether to allow mock patching.
    useStacksForSavedTipImages : bool
        Whether to use z-stacks when saving tip images.
    controlSurface : dict
        A control surface to drive this window from, as
        ``{'device': name, 'page': int, 'actions': {'buttonName': [row, col]}}``. *page*
        defaults to 0 and *actions* to :data:`DEFAULT_ACTION_KEYS`. Columns from
        :data:`PIPETTE_COLUMN_OFFSET` onwards are claimed as one column per pipette, with
        one row per entry in :data:`PIPETTE_ROW_ACTIONS`. The surface's buttons need
        ``setBacklight`` or ``setColor`` for the state indicators; controls it does not
        offer are skipped
        with a warning. Superseded spelling: ``xkeysDevice: name``.
    """
    moduleDisplayName = "MultiPatch"
    moduleCategory = "Acquisition"

    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)

        self.win = MultiPatchWindow(self)
        self.win.show()

    def quit(self):
        self.win.stopRecording()
        self.win.saveConfig()
        self.win.releaseControls()
        return Module.quit(self)


class MultiPatchWindow(Qt.QWidget):
    def __init__(self, module):
        # Runs while the record button is on; None otherwise.
        self._logWriter = None
        self.eventHistory = []
        self._pipsToSetTips = []
        self._setTargetPips = []
        self._profileEditor = None

        Qt.QWidget.__init__(self)
        self.module = module

        self.ui = Ui_MultiPatch()
        self.ui.setupUi(self)

        self.setWindowTitle('Multipatch')
        self.setWindowIcon(Qt.QIcon(os.path.join(os.path.dirname(__file__), 'icon.png')))

        man = getManager()
        pipNames = man.listInterfaces('patchpipette')
        self.pips = [man.getDevice(name) for name in pipNames]
        self.pips.sort(key=lambda p: int(re.sub(r'[^\d]+', '', p.name())))

        microscopeNames = man.listInterfaces('microscope')
        if len(microscopeNames) == 1:
            self.microscope = man.getDevice(microscopeNames[0])
            self.microscope.sigSurfaceDepthChanged.connect(self.surfaceDepthChanged)
        elif len(microscopeNames) == 0:
            # flying blind?
            self.microscope = None
        else:
            raise AssertionError("Currently only 1 microscope is supported")

        self.pipCtrls = []
        for i, pip in enumerate(self.pips):
            pip.sigMoveStarted.connect(self.pipetteMoveStarted)
            pip.sigMoveFinished.connect(self.pipetteMoveFinished)
            if isinstance(pip, PatchPipette):
                pip.sigNewEvent.connect(self.pipetteEvent)
                if pip.clampDevice is not None:
                    pip.clampDevice.sigTestPulseEnabled.connect(self.pipetteTestPulseEnabled)
            ctrl = PipetteControl(pip, self)
            if i > 0:
                ctrl.hideHeader()

            # insert mock patching ui if requested
            self.ui.matrixLayout.addWidget(ctrl, i, 0)
            if module.config.get('enableMockPatch', False):
                pip.mockpatch = MockPatch(pip)
                self.ui.matrixLayout.addWidget(pip.mockpatch.widget, i, 1)

            # Add this pipette's plots to the right panel
            plotContainer = Qt.QWidget()
            plotContainerLayout = Qt.QHBoxLayout(plotContainer)
            plotContainerLayout.setContentsMargins(0, 0, 0, 0)
            plotContainerLayout.setSpacing(0)
            for plt in ctrl.plots:
                plotContainerLayout.addWidget(plt)
            self.ui.plotsLayout.addWidget(plotContainer)

            pip.sigActiveChanged.connect(self.pipetteActiveChanged)
            ctrl.sigSelectChanged.connect(self.pipetteSelectChanged)
            ctrl.sigLockChanged.connect(self.pipetteLockChanged)
            ctrl.sigPlotModesChanged.connect(self.setPlotModes)

            self.pipCtrls.append(ctrl)

        # load profile configurations from old location
        for name, profile in module.config.get('patchProfiles', {}).items():
            PatchPipetteStateManager.addProfile(name, profile, overwrite=True)

        # set up patch profile menu
        profiles = PatchPipetteStateManager.listProfiles()
        if 'default' not in profiles:
            profiles.insert(0, 'default')
        for profile in profiles:
            self.ui.profileCombo.addItem(profile)

        common_opts = dict(stoppable=True, failure="FAILED!", showStatus=False)

        self.ui.homeBtn.setOpts(task_producer=self._moveHome, **common_opts)
        self.ui.nucleusHomeBtn.setOpts(task_producer=self._nucleusHome, raiseOnError=False, **common_opts)
        self.ui.coarseSearchBtn.setOpts(task_producer=self._coarseSearch, **common_opts)
        self.ui.fineSearchBtn.setOpts(task_producer=self._fineSearch, **common_opts)
        self.ui.aboveTargetBtn.setOpts(task_producer=self._aboveTarget, **common_opts)
        self.ui.autoFindTipBtn.setOpts(task_producer=self._autoFindTip, **common_opts)
        self.ui.cellDetectBtn.setOpts(task_producer=self._cellDetect, raiseOnError=False, **common_opts)
        self.ui.breakInBtn.setOpts(task_producer=self._breakIn, raiseOnError=False, **common_opts)
        self.ui.toTargetBtn.setOpts(task_producer=self._toTarget, **common_opts)
        self.ui.sealBtn.setOpts(task_producer=self._seal, raiseOnError=False, **common_opts)
        self.ui.reSealBtn.setOpts(task_producer=self._reSeal, raiseOnError=False, **common_opts)
        self.ui.reSealNoNuzzleBtn.setOpts(task_producer=self._reSealNoNuzzle, raiseOnError=False, **common_opts)
        self.ui.refillBtn.setOpts(task_producer=self._refill, raiseOnError=False, **common_opts)
        self.ui.approachBtn.setOpts(task_producer=self._approach, raiseOnError=False, **common_opts)
        self.ui.cleanBtn.setOpts(task_producer=self._clean, raiseOnError=False, **common_opts)
        self.ui.collectBtn.setOpts(task_producer=self._collect, raiseOnError=False, **common_opts)

        self.ui.profileCombo.currentIndexChanged.connect(self.profileComboChanged)
        self.ui.editProfileBtn.clicked.connect(self.openProfileEditor)
        self.ui.setTipBtn.toggled.connect(self.setTipToggled)
        self.ui.setTargetBtn.toggled.connect(self.setTargetToggled)

        self.ui.hideMarkersBtn.toggled.connect(self.hideBtnToggled)
        self.ui.recordTestPulsesBtn.toggled.connect(self.recordTestPulsesToggled)
        self.ui.recordBtn.toggled.connect(self.recordToggled)
        self.ui.recordTestPulsesBtn.setEnabled(self.ui.recordBtn.isChecked())
        self.ui.resetBtn.clicked.connect(self.resetHistory)

        self.ui.fastBtn.clicked.connect(self._turnOffSlowBtn)
        self.ui.slowBtn.clicked.connect(self._turnOffFastBtn)

        self._surface = None  # ControlSurface, or None if none is configured
        self._surfacePage = 0
        self._actionControls = {}  # Control -> name of a button on self.ui
        self._pipetteControls = {}  # Control -> (row, pipette index)
        self._pipetteGrid = None  # ndarray of Control, (row, pipette index)
        # how each control shows a two-LED state, settled once by _bindBacklight();
        # a control that can indicate nothing has no entry here
        self._backlights = {}  # Control -> callable(blue, red)
        surfaceConf = module.config.get('controlSurface')
        if surfaceConf is None and module.config.get('xkeysDevice') is not None:
            surfaceConf = {'device': module.config['xkeysDevice']}
        if surfaceConf is not None:
            self._setupControlSurface(surfaceConf)

        self.resetHistory()

        if self.microscope:
            d = self.microscope.getSurfaceDepth()
            if d is not None:
                self.surfaceDepthChanged(d)

        self.uiState = UiState(
            self, os.path.join('modules', f'{self.module.name}_ui.cfg'), widgets={'splitter': self.ui.splitter}
        )
        self.loadConfig()

    @property
    def _shouldSaveTipImages(self):
        # TODO this isn't safe outside of the UI thread
        return self.ui.saveTipImageBtn.isChecked()

    @_shouldSaveTipImages.setter
    def _shouldSaveTipImages(self, value):
        self.ui.saveTipImageBtn.setChecked(value)

    def _turnOffSlowBtn(self, checked):
        self.ui.slowBtn.setChecked(False)

    def _turnOffFastBtn(self, checked):
        self.ui.fastBtn.setChecked(False)

    def saveConfig(self):
        self.uiState.save()
        config = {
            'plotModes': self.pipCtrls[0].getPlotModes(),
            "plots": {
                (ctrl.pip.name(), plot.mode): plot.plot.saveState()
                for ctrl in self.pipCtrls for plot in ctrl.plots
            },
            "should save tip images": self._shouldSaveTipImages,
        }
        getManager().writeConfigFile(config, self._configFileName())

    def loadConfig(self):
        config = getManager().readConfigFile(self._configFileName())
        if 'plotModes' in config:
            self.setPlotModes(config['plotModes'])
        if "plots" in config:
            for pipette, plotname in config["plots"]:
                ctrl = next((ctrl for ctrl in self.pipCtrls if ctrl.pip.name() == pipette), None)
                if ctrl is not None:
                    plot = next((plot for plot in ctrl.plots if plot.mode == plotname), None)
                    if plot is not None:
                        plot.plot.restoreState(config["plots"][(pipette, plotname)])
        self._shouldSaveTipImages = config.get("should save tip images", True)

    def _configFileName(self):
        return os.path.join('modules', f'{self.module.name}.cfg')

    def profileComboChanged(self):
        profile = self.ui.profileCombo.currentText()
        for pip in self.pips:
            pip.stateManager().setProfile(profile)

    def openProfileEditor(self):
        if self._profileEditor is None or not self._profileEditor.isVisible():
            from .patchProfileEditor import ProfileEditor
            self._profileEditor = ProfileEditor()
            self._profileEditor.sigProfileChanged.connect(self.patchProfilesChanged)
            self._profileEditor.show()
        else:
            self._profileEditor.setTopLevelWindow()

    def patchProfilesChanged(self, profiles):
        self.recordEvent({
            "event_time": ptime.time(),
            "device": None,
            "event": "global patch profiles changed",
            "profile": json.dumps(profiles, cls=ACQ4JSONEncoder),
        })

    def setPlotModes(self, modes):
        for ctrl in self.pipCtrls:
            ctrl.setPlotModes(modes)
        self.saveConfig()

    def _setAllSelectedPipettesToState(self, state, **config):
        return MultiFuture([
            pip.setState(state, **config)
            for pip in self.selectedPipettes()
            if isinstance(pip, PatchPipette)
        ], name=f"Set pipettes state to {state}")

    def _moveHome(self):
        # This runs on the GUI thread, which carries no throughline of its own; the
        # frame is what tells the log that these moves came from a button press, and
        # each move's task nests under it.
        with throughline(name="Move pipettes home"):
            futures = []
            for pip in self.selectedPipettes():
                speed = self.selectedSpeed(default='fast')
                if isinstance(pip, PatchPipette):
                    pip.setState('out')
                    pip = pip.pipetteDevice
                futures.append(pip.goHome(speed))
            return MultiFuture(futures, name="Move pipettes home")

    def _nucleusHome(self):
        return self._setAllSelectedPipettesToState('home with nucleus')

    def _coarseSearch(self):
        return self.moveSearch(self.module.config.get('coarseSearchDistance', 400e-6))

    def _fineSearch(self):
        if len(self.selectedPipettes()) == 1:
            distance = 0
        else:
            distance = self.module.config.get('fineSearchDistance', 50e-6)
        return self.moveSearch(distance)

    def _aboveTarget(self):
        futures = []
        speed = self.selectedSpeed(default='fast')
        for pip in self.selectedPipettes():
            pip.setState('bath')
            futures.append(pip.pipetteDevice.goAboveTarget(speed))
        return MultiFuture(futures, name="Move pipettes above target")

    @asynch
    def _autoFindTip(self, max_reps=10):
        work_to_do = self.selectedPipettes()
        while work_to_do:
            patchpip = work_to_do.pop(0)
            pip = patchpip.pipetteDevice if isinstance(patchpip, PatchPipette) else patchpip
            pip.iterativelyFindTip(max_reps=max_reps)

    def _cellDetect(self):
        return self._setAllSelectedPipettesToState('cell detect')

    def _breakIn(self):
        return self._setAllSelectedPipettesToState('break in')

    def _toTarget(self):
        speed = self.selectedSpeed(default='fast')
        return MultiFuture([
            (
                pip.pipetteDevice if isinstance(pip, PatchPipette) else pip
            ).goTarget(speed)
            for pip in self.selectedPipettes()
        ], name="Move pipettes to target")

    def _seal(self):
        return self._setAllSelectedPipettesToState('seal')

    def _reSeal(self):
        return self._setAllSelectedPipettesToState('reseal')

    def _reSealNoNuzzle(self):
        return self._setAllSelectedPipettesToState('reseal', extractNucleus=False)

    def _refill(self):
        return self._setAllSelectedPipettesToState('refill')

    def _approach(self):
        with throughline(name="Move pipettes to approach"):
            futures = []
            for pip in self.selectedPipettes():
                if isinstance(pip, PatchPipette):
                    futures.append(pip.setState('approach'))
                else:
                    futures.append(pip.goApproach(self.selectedSpeed(default='fast')))
            return MultiFuture(futures, name="Move pipettes to approach")

    def _clean(self):
        return self._setAllSelectedPipettesToState('clean')

    def _collect(self):
        return self._setAllSelectedPipettesToState('collect')

    def selectedSpeed(self, default):
        if self.ui.fastBtn.isChecked():
            self.ui.fastBtn.setChecked(False)
            self.updateControlLights()
            return 'fast'
        if self.ui.slowBtn.isChecked():
            self.ui.slowBtn.setChecked(False)
            self.updateControlLights()
            return 'slow'
        return default

    def moveSearch(self, distance):
        with throughline(name="Move pipettes to search"):
            speed = self.selectedSpeed(default='fast')
            futures = []
            for pip in self.selectedPipettes():
                if isinstance(pip, PatchPipette):
                    pip.setState('bath')
                    pip = pip.pipetteDevice
                futures.append(pip.goSearch(speed, distance=distance))
            return MultiFuture(futures, name="Move pipettes to search")

    def setTipToggled(self, b):
        cammod = getManager().getModule('Camera')
        self._cammod = cammod
        pips = self.selectedPipettes()
        if b is True:
            self.ui.setTargetBtn.setChecked(False)
            if len(pips) == 0:
                self.ui.setTipBtn.setChecked(False)
                return
            # start manual tip setting of selected pipettes
            cammod.window().getView().scene().sigMouseClicked.connect(self.cameraModuleClicked_setTip)
            self._pipsToSetTips = pips
        else:
            # stop manual tip setting
            pg.disconnect(cammod.window().getView().scene().sigMouseClicked, self.cameraModuleClicked_setTip)
            self._pipsToSetTips = []

    def setTargetToggled(self, b):
        cammod = getManager().getModule('Camera')
        self._cammod = cammod
        pips = self.selectedPipettes()
        if b is True:
            self.ui.setTipBtn.setChecked(False)
            if len(pips) == 0:
                self.ui.setTargetBtn.setChecked(False)
                return
            cammod.window().getView().scene().sigMouseClicked.connect(self.cameraModuleClicked_setTarget)
            self._setTargetPips = pips
        else:
            pg.disconnect(cammod.window().getView().scene().sigMouseClicked, self.cameraModuleClicked_setTarget)
            self._setTargetPips = []

    def cameraModuleClicked_setTip(self, ev):
        if ev.button() != Qt.Qt.LeftButton:
            return

        # Set next pipette position from mouse click
        pip = self._pipsToSetTips.pop(0)
        if isinstance(pip, PatchPipette):
            pip = pip.pipetteDevice
        pos = self._cammod.window().getView().mapSceneToView(ev.scenePos())
        spos = pip.scopeDevice().globalPosition()
        pos = [pos.x(), pos.y(), spos[2]]
        tip_task = pip.setTipOffsetIfAcceptable(pos)
        tip_task.add_finish_callback(
            lambda result, exc: run_in_gui_thread(self._handleManualSetTip, result, exc, pip)
        )

    def _handleManualSetTip(self, success, exc, pip):
        if exc is not None:
            raise exc
        if not success:
            self._pipsToSetTips.insert(0, pip)
            return

        if self._shouldSaveTipImages:
            raise_errors(
                pip.saveManualTipPosition(
                    stack=self.module.config.get("useStacksForSavedTipImages", True)
                ),
                "Failed to save tip images: {error}",
            )

        if len(self._pipsToSetTips) == 0:
            self.ui.setTipBtn.setChecked(False)
            self.updateControlLights()

    def cameraModuleClicked_setTarget(self, ev):
        if ev.button() != Qt.Qt.LeftButton:
            return

        # Set next pipette position from mouse click
        pip = self._setTargetPips.pop(0)
        if isinstance(pip, PatchPipette):
            pip = pip.pipetteDevice
        pos = self._cammod.window().getView().mapSceneToView(ev.scenePos())
        spos = pip.scopeDevice().globalPosition()
        pos = [pos.x(), pos.y(), spos[2]]
        pip.setTarget(pos)

        if len(self._setTargetPips) == 0:
            self.ui.setTargetBtn.setChecked(False)
            self.updateControlLights()

    def hideBtnToggled(self, hide):
        for pip in self.pips:
            if isinstance(pip, PatchPipette):
                pip = pip.pipetteDevice
            pip.hideMarkers(hide)

    def pipetteTestPulseEnabled(self, clamp, enabled):
        self.updateSelectedPipControls()

    # def testPulseClicked(self):
    #     for pip in self.selectedPipettes():
    #         pip.clampDevice.enableTestPulse(self.ui.testPulseBtn.isChecked())

    def pipetteActiveChanged(self, active):
        self.selectionChanged()

    def pipetteSelectChanged(self, pipctrl, sel):
        if sel:
            # unselect all other pipettes
            for ctrl in self.pipCtrls:
                if ctrl is pipctrl:
                    continue
                ctrl.setSelected(False)

        self.selectionChanged()

    def pipetteLockChanged(self, state):
        self.selectionChanged()

    def selectionChanged(self):
        pips = self.selectedPipettes()
        solo = len(pips) == 1
        none = len(pips) == 0

        if none:
            self.ui.setTipBtn.setChecked(False)
            self.ui.setTargetBtn.setChecked(False)
            self.ui.selectedGroupBox.setTitle("Selected:")
            self.ui.selectedGroupBox.setEnabled(False)
        else:
            if solo:
                self.ui.selectedGroupBox.setTitle(f"Selected: {pips[0].name()}")
            elif len(pips) > 1:
                self.ui.selectedGroupBox.setTitle("Selected: multiple")
            self.ui.selectedGroupBox.setEnabled(True)
            self.updateSelectedPipControls()

        self.updateControlLights()

    def updateSelectedPipControls(self):
        pips = self.selectedPipettes()
        # tp = any([pip.testPulseEnabled() for pip in pips])
        # self.ui.testPulseBtn.setChecked(tp)

    def selectedPipettes(self) -> List[PatchPipette]:
        sel = []
        for ctrl in self.pipCtrls:
            if ctrl.selected():
                # solo mode
                if ctrl.locked():
                    return []
                return [ctrl.pip]
            if ctrl.active() and not ctrl.locked():
                sel.append(ctrl.pip)
        return sel

    # ----------------------------------------------------------------- control surface

    def _setupControlSurface(self, conf):
        """Claim this window's controls on the configured control surface.

        Two blocks are claimed: the fixed buttons named by *conf*'s ``actions`` (default
        :data:`DEFAULT_ACTION_KEYS`), and one column per pipette from
        :data:`PIPETTE_COLUMN_OFFSET` onwards, taken straight out of the surface's first
        control grid. A surface smaller than the layout, or a control another owner
        already holds, is logged and skipped rather than refusing to open the window.
        """
        surface = getManager().getDevice(conf['device'])
        if not isinstance(surface, ControlSurface):
            raise TypeError(
                f"MultiPatch controlSurface {conf['device']!r} is a {type(surface).__name__},"
                f" not a ControlSurface"
            )
        self._surface = surface
        self._surfacePage = int(conf.get('page', 0))

        for btnName, key in conf.get('actions', DEFAULT_ACTION_KEYS).items():
            control = self._claim('button', tuple(key))
            if control is not None:
                self._actionControls[control] = btnName
                control.sigPressed.connect(self._actionControlPressed)
                self._bindBacklight(control)

        grids = surface.controlGrids(page=self._surfacePage)
        if len(grids) == 0:
            logger.warning(
                f"Control surface {surface.name()} offers no control grid, so MultiPatch"
                f" has no per-pipette buttons"
            )
        else:
            grid = grids[0]
            rows = min(len(PIPETTE_ROW_ACTIONS), grid.shape[0])
            cols = min(len(self.pipCtrls), grid.shape[1] - PIPETTE_COLUMN_OFFSET)
            if cols < len(self.pipCtrls):
                logger.warning(
                    f"Control surface {surface.name()} has room for {max(cols, 0)} of"
                    f" {len(self.pipCtrls)} pipette columns"
                )
            block = grid[:rows, PIPETTE_COLUMN_OFFSET:PIPETTE_COLUMN_OFFSET + max(cols, 0)]
            for (row, col), control in np.ndenumerate(block):
                try:
                    control.acquire(self)
                except ControlInUse:
                    logger.warning(f"MultiPatch could not claim {control}", exc_info=True)
                    continue
                self._pipetteControls[control] = (row, col)
                control.sigPressed.connect(self._pipetteControlPressed)
                self._bindBacklight(control)
            self._pipetteGrid = block

        self.updateControlLights()

    def _claim(self, type, key):
        """Claim one control by address, returning None if it is unavailable."""
        try:
            return self._surface.acquireControl(type, self._surfacePage, key, owner=self)
        except (KeyError, ControlInUse):
            logger.warning(
                f"MultiPatch could not claim {type} {key!r} on page {self._surfacePage} of"
                f" {self._surface.name()}",
                exc_info=True,
            )
            return None

    def releaseControls(self):
        """Give every claimed control back, so that reopening this window can reclaim it."""
        for control in list(self._actionControls) + list(self._pipetteControls):
            control.release()
        self._actionControls = {}
        self._pipetteControls = {}
        self._backlights = {}
        self._pipetteGrid = None

    def _bindBacklight(self, control):
        """Work out once how *control* can show a two-LED ``(blue, red)`` state.

        Two independent indicators on one key, one of them able to flash, is an X-Keys
        idiosyncrasy and is spelled as one: ``XKeysControl.setBacklight`` is a contract
        between this window and that class, not something any generic control interface
        promises. A surface whose keys take a colour instead gets the pair collapsed onto
        one of :data:`BACKLIGHT_COLORS`, which loses flash but keeps the indicator -- and
        in colours an X-Keys key can also show, so it is the same indicator rather than a
        different-looking substitute. Having the method is not proof this control has the
        output -- one control class covers a surface's keys *and* its dials -- so each
        candidate is tried once, on the "off" state, and one that refuses is passed over.
        A control that can indicate nothing is said so here, once, rather than on every
        repaint of the bank.

        Parameters
        ----------
        control : Control
            The control, already claimed by this window.
        """
        candidates = []
        if hasattr(control, 'setBacklight'):
            candidates.append(control.setBacklight)
        if hasattr(control, 'setColor'):
            candidates.append(
                lambda blue, red: control.setColor(BACKLIGHT_COLORS[(bool(blue), bool(red))])
            )
        for writer in candidates:
            try:
                writer(0, 0)
            except UnsupportedControlFeature:
                continue  # the class offers it, this control does not
            self._backlights[control] = writer
            return
        logger.warning(
            f"MultiPatch cannot indicate state on {control}: it offers no output this"
            f" window knows how to drive. The button still works."
        )

    def _setBacklight(self, control, blue, red):
        """Show the ``(blue, red)`` state on *control*, each value 0, 1 or 2.

        A no-op on a control that indicated it could show nothing when it was bound; see
        :meth:`_bindBacklight`.
        """
        writer = self._backlights.get(control)
        if writer is not None:
            writer(blue, red)

    def updateControlLights(self):
        """Repaint every claimed control to match the window's state.

        One call repaints a whole bank, which is why the surface is expected to coalesce
        the writes; see :meth:`acq4.devices.XKeys.XKeys._flushBacklights`.
        """
        if self._surface is None:
            return
        sel = self.selectedPipettes()
        grid = self._pipetteGrid
        if grid is not None:
            for col in range(grid.shape[1]):
                ctrl = self.pipCtrls[col]
                pip = ctrl.pip
                states = [
                    (1 if ctrl.active() else 0, 2 if pip.pipetteDevice.moving else 0),
                    (1 if ctrl.locked() else 0, 1 if pip in sel else 0),
                    (1 if ctrl.selected() else 0, 1 if pip in sel else 0),
                ]
                for row, (blue, red) in enumerate(states[: grid.shape[0]]):
                    self._setBacklight(grid[row, col], blue, red)
        for control, btnName in self._actionControls.items():
            if btnName in CHECKABLE_ACTIONS:
                on = int(getattr(self.ui, btnName).isChecked())
                self._setBacklight(control, on, on)

    def _actionControlPressed(self, control):
        """Click the fixed button bound to *control*."""
        getattr(self.ui, self._actionControls[control]).click()
        self.updateControlLights()

    def _pipetteControlPressed(self, control):
        """Click one pipette's button, as addressed by *control*'s row and column."""
        row, col = self._pipetteControls[control]
        getattr(self.pipCtrls[col].ui, PIPETTE_ROW_ACTIONS[row]).click()

    def pipetteMoveStarted(self, pip):
        self.updateControlLights()

    def pipetteMoveFinished(self, pip):
        self.updateControlLights()

    def pipetteEvent(self, pip, ev):
        self._rememberEvent(ev)

    def surfaceDepthChanged(self, depth):
        event = OrderedDict([
            ("device", str(self.microscope.name())),
            ("event_time", ptime.time()),
            ("event", "surface_depth_changed"),
            ("surface_depth", depth),
        ])
        self._rememberEvent(event)

    def recordToggled(self, rec):
        if not rec:
            self.resetHistory()
        self.ui.recordTestPulsesBtn.setEnabled(rec)
        self._syncWriter()
        if rec:
            profile_data = PatchPipetteStateManager.buildPatchProfilesParameters().getValues()
            self.patchProfilesChanged(profile_data)

    def recordTestPulsesToggled(self, rec):
        self._syncWriter()

    def stopRecording(self, wait=True):
        """Stop the log writer, if one is running.

        `wait=False` leaves the writer thread to drain and close its files alone: the
        record button runs on the GUI thread, where waiting out a backlog of
        compressed sidecar writes would freeze the UI until it flushed. Shutdown
        still waits, because nothing else will be alive to finish the files.
        """
        if self._logWriter is not None:
            self._logWriter.stop(wait=wait)
            self._logWriter = None

    def _syncWriter(self):
        """Start, stop or adjust the log writer to match the two record buttons.

        The writer runs while "record" is on; a new one begins with a replay of
        eventHistory and covers every patch pipette and the microscope. "Record test
        pulses" is ignored while "record" is off; otherwise it saves full test pulses
        for the pipettes selected when it (or "record") was switched on.
        """
        if not self.ui.recordBtn.isChecked():
            self.stopRecording(wait=False)
            return
        fullTestPulsePipettes = self.selectedPipettes() if self.ui.recordTestPulsesBtn.isChecked() else []
        if self._logWriter is None:
            try:
                self._logWriter = MultiPatchLogWriter(
                    getManager().getCurrentDir(),
                    pipettes=[p for p in self.pips if isinstance(p, PatchPipette)],
                    microscope=self.microscope,
                    initial_records=list(self.eventHistory),
                    full_test_pulse_pipettes=fullTestPulsePipettes,
                ).start()
            except Exception:
                # Reached from the record button's toggled slot, which has nowhere to
                # put an exception; un-check it so the UI matches what is recording.
                logger.exception("Could not start event recording")
                self.ui.recordBtn.setChecked(False)
        else:
            self._logWriter.setFullTestPulsePipettes(fullTestPulsePipettes)

    def recordEvent(self, event):
        """Record one event this window originates (a patch-profile change).

        Pipette events and surface-depth changes go through _rememberEvent instead:
        the log writer subscribes to those itself.
        """
        if self._logWriter is not None:
            self._logWriter.record(event)
        self._rememberEvent(event)

    def _rememberEvent(self, event):
        """Keep an event, as a JSON-safe record, in the in-memory history (replayed
        into a newly started log)."""
        if not self.eventHistory:
            self.resetHistory()
        self.eventHistory.append(eventToRecord(event))

    def resetHistory(self):
        self.eventHistory = []
        for pip in self.selectedPipettes():
            if pip.clampDevice is not None:
                pip.clampDevice.resetTestPulseHistory()
        for ctrl in self.pipCtrls:
            ctrl.clearEventLog()
