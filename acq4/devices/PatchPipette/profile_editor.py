import pyqtgraph as pg
import acq4.util.Qt as qt
from .statemanager import StateManager

"""
Todo:
- Parametertree showing all profiles
- Each profile contains a list of states
- Each state contains a list of parameters
- Each parameter is either a custom value or an indication of using the default value

"""


class ProfileEditor(qt.QWidget):
    def __init__(self, parent=None):
        #initialize a parametertree widget to show the profiles
        super().__init__(parent)
        
        # use StateManager.listProfiles() to get a list of profiles
        # use StateManager.getProfile(profileName) to get a profile
    
        self.layout = qt.QGridLayout()
        self.setLayout(self.layout)
        self.ptree = pg.parametertree.ParameterTree()
        self.layout.addWidget(self.ptree, 0, 0)

        params = []
        for profile in StateManager.listProfiles():
            params.append(ProfileParameter(profile))
            # childs = []
            # params.append({'name': profile, 'type': 'group', 'children': childs})
            # profileConfig = StateManager.getProfileConfig(profile)
            # for key, val in in profileConfig.items():
            #     if key == 'copyFrom':
            #         childs.append({'name': 'copyFrom', 'type': 'str', 'value': profileConfig['copyFrom']})
            #     else:
            #         childs.append({'name': key, 'type': 'str', 'value': val})



class ProfileParameter(pg.Parameter):
    def __init__(self, profile):

        
        super().__init__(name=profile, type='group', children=[
            {'name': 'copyFrom', 'type': 'str', 'value': ''},
        ])
        config = StateManager.getProfileConfig(profile)
        for key, val in config.items():
            if key == 'copyFrom':
                self['copyFrom'] = config['copyFrom']
            else:
                self.addChild(StateParameter(key, val))


class StateParameter(pg.Parameter):
    def __init__(self, name, config):
        super().__init__(name=name, type='group', children=[])
        stateClass = StateManager.getStateClass(name)
        stateDefaults = stateClass.defaultConfig()
        for paramName, value in stateDefaults:
            

        for key, val in config.items():  # TODO this only covers the explicitly overridden params
            self.addChild({'name': key, 'type': 'str', 'value': val})
