from .igorpro import IgorBridge


def __reload__(old):
    MIESBridge._bridge = old['MIESBridge']._bridge


class MIESBridge(object):
    """Bridge for communicating with MIES (multi-patch ephys and pressure control in IgorPro)
    """
    _bridge = None

    @classmethod
    def getBridge(cls):
        """Return a singleton MIESBridge instance.
        """
        if cls._bridge is None:
            cls._bridge = MIESBridge()
        return cls._bridge

    def __init__(self):
        self.igor = IgorBridge()
        self.windowName = 'ITC1600_Dev_0'

    def selectHeadstage(self, hs):
        self.setCtrl("slider_DataAcq_ActiveHeadstage", hs)

    def setManualPressure(self, pressure):
        self.setCtrl("setvar_DataAcq_SSPressure", pressure)

    def clickApproach(self):
        self.setCtrl("button_DataAcq_Approach")

    def clickSeal(self):
        self.setCtrl("button_DataAcq_Seal")

    def setHeadstageActive(self, hs, active):
        self.setCtrl('Check_DataAcqHS_%02d' % hs, active)

    def autoPipetteOffset(self):
        self.setCtrl('button_DataAcq_AutoPipOffset_VC')

    def setCtrl(self, name, value=None):
        """Set or activate a GUI control in MIES.
        """
        if value is None:
            self.igor('PGC_SetAndActivateControl("%s", "%s")' % (self.windowName, name))
        elif isinstance(value, int):
            self.igor('PGC_SetAndActivateControl("%s", "%s", val=%d)' % (self.windowName, name, value))
        elif isinstance(value, float):
            self.igor('PGC_SetAndActivateControl("%s", "%s", val=%f)' % (self.windowName, name, value))
        else:
            raise TypeError("Invalid value %s" % value)

    

