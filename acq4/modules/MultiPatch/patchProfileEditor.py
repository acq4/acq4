from copy import deepcopy
import os
import pyqtgraph as pg
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

        params = []
        for profile in PatchPipetteStateManager.listProfiles():
            params.append(ProfileParameter(profile))
        self.param_root = pg.parametertree.Parameter.create(name='profiles', type='group', children=params)
        self.ptree.setParameters(self.param_root)
        self.param_root.sigTreeStateChanged.connect(self.paramTreeChanged)

    def paramTreeChanged(self, root_param, changes):
        for param, change, data in changes:
            (profile_name, state_name, *param_name) = self.param_root.childPath(param)
            # using deepcopy pretends that the profile is immutable, but it is not
            profile = deepcopy(PatchPipetteStateManager.getProfileConfig(profile_name))
            if state_name == "copyFrom":
                profile[state_name] = data
            else:
                profile.setdefault(state_name, {})
                if profile.get("copyFrom", None):
                    default = PatchPipetteStateManager.getStateConfig(state_name, profile["copyFrom"]).get(param_name[0], None)
                else:
                    default = param.defaultValue()
                if data == default:
                    if param_name[0] in profile[state_name]:
                        del profile[state_name][param_name[0]]
                else:
                    profile[state_name][param_name[0]] = data
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
                        profile_item.applyDefaults({state_name: {param_name[0]: data}})

    def setTopLevelWindow(self):
        self.raise_()
        self.activateWindow()


class ProfileParameter(pg.parametertree.Parameter):
    def __init__(self, profile):
        super().__init__(name=profile, type='group', children=[
            {'name': 'copyFrom', 'type': 'str', 'value': ''},
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
        for state in self:
            if state.name() in defaults:
                state.applyDefaults(defaults[state.name()])


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
            param = pg.parametertree.Parameter(**param_config)
            param.setValue(config.get(param.name(), param.defaultValue()))
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
        for param in self:
            if param.name() in defaults:
                if param.valueIsDefault():
                    param.setValue(defaults[param.name()])
                param.setDefault(defaults[param.name()])