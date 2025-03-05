import json
from copy import deepcopy
import os
import pyqtgraph as pg
from acq4.util.debug import logMsg
from acq4.util.json_encoder import ACQ4JSONEncoder
from pyqtgraph.parametertree import Parameter
import acq4.util.Qt as qt
from acq4.devices.PatchPipette.statemanager import PatchPipetteStateManager


class ProfileEditor(qt.QWidget):
    sigProfileChanged = qt.pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__()
        self.setWindowTitle('Patch Pipette Profile Editor')
        self.setWindowIcon(qt.QIcon(os.path.join(os.path.dirname(__file__), 'icon.png')))

        self.layout = qt.QGridLayout()
        self.setLayout(self.layout)
        self.ptree = pg.parametertree.ParameterTree()
        self.layout.addWidget(self.ptree, 0, 0)

        self.param_root = PatchPipetteStateManager.buildPatchProfilesParameters()
        self.ptree.setParameters(self.param_root)
        self.param_root.sigTreeStateChanged.connect(self.paramTreeChanged)

    def paramTreeChanged(self, root_param, changes):
        loggable = {}
        for param, change, data in changes:
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

            PatchPipetteStateManager.addProfile(profile_name, profile, overwrite=True)

            # update display of dependent parameters
            if state_name == "copyFrom":
                for profile_item in self.param_root:
                    profile_item.reinitialize()
            else:
                for profile_item in self.param_root:
                    if profile_item.name() == profile_name:
                        continue
                    if PatchPipetteStateManager.getProfileConfig(profile_item.name()).get("copyFrom", None) == profile_name:
                        profile_item.applyDefaults({state_name: {param_name: data}})
        logMsg(f"Patch profile {profile_name} updated: {json.dumps(loggable, cls=ACQ4JSONEncoder)}")
        self.sigProfileChanged.emit(loggable)

    def setTopLevelWindow(self):
        self.raise_()
        self.activateWindow()
