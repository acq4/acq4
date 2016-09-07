from .igorpro import IgorThread


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
        self.igor = IgorThread()
        self.windowName = 'ITC1600_Dev_0'

    def selectHeadstage(self, hs):
        return self.setCtrl("slider_DataAcq_ActiveHeadstage", hs)

    def setManualPressure(self, pressure):
        return self.setCtrl("setvar_DataAcq_SSPressure", pressure)

    def clickApproach(self):
        return self.setCtrl("button_DataAcq_Approach")

    def clickSeal(self):
        return self.setCtrl("button_DataAcq_Seal")

    def setHeadstageActive(self, hs, active):
        return self.setCtrl('Check_DataAcqHS_%02d' % hs, active)

    def autoPipetteOffset(self):
        return self.setCtrl('button_DataAcq_AutoPipOffset_VC')

    def setCtrl(self, name, value=None):
        """Set or activate a GUI control in MIES.
        """
        windowName = '"{}"'.format(self.windowName)
        name_arg = '"{}"'.format(name)
        if value is None:
            return self.igor('PGC_SetAndActivateControl', windowName, name_arg)
        elif isinstance(value, int):
            val = 'val={:d}'.format(value)
            return self.igor('PGC_SetAndActivateControl', windowName, name_arg, val)
        elif isinstance(value, float):
            val = 'val={:f}'.format(value)
            return self.igor('PGC_SetAndActivateControl', windowName, name_arg, val)
        else:
            raise TypeError("Invalid value %s" % value)

    

