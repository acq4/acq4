import json
import os
from copy import deepcopy

import acq4.util.Qt as qt
import pyqtgraph as pg
from acq4.devices.PatchPipette.statemanager import PatchPipetteStateManager
from acq4.logging_config import get_logger
from acq4.util.json_encoder import ACQ4JSONEncoder
from pyqtgraph.parametertree import Parameter

logger = get_logger(__name__)


class ProfileEditor(qt.QWidget):
    sigProfileChanged = qt.pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Patch Pipette Profile Editor')
        self.setWindowIcon(qt.QIcon(os.path.join(os.path.dirname(__file__), 'icon.png')))

        self.layout = qt.QGridLayout()
        self.setLayout(self.layout)
        self.ptree = pg.parametertree.ParameterTree()
        self.layout.addWidget(self.ptree, 0, 0)

        self.param_root = PatchPipetteStateManager.buildPatchProfilesParameters()
        self.ptree.setParameters(self.param_root)
        self.param_root.sigTreeStateChanged.connect(self.paramTreeChanged)
        # True while a change is crossing between the tree and the profile store,
        # in either direction, so that neither side echoes the other back.
        self._syncing = False
        PatchPipetteStateManager.profileNotifier().sigProfileConfigChanged.connect(
            self.profileConfigChanged)

    def profileConfigChanged(self, profile_name, config):
        """Re-apply a profile changed outside this editor -- by a protocol action,
        say -- to the tree, so an open editor shows what the rigs are actually
        patching with.

        A profile the tree does not have is ignored: the tree is built once, at
        construction, and this editor has never been able to grow a profile.
        """
        if self._syncing:
            return
        item = next((c for c in self.param_root if c.name() == profile_name), None)
        if item is None:
            logger.debug(f"Patch profile {profile_name} changed; not shown in this editor")
            return
        self._syncing = True
        try:
            item.syncFromConfig(config)
            for profile_item in self.param_root:
                if profile_item is item:
                    continue
                this_profile = PatchPipetteStateManager.getProfileConfig(profile_item.name())
                if this_profile.get("copyFrom", None) == profile_name:
                    profile_item.reinitialize()
        finally:
            self._syncing = False

    def paramTreeChanged(self, root_param, changes):
        for param, change, data in changes:
            loggable = {}
            (profile_name, state_name, *param_name) = self.param_root.childPath(param)
            # using deepcopy pretends that the profile is immutable, but it is not
            profile = deepcopy(PatchPipetteStateManager.getProfileConfig(profile_name))
            if state_name == "copyFrom":
                profile[state_name] = data
                loggable.setdefault(profile_name, {})[state_name] = data
            else:
                param_name = param_name[0]
                profile.setdefault(state_name, {})
                profile[state_name][param_name] = data
                if not param.valueModifiedSinceResetToDefault():
                    del profile[state_name][param_name]
                loggable.setdefault(profile_name, {}).setdefault(state_name, {})[param_name] = data

            # Guarded: the store notifies on every write, and the tree updates it
            # makes below are this editor's own business. Every write this editor
            # performs -- including the ones the dependent-parameter updates below
            # provoke by re-entering this handler -- passes through here, so
            # profileConfigChanged only ever sees a change from somewhere else.
            self._syncing = True
            try:
                PatchPipetteStateManager.addProfile(profile_name, profile, overwrite=True)
            finally:
                self._syncing = False

            # update display of dependent parameters
            if state_name == "copyFrom":
                for profile_item in self.param_root:
                    profile_item.reinitialize()
            else:
                for profile_item in self.param_root:
                    if profile_item.name() == profile_name:
                        continue
                    this_profile = PatchPipetteStateManager.getProfileConfig(profile_item.name())
                    copy_from = this_profile.get("copyFrom", None)
                    if copy_from == profile_name:
                        profile_item.applyDefaults({state_name: {param_name: data}})
            logger.debug(f"Patch profile {profile_name} updated: {json.dumps(loggable, cls=ACQ4JSONEncoder)}")
            self.sigProfileChanged.emit(loggable)

    def setTopLevelWindow(self):
        self.raise_()
        self.activateWindow()
