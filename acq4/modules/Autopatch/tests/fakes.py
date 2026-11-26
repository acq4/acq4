"""Shared stand-ins for the Manager and module an AutopatchWindow is built with."""
from types import SimpleNamespace

from acq4.Manager import getManager
from acq4.util import Qt


class FakePinnedFrameSource(Qt.QObject):
    """Stands in for the Camera module's ImagingCtrl: the pinned-frame list and
    the signal Area 1 mirrors it through.

    clearPinnedFrames() genuinely empties the list and emits, because the real
    one does (via removePinnedFrame) -- ReferenceImagery.beginSlice() calls it
    when the operator agrees to clear a previous slice's frames, and a fake
    that only recorded the call rather than emptying the list would hide a
    missing recompute in the code under test.
    """

    sigPinnedFramesChanged = Qt.Signal()

    def __init__(self):
        super().__init__()
        self.pinnedFrames = []

    def clearPinnedFrames(self):
        self.pinnedFrames = []
        self.sigPinnedFramesChanged.emit()

    def addPinnedFrame(self, item):
        """Stacks `item` above the last frame and emits, as ImagingCtrl.addPinnedFrame does."""
        item.setZValue(-10000 if not self.pinnedFrames else self.pinnedFrames[-1].zValue() + 1)
        self.pinnedFrames.append(item)
        self.sigPinnedFramesChanged.emit()


# The two folder types this window's paths ask create_data_dir for: "Slice" for
# newSlice(), and "Cell" for the directory a run makes per cell. A real Manager's
# config carries many more. "Cell" is named the way the real config names it
# (config/example/folderTypes.cfg) -- a fixed "cell", not a timestamp -- so two
# cells in one run have to be told apart by mkdir's autoIncrement, as they are on
# a rig.
FOLDER_TYPES = {
    "Slice": {"name": "Slice_%Y%m%d_%H%M%S", "experimentalUnit": False},
    "Cell": {"name": "cell", "experimentalUnit": False},
}


class FakeManager(Qt.QObject):
    """Stands in for Manager.

    `root_dir` is the DirHandle create_data_dir writes under; None for tests
    that never create a data directory. Offers a Camera module whose window
    records drawn items in `drawn` and has one interface backed by
    `pinnedFrameSource`. Config files are kept in the `configFiles` dict.
    """

    sigModulesChanged = Qt.Signal()

    def __init__(self, root_dir=None, config=None):
        super().__init__()
        self._current_dir = root_dir
        self.configFiles = {}
        # The rig's own configuration. `misc.minCellVolume`/`misc.detectionStepZ`
        # seed Area 2's detection controls with a starting point for a fresh
        # slice. Empty by default, so every other test sees the engine's own
        # defaults, the way an unconfigured rig would.
        self.config = config if config is not None else {}
        self.drawn = []
        self.pinnedFrameSource = FakePinnedFrameSource()
        self.cameraWindow = SimpleNamespace(
            getInterfaceForDevice=lambda name: SimpleNamespace(
                imagingCtrl=self.pinnedFrameSource
            ),
            interfaces={"cam": SimpleNamespace(imagingCtrl=self.pinnedFrameSource)},
            addItem=lambda item, **kwds: self.drawn.append(item),
            removeItem=self.drawn.remove,
        )

    def listModules(self):
        return ["Camera", "Data Manager"]

    def getModule(self, name):
        if name != "Camera":
            raise KeyError(name)
        return SimpleNamespace(window=lambda: self.cameraWindow)

    def getCurrentDir(self):
        return self._current_dir

    def setCurrentDir(self, d):
        self._current_dir = d

    def folderTypesConfig(self):
        return FOLDER_TYPES

    def readConfigFile(self, fileName, missingOk=True):
        if fileName not in self.configFiles and not missingOk:
            raise FileNotFoundError(fileName)
        return self.configFiles.get(fileName, {})

    def writeConfigFile(self, data, fileName):
        self.configFiles[fileName] = data


def fakeModule(name="Autopatch"):
    """A stand-in Autopatch module holding getManager() (the conftest FakeManager), `name` and quit()."""
    return SimpleNamespace(manager=getManager(), name=name, quit=lambda fromUi=False: None)


class FakePatchPipette(Qt.QObject):
    """Stands in for a PatchPipette: the sigStateChanged(self, newState, oldState)
    signal (states are plain names) and pipetteDevice.targetPosition().

    `setState` emits from the calling thread, as the real state manager does.
    """

    sigStateChanged = Qt.Signal(object, object, object)

    def __init__(self, target=(1e-3, 2e-3, -30e-6)):
        super().__init__()
        self.pipetteDevice = SimpleNamespace(targetPosition=lambda: self.target)
        self.target = target
        self.state = "bath"

    def setState(self, state):
        old, self.state = self.state, state
        self.sigStateChanged.emit(self, state, old)


class FakePipetteSelector(Qt.QWidget):
    """A pipette selector whose selection a test can change."""

    def __init__(self, pipette=None):
        super().__init__()
        self.pipette = pipette

    def getSelectedObj(self):
        return self.pipette
