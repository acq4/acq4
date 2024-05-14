import pyqtgraph as pg
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
    def loadFromFileHandle(cls, fh: FileHandle) -> "Frame | list[Frame]":
        data = fh.read()
        if fh.fileType() == "MetaArray":
            if data.ndim == 3:
                frames = []
                for row in data:
                    info = fh.info().deepcopy()
                    if data.axisName(0) == "Time":
                        info["time"] = row.axisValues(2)
                    elif data.axisName(0) == "Depth":
                        depth = row.axisValues(2)
                        xform = pg.SRTTransform3D(info["transform"])
                        pos = xform.getTranslation()
                        pos[2] = depth
                        xform.setTranslate(pos)
                        info["transform"] = xform
                    f = Frame(row.asarray(), info)
                    f.loadLinkedFiles(fh.parent())
                    frames.append(f)
                return frames
            else:
                data = data.asarray()
        frame = cls(data, fh.info().deepcopy())
        frame.loadLinkedFiles(fh.parent())
        return frame
