import os
import pyqtgraph as pg
import acq4.util.Qt as qt
from acq4.devices.PatchPipette.statemanager import PatchPipetteStateManager

"""
Todo:
- Parametertree showing all profiles
- Each profile contains a list of states
- Each state contains a list of parameters
- Each parameter is either a custom value or an indication of using the default value

"""


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
            # childs = []
            # params.append({'name': profile, 'type': 'group', 'children': childs})
            # profileConfig = StateManager.getProfileConfig(profile)
            # for key, val in in profileConfig.items():
            #     if key == 'copyFrom':
            #         childs.append({'name': 'copyFrom', 'type': 'str', 'value': profileConfig['copyFrom']})
            #     else:
            #         childs.append({'name': key, 'type': 'str', 'value': val})



class ProfileParameter(pg.parametertree.Parameter):
    def __init__(self, profile):

        
        super().__init__(name=profile, type='group', children=[
            {'name': 'copyFrom', 'type': 'str', 'value': ''},
        ])
        config = PatchPipetteStateManager.getProfileConfig(profile)
        for key, val in config.items():
            if key == 'copyFrom':
                self['copyFrom'] = config['copyFrom']
            else:
                self.addChild(StateParameter(key, val))


class StateParameter(pg.parametertree.Parameter):
    def __init__(self, name, config):
        super().__init__(name=name, type='group', children=[])
        stateClass = PatchPipetteStateManager.getStateClass(name)
        for param_config in stateClass.parameterTreeConfig():
            self.addChild(pg.parametertree.Parameter(**param_config))

