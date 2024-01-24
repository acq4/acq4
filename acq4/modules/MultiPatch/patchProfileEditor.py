from copy import deepcopy
import os
import pyqtgraph as pg
from pyqtgraph.parametertree import Parameter
import acq4.util.Qt as qt
from acq4.devices.PatchPipette.statemanager import PatchPipetteStateManager


class ProfileEditor(qt.QWidget):
    def __init__(self, parent=None):
        super().__init__()
        self.setWindowTitle('Patch Pipette Profile Editor')
        self.setWindowIcon(qt.QIcon(os.path.join(os.path.dirname(__file__), 'icon.png')))

        self.layout = qt.QGridLayout()
        self.setLayout(self.layout)
        self.ptree = pg.parametertree.ParameterTree()
        self.layout.addWidget(self.ptree, 0, 0)

        params = [ProfileParameter(profile) for profile in PatchPipetteStateManager.listProfiles()]
        self.param_root = Parameter.create(name='profiles', type='group', children=params)
        self.ptree.setParameters(self.param_root)
        self.param_root.sigTreeStateChanged.connect(self.paramTreeChanged)

    def paramTreeChanged(self, root_param, changes):
        for param, change, data in changes:
            (profile_name, state_name, *param_name) = self.param_root.childPath(param)
            # using deepcopy pretends that the profile is immutable, but it is not
            profile = deepcopy(PatchPipetteStateManager.getProfileConfig(profile_name))
            param_name = param_name[0]
            if state_name == "copyFrom":
                profile[state_name] = data
            else:
                profile.setdefault(state_name, {})
                profile[state_name].setdefault(param_name, data)
                if not param.valueModifiedSinceResetToDefault():
                    del profile[state_name][param_name]

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

    def setTopLevelWindow(self):
        self.raise_()
        self.activateWindow()


class ProfileParameter(pg.parametertree.Parameter):
    def __init__(self, profile):
        super().__init__(name=profile, type='group', children=[
            {'name': 'copyFrom', 'type': 'str', 'default': ''},
        ])
        config = PatchPipetteStateManager.getProfileConfig(profile)
        if 'copyFrom' in config:
            self['copyFrom'] = config['copyFrom']
        for state in PatchPipetteStateManager.listStates():
            self.addChild(StateParameter(state, profile))

    def reinitialize(self):
        for child in self:
            if isinstance(child, StateParameter):
                child.reinitialize()

    def applyDefaults(self, defaults):
        for key, val in defaults.items():
            self.child(key).applyDefaults(val)


class StateParameter(pg.parametertree.Parameter):
    def __init__(self, name, profile):
        super().__init__(name=name, type='group', children=[])
        self._profile = profile
        self._state = name
        profile_config = PatchPipetteStateManager.getProfileConfig(profile)
        if profile_config.get('copyFrom', None):
            defaults = PatchPipetteStateManager.getStateConfig(name, profile_config['copyFrom'])
        else:
            defaults = {}
        stateClass = PatchPipetteStateManager.getStateClass(name)
        config = PatchPipetteStateManager.getStateConfig(name, profile)
        for param_config in stateClass.parameterTreeConfig():
            if param_config['name'] in defaults:
                param_config['default'] = defaults[param_config['name']]
            param_config['pinValueToDefault'] = True
            param = pg.parametertree.Parameter.create(**param_config)
            if config.get(param.name()) is not None:
                param.setValue(config[param.name()])
            self.addChild(param)

    def reinitialize(self):
        profile = self._profile
        name = self._state
        profile_config = PatchPipetteStateManager.getProfileConfig(profile)
        if profile_config.get('copyFrom', None):
            defaults = PatchPipetteStateManager.getStateConfig(name, profile_config['copyFrom'])
        else:
            defaults = PatchPipetteStateManager.getStateConfig(name, None)
        self.applyDefaults(defaults)

    def applyDefaults(self, defaults):
        for key, val in defaults.items():
            self.child(key).setDefault(val, updatePristineValues=True)
