
from .frame_display import FrameDisplay
from .imaging_template import Ui_Form


class ImagingCtrl(QtGui.QWidget):
    """Control widget used to interact with imaging devices. 

    Provides:

    * Acquire frame / video controls
    * Save frame, pin frame
    * Record stack
    * FPS display
    * Everything else provided by FrameDisplay class, including contrast and background
      subtraction
    """
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)

        # takes care of displaying image data, 
        # contrast & background subtraction user interfaces
        self.frameDisplay = FrameDisplay()

        self.ui = Ui_Form()
        self.ui.setupUi(selr)


