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
import coorx.image


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

        # Model 04
        # import acq4.util.pipette_detection.torch_model_04
        # from acq4.util.pipette_detection.torch_model_04 import PipetteDetector
        # detector_path = os.path.dirname(acq4.util.pipette_detection.torch_model_04.__file__)
        # model_file = os.path.join(detector_path, 'torch_models', '04_more_increased_difficulty.pth')

        # Model 05
        # import acq4.util.pipette_detection.torch_model_05
        # from acq4.util.pipette_detection.torch_model_05 import PipetteDetector
        # detector_path = os.path.dirname(acq4.util.pipette_detection.torch_model_05.__file__)
        # model_file = os.path.join(detector_path, 'torch_models', '05_deeper_training.pth')

        # Model 06
        # import acq4.util.pipette_detection.torch_model_06
        # from acq4.util.pipette_detection.torch_model_06 import PipetteDetector
        # detector_path = os.path.dirname(acq4.util.pipette_detection.torch_model_06.__file__)
        # model_file = os.path.join(detector_path, 'torch_models', '06_resnet50.pth')

        # Model 08
        import acq4.util.pipette_detection.torch_model_08
        from acq4.util.pipette_detection.torch_model_08 import PipetteDetector
        detector_path = os.path.dirname(acq4.util.pipette_detection.torch_model_08.__file__)
        model_file = os.path.join(detector_path, 'torch_models', '08_aux_error_disabled.pth')

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = PipetteDetector()
        model.to(device)
        model.load_state_dict(torch.load(model_file))

        _pipette_detection_model = model
    return _pipette_detection_model


analysis_window = None


def do_pipette_tip_detection(data: np.ndarray, angle: float, show=True):
    """
    Parameters
    ----------
    data : image data shaped like [cols, rows]
    angle : angle of pipette in degrees, measured wittershins relative to pointing directly rightward

    Returns
    -------
    pos_rc : tuple
        (row, col) position of detected pipette
    z_um : float
        z position of pipette relative to focal plane in um
    err : float
        Indicator of confidence (model-specific)
    """
    import os
    import torch
    from acq4.util.pipette_detection.torch_model_08 import make_position_normalizer

    global analysis_window

    pos_normalizer = make_position_normalizer(image_size=400)
    model = get_pipette_detection_model()

    image = coorx.image.Image(data, axes=(0, 1))

    # rotate and crop image
    # rot, tr = make_rotated_crop(data, -angle, crop=None)
    rotated = image.rotate(-angle, reshape=False)
    scaled = rotated.zoom(400 / rotated.shape[0])

    scaled_pos_rc, z_um1, err1 = detect_pipette_once(model, scaled.image, pos_normalizer)

    # position expressed in pixels relative to the rotated/zoomed image
    # this must be mapped back to the original
    rotated_pos_rc = scaled.point(scaled_pos_rc).mapped_to(rotated.cs)

    # crop a 400x400 region around the detected position
    row_start = int(np.clip(rotated_pos_rc[0] - 200, 0, image.shape[0] - 400))
    col_start = int(np.clip(rotated_pos_rc[1] - 200, 0, image.shape[1] - 400))
    cropped = rotated[row_start:row_start+400, col_start:col_start+400]
    # print("detected position:", pos_rc2)
    # print("image shape:", image.shape)
    # print("cropping at", row_start, col_start)
    # print("cropped shape:", cropped.shape)

    # detect again
    cropped_pos_rc, z_um3, err3 = detect_pipette_once(model, cropped.image, pos_normalizer)
    image_pos_rc = cropped.point(cropped_pos_rc).mapped_to(image.cs)

    if show:
        if analysis_window is None:
            w = pg.QtWidgets.QWidget()
            l = pg.QtWidgets.QGridLayout()
            w.setLayout(l)
            w.views = []
            for i in range(3):
                imv = pg.ImageView()
                imv.target = pg.TargetItem()
                imv.view.addItem(imv.target)
                w.views.append(imv)
                l.addWidget(imv, 0, i)
            analysis_window = w
            w.resize(900, 300)

        views = analysis_window.views
        views[0].setImage(scaled.image.T)
        views[0].target.setPos(*scaled_pos_rc[::-1])
        views[1].setImage(cropped.image.T)
        views[1].target.setPos(*cropped_pos_rc[::-1])
        views[0].setImage(image.image.T)
        views[0].target.setPos(*image_pos_rc[::-1])

        analysis_window.show()

    return image_pos_rc, z_um3, err3, locals()


def detect_pipette_once(model, data, pos_normalizer):
    import torch
    from acq4.util.pipette_detection.torch_model_08 import make_image_tensor
    from acq4.util.pipette_detection.training_data import normalize_image

    # make into RGB batch (1, rows, cols, 3)
    img = np.repeat(data[np.newaxis, ..., np.newaxis], 3, axis=-1)

    # normalize image
    normalized = normalize_image(img)

    # make prediction
    image_tensor = make_image_tensor(normalized)
    model.eval()  # set model to inference mode
    with torch.no_grad():
        pred_pos, pred_err = model(image_tensor)
        pred_pos = pred_pos[0].cpu().numpy()
        pred_err = pred_err[0].cpu().numpy()

    denorm_pos = pos_normalizer.denormalize(pred_pos)
    denorm_err_pos = pos_normalizer.denormalize(pred_pos + pred_err)
    err = np.linalg.norm(denorm_err_pos - denorm_pos)

    z_um, row, col  = denorm_pos

    return (row, col), z_um, err


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
