from acq4.util import imaging
from acq4.util.DataManager import FileHandle


class Frame(imaging.Frame):
    def __init__(self, data, info):
        from acq4.devices.Camera import Camera

        # make frame transform to map from image coordinates to sensor coordinates.
        # (these may differ due to binning and region of interest settings)
        tr = Camera.makeFrameTransform(info["region"], info["binning"])
        info["frameTransform"] = tr

        super().__init__(data, info)

    @classmethod
    def loadFromFileHandle(cls, fh: FileHandle):
        frame = cls(fh.read(), fh.info().deepcopy())
        frame.loadLinkedFiles(fh.parent())
        return frame
