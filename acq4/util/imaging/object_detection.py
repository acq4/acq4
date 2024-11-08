from __future__ import annotations

from threading import RLock
from typing import Optional

import click
import numpy as np
import scipy.stats
import tifffile
from MetaArray import MetaArray
from PIL import Image

from acq4.util.future import Future, future_wrap
from acq4.util.imaging import Frame
import pyqtgraph as pg
from pyqtgraph import SRTTransform3D
from teleprox import ProcessSpawner
from teleprox.shmem import SharedNDArray

_lock = RLock()
_remote_process: Optional[ProcessSpawner] = None
_shared_array: Optional[SharedNDArray] = None
_yolo: "Optional[YOLO]" = None


def _get_yolo() -> "YOLO":
    from yolo import YOLO  # todo put this someplace
    global _yolo
    if _yolo is None:
        _yolo = YOLO()
    return _yolo


def normalize(image: Image, min_in=None, max_in=None):
    # TODO reimplement it with no-copy, maybe?
    if min_in is None:
        # min_in = scipy.stats.scoreatpercentile(image, 5)
        min_in = np.min(image)
        # min_in = 0
    if max_in is None:
        # max_in = scipy.stats.scoreatpercentile(image, 90)
        max_in = np.max(image)
        # max_in = 65535
    min_out = 0
    max_out = 255  # maxmimum intensity (output)
    image = (image - np.uint16(min_in)) * (
            ((max_out - min_out) / (max_in - min_in)) + min_out
    )
    # image = (image - np.uint16(min_in)) * (
    #     (max_out / (max_in - min_in))
    # )
    image = scipy.ndimage.zoom(image, 3)
    offset_w = int(image.shape[0] * 0.3)
    offset_h = int(image.shape[1] * 0.3)
    margin_w = int(image.shape[0] * 0.4)
    margin_h = int(image.shape[1] * 0.4)
    image = image[offset_w:offset_w + margin_w, offset_h:offset_h + margin_h]
    return Image.fromarray(image.astype(np.uint8))


def _get_shared_array(data: np.ndarray) -> SharedNDArray:
    global _shared_array
    # TODO what if someone else is using it?!
    if _shared_array is not None and _shared_array.data.shape != data.shape:
        # it might still be in use, so just let the normal shared memory cleanup do unlink
        _shared_array.shmem.close()
        _shared_array = None
    if _shared_array is None:
        _shared_array = SharedNDArray.copy(data)
    else:
        _shared_array.data[:] = data
    return _shared_array


def _get_remote_process():
    global _remote_process
    # TODO what if someone else is using it?!
    # TODO how does cleanup happen?
    if _remote_process is None:
        # no local server forces no proxies, only serialization and shared mem
        _remote_process = ProcessSpawner(name="ACQ4 Object Detection", start_local_server=False, qt=True)
    return _remote_process


@future_wrap
def detect_pipette_tip(frame: Frame, angle: float, _future: Future) -> tuple[float, float, float]:
    shared_array = _get_shared_array(frame.data())
    with _lock:
        rmt_process = _get_remote_process()
        rmt_array = rmt_process.client.transfer(shared_array)
        rmt_this = rmt_process.client._import("acq4.util.imaging.object_detection")
        _future.checkStop()
        return rmt_this.do_pipette_tip_detection(rmt_array.data, angle, _timeout=60)



_pipette_detection_model = None
def get_pipette_detection_model():
    global _pipette_detection_model
    if _pipette_detection_model is None:
        import torch, os
        import acq4.util.pipette_detection.torch_model_04
        from acq4.util.pipette_detection.torch_model_04 import PipetteDetector

        # initialize model
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = PipetteDetector()
        model.to(device)

        # load model weights
        detector_path = os.path.dirname(acq4.util.pipette_detection.torch_model_04.__file__)
        model_file = os.path.join(detector_path, 'torch_models', '04_more_increased_difficulty.pth')
        model.load_state_dict(torch.load(model_file))

        _pipette_detection_model = model
    return _pipette_detection_model


def do_pipette_tip_detection(data: np.ndarray, angle: float):
    """
    Parameters
    ----------
    data : image data shaped like [cols, rows]
    angle : angle of pipette in degrees, measured wittershins relative to pointing directly rightward
    """
    import os
    import torch
    from acq4.util.pipette_detection.torch_model_04 import make_image_tensor, pos_normalizer
    from acq4.util.pipette_detection.test_data import make_rotated_crop

    model = get_pipette_detection_model()

    # rotate and crop image
    margin = (np.array(data.shape) - 400) // 2
    crop = (slice(margin[0], margin[0]+400), slice(margin[1], margin[1]+400))
    rot, tr = make_rotated_crop(data, -angle, crop)
    # convert to 0-255 rgb
    img = (rot - rot.min()) / (rot.max() - rot.min()) * 255
    img = np.stack([img] * 3, axis=-1)[np.newaxis, ...]

    # make prediction
    image_tensor = make_image_tensor(img)
    model.eval()  # set model to inference mode
    with torch.no_grad():
        pred = model(image_tensor).cpu().numpy()
    z, y, x, snr = pos_normalizer.denormalize(pred)[0]

    # unrotate/uncrop prediction
    pos_xy = tr.imap([y, x])

    return pos_xy, z, snr, locals()


@future_wrap
def detect_neurons(frames: Frame | list[Frame], model: str = "cellpose", _future: Future = None) -> list:
    if do_3d := not isinstance(frames, Frame):
        data = np.stack([frame.data() for frame in frames])
        transform = frames[0].globalTransform()
    else:
        data = frames.data()[np.newaxis, ...]
        transform = frames.globalTransform()
    shared_array = _get_shared_array(data)
    _future.checkStop()
    with _lock:
        rmt_process = _get_remote_process()
        rmt_array = rmt_process.client.transfer(shared_array)
        rmt_this = rmt_process.client._import("acq4.util.imaging.object_detection")
        _future.checkStop()
        return rmt_this.do_neuron_detection(rmt_array.data, transform, model, do_3d, _timeout=60)


def do_neuron_detection(data: np.ndarray, transform: SRTTransform3D, model: str = "cellpose", do_3d: bool = False) -> list:
    if model == 'cellpose':
        return _do_neuron_detection_cellpose(data, transform, do_3d)
    elif model == 'yolo':
        return _do_neuron_detection_yolo(data, transform)
    else:
        raise ValueError(f"Unknown model {model}")


def _do_neuron_detection_yolo(data: np.ndarray, transform: SRTTransform3D) -> list:
    image = Image.fromarray(data)
    image = normalize(image)
    my_yolo = _get_yolo()
    boxes = list(my_yolo.get_boxes(image).keys())

    # for _ in range(3):
    #     start_x = np.random.randint(0, 236)
    #     start_y = np.random.randint(0, 236)
    #     boxes.append((
    #         start_x,
    #         start_y,
    #         start_x + np.random.randint(12, 22),
    #         start_y + np.random.randint(12, 22)))

    def xyxy_to_rect(box: tuple):
        start_x, start_y, end_x, end_y = box
        start = transform.map((start_x, start_y))
        end = transform.map((end_x, end_y))
        return start, end
    return [xyxy_to_rect(box) for box in boxes]  # TODO filter by class? score?


def _do_neuron_detection_cellpose(data: np.ndarray, transform: SRTTransform3D, do_3d: bool = False) -> list:
    from cellpose import models

    model = models.Cellpose(gpu=True, model_type="cyto3")
    data = data[:, np.newaxis, :, 0:-2]  # add channel dimension, weird the shape
    masks_pred, flows, styles, diams = model.eval(
        [data],
        diameter=35,
        # niter=2000,
        channel_axis=1,
        z_axis=0 if do_3d else None,
        stitch_threshold=0.25 if do_3d else 0,
    )
    mask = masks_pred[0]  # each distinct cell gets an id: 1, 2, ...

    def bbox(num) -> tuple[tuple[float, ...], tuple[float, ...]]:
        match = mask == num
        coords = np.array(np.where(match)).T
        start = coords.min(axis=0)
        end = coords.max(axis=0)
        return transform.map(tuple(start[::-1])), transform.map(tuple(end[::-1]))

    cell_num = 1
    boxes = []
    while np.any(mask == cell_num):
        boxes.append(bbox(cell_num))
        cell_num += 1
    return boxes


@click.command()
@click.argument("image", required=True)
@click.option("--model", default="cellpose", show_default=True, type=click.Choice(["cellpose", "yolo", "pipette"]))
@click.option("--angle", default=0, show_default=True, type=float)
@click.option("--z", default=0, show_default=True, type=int)
@click.option("--display", is_flag=True, type=bool)
def cli(image, model, angle, z, display):
    null_xform = SRTTransform3D()
    if image[-3:] == ".ma":
        image = MetaArray(file=image)
        data = image.asarray()
    elif image[-5:] == ".tiff":
        data = tifffile.imread(image)
    else:
        image = Image.open(image)
        data = np.array(image)
    print(f"image shape: {data.shape}")
    if model == "pipette":
        # fill in 3 channels
        data = np.stack([data[z], data[z], data[z]], axis=-1)
        print(f"image reshaped to be: {data.shape}")
        _x, _y, _z = do_pipette_tip_detection(data[np.newaxis, ...], angle * np.pi / 180)
        print(f"Detected pipette tip at {_x}, {_y}, {_z}")
        # wait for user input
        input("Press Enter to continue...")
    else:
        do_3d = data.ndim == 4 or (data.ndim == 3 and data.shape[-1] > 3)
        neurons = do_neuron_detection(data, null_xform, model, do_3d)
        print(f"Detected {len(neurons)} neuron(s)")
        print(neurons)
        if display:
            pg.mkQApp()
            pg.image(data[0][:])
            for neuron in neurons:
                start, end = neuron
                pg.plot([start[0], end[0]], [start[1], end[1]], pen="r")
            pg.exec_()


if __name__ == '__main__':
    cli()
