from __future__ import annotations

from functools import lru_cache
from threading import RLock
from typing import Optional

import click
import numpy as np
import scipy.stats
import tifffile
from PIL import Image

import pyqtgraph as pg
from MetaArray import MetaArray
from acq4.util.future import Future, future_wrap
from acq4.util.imaging import Frame
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
    image = (image - np.uint16(min_in)) * (((max_out - min_out) / (max_in - min_in)) + min_out)
    # image = (image - np.uint16(min_in)) * (
    #     (max_out / (max_in - min_in))
    # )
    image = scipy.ndimage.zoom(image, 3)
    offset_w = int(image.shape[0] * 0.3)
    offset_h = int(image.shape[1] * 0.3)
    margin_w = int(image.shape[0] * 0.4)
    margin_h = int(image.shape[1] * 0.4)
    image = image[offset_w : offset_w + margin_w, offset_h : offset_h + margin_h]
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
        import acq4.util.pipette_detection.torch_model_05
        from acq4.util.pipette_detection.torch_model_05 import PipetteDetector

        detector_path = os.path.dirname(acq4.util.pipette_detection.torch_model_05.__file__)
        model_file = os.path.join(detector_path, "torch_models", "05_deeper_training.pth")

        # Model 06
        # import acq4.util.pipette_detection.torch_model_06
        # from acq4.util.pipette_detection.torch_model_06 import PipetteDetector
        # detector_path = os.path.dirname(acq4.util.pipette_detection.torch_model_06.__file__)
        # model_file = os.path.join(detector_path, 'torch_models', '06_resnet50.pth')

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = PipetteDetector()
        model.to(device)
        model.load_state_dict(torch.load(model_file))

        _pipette_detection_model = model
    return _pipette_detection_model


analysis_window = None
viewer_window = None


def do_pipette_tip_detection(data: np.ndarray, angle: float, show=False):
    """
    Parameters
    ----------
    data : image data shaped like [cols, rows]
    angle : angle of pipette in degrees, measured wittershins relative to pointing directly rightward
    """
    import torch
    from acq4.util.pipette_detection.torch_model_04 import make_image_tensor, pos_normalizer
    from acq4.util.pipette_detection.test_data import make_rotated_crop

    global analysis_window

    model = get_pipette_detection_model()

    # rotate and crop image
    margin = np.clip((np.array(data.shape) - 400) // 2, 0, None)
    crop = (slice(margin[0], margin[0] + 400), slice(margin[1], margin[1] + 400))
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

    if show:
        imv = pg.ImageView()
        imv.setImage(img.T)
        pt = pg.TargetItem(pos=(x, y))
        imv.target = pt
        imv.view.addItem(pt)
        imv.show()
        analysis_window = imv

    return pos_xy, z, snr, locals()


@future_wrap
def detect_neurons(
    frames: Frame | list[Frame],
    model: str = "healthy-cellpose",
    classifier: str = None,
    autoencoder: str = None,
    _future: Future = None,
) -> list:
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
        return rmt_this.do_neuron_detection(
            rmt_array.data, transform, model, do_3d, classifier, autoencoder, _timeout=60
        )


def do_neuron_detection(
    data: np.ndarray,
    transform: SRTTransform3D,
    model: str = "healthy-cellpose",
    do_3d: bool = False,
    classifier: str = None,
    autoencoder: str = None,
) -> list:
    if model == "healthy-cellpose":
        return _do_healthy_neuron_detection(data, transform, classifier, autoencoder)
    elif model == "cellpose":
        return _do_neuron_detection_cellpose(data, transform, do_3d)
    elif model == "yolo":
        return _do_neuron_detection_yolo(data, transform)
    else:
        raise ValueError(f"Unknown model {model}")


def _do_healthy_neuron_detection(data, transform, classifier, autoencoder, diameter: int = 35, camera_pixel_size: float = 0.32, z_scale: float = 1, n: int = 10):
    from acq4.util.healthy_cell_detector.train import get_health_ordered_cells, load_classifier
    from acq4.util.healthy_cell_detector.models import NeuronAutoencoder
    import torch

    classifier = load_classifier(classifier)
    autoencoder = NeuronAutoencoder.load(autoencoder).to("cuda" if torch.cuda.is_available() else "cpu")
    autoencoder.eval()
    cells = get_health_ordered_cells(data, classifier, autoencoder, diameter, camera_pixel_size, z_scale)
    return [
        (transform.map(center - diameter / 2), transform.map(center + diameter / 2))
        for center in cells[:n]
    ]


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
    mask = get_cellpose_masks(data, do_3d, z_axis=0 if do_3d else None, stitch_threshold=0.25 if do_3d else 0)

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


def get_cellpose_masks(data, diameter=35, stitch_threshold=0.25, z_axis=0):
    model = get_cyto3_model()
    # TODO do this without copying the data
    if data.shape[-1] == data.shape[-2]:
        data = data[:, np.newaxis, :, 0:-2]  # add channel dimension, weird the shape
    else:
        data = data[:, np.newaxis, :, :]  # add channel dimension
    masks_pred, flows, styles, diams = model.eval(
        [data],
        diameter=diameter,
        channel_axis=1,
        z_axis=z_axis,
        stitch_threshold=stitch_threshold,
    )
    return masks_pred[0]


@lru_cache(maxsize=1)
def get_cyto3_model():
    from cellpose import models

    return models.Cellpose(gpu=True, model_type="cyto3")


class WhimsicalViewer(pg.QtWidgets.QMainWindow):
    """A whimsical GUI for viewing 3D image stacks with bounding boxes."""
    
    def __init__(self, data, neurons, title="Whimsical Cell Viewer"):
        global viewer_window
        super().__init__()
        viewer_window = self
        
        self.data = data
        self.neurons = neurons
        self.current_z = len(data) // 2 if len(data) > 1 else 0
        self.max_z = len(data) - 1
        
        # Setup UI
        self.setWindowTitle(title)
        self.resize(800, 600)
        
        # Create central widget and layout
        central_widget = pg.QtWidgets.QWidget()
        layout = pg.QtWidgets.QVBoxLayout()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)
        
        # Create image view
        self.image_view = pg.ImageView()
        layout.addWidget(self.image_view)
        
        # Create controls
        controls_layout = pg.QtWidgets.QHBoxLayout()
        layout.addLayout(controls_layout)
        
        # Z slider
        slider_layout = pg.QtWidgets.QHBoxLayout()
        controls_layout.addLayout(slider_layout)
        
        slider_layout.addWidget(pg.QtWidgets.QLabel("Z Layer:"))
        self.z_slider = pg.QtWidgets.QSlider(pg.QtCore.Qt.Horizontal)
        self.z_slider.setMinimum(0)
        self.z_slider.setMaximum(self.max_z)
        self.z_slider.setValue(self.current_z)
        self.z_slider.valueChanged.connect(self.update_z)
        slider_layout.addWidget(self.z_slider)
        
        self.z_label = pg.QtWidgets.QLabel(f"{self.current_z}/{self.max_z}")
        slider_layout.addWidget(self.z_label)
        
        # Navigation buttons
        nav_layout = pg.QtWidgets.QHBoxLayout()
        controls_layout.addLayout(nav_layout)
        
        self.prev_button = pg.QtWidgets.QPushButton("⬅️ Previous")
        self.prev_button.clicked.connect(self.prev_z)
        nav_layout.addWidget(self.prev_button)
        
        self.next_button = pg.QtWidgets.QPushButton("Next ➡️")
        self.next_button.clicked.connect(self.next_z)
        nav_layout.addWidget(self.next_button)
        
        # Legend
        legend_layout = pg.QtWidgets.QHBoxLayout()
        controls_layout.addLayout(legend_layout)
        
        legend_layout.addWidget(pg.QtWidgets.QLabel("Legend:"))
        
        above_label = pg.QtWidgets.QLabel("Above")
        above_label.setStyleSheet("color: blue")
        legend_layout.addWidget(above_label)
        
        current_label = pg.QtWidgets.QLabel("Current")
        current_label.setStyleSheet("color: green")
        legend_layout.addWidget(current_label)
        
        below_label = pg.QtWidgets.QLabel("Below")
        below_label.setStyleSheet("color: red")
        legend_layout.addWidget(below_label)
        
        # Initialize display
        self.roi_items = []
        self.update_display()
    
    def update_z(self, z):
        self.current_z = z
        self.z_label.setText(f"{self.current_z}/{self.max_z}")
        self.update_display()
    
    def prev_z(self):
        if self.current_z > 0:
            self.current_z -= 1
            self.z_slider.setValue(self.current_z)
    
    def next_z(self):
        if self.current_z < self.max_z:
            self.current_z += 1
            self.z_slider.setValue(self.current_z)
    
    def update_display(self):
        # Update image
        self.image_view.setImage(self.data[self.current_z], autoLevels=True)
        
        # Clear existing ROIs
        for roi in self.roi_items:
            self.image_view.removeItem(roi)
        self.roi_items = []
        
        # Add new ROIs with appropriate colors
        for neuron in self.neurons:
            start, end = neuron
            
            # Determine if the bounding box is above, below, or at the current z-level
            # This is a simplification - in reality we'd need to check the actual z coordinates
            # For now, we'll use a random assignment for demonstration
            z_min, z_max = self._get_z_range(neuron)
            
            if self.current_z < z_min:
                pen = pg.mkPen('b', width=2)  # Blue for above
            elif self.current_z > z_max:
                pen = pg.mkPen('r', width=2)  # Red for below
            else:
                pen = pg.mkPen('g', width=2)  # Green for current
            
            roi = pg.ROI(start[:2], size=end[:2] - start[:2], pen=pen)
            self.image_view.addItem(roi)
            self.roi_items.append(roi)
    
    def _get_z_range(self, neuron):
        """Determine the z-range of a neuron bounding box."""
        start, end = neuron
        
        # If we have 3D coordinates
        if len(start) > 2 and len(end) > 2:
            return start[2], end[2]
        
        # For 2D bounding boxes, we'll estimate a z-range
        # This is just for demonstration - in a real application,
        # you'd want to use actual 3D bounding boxes
        z_span = min(5, self.max_z // 3)
        center_z = np.random.randint(z_span, self.max_z - z_span)
        return center_z - z_span, center_z + z_span


@click.command()
@click.argument("image", required=True)
@click.option(
    "--model",
    default="cellpose",
    show_default=True,
    type=click.Choice(["healthy-cellpose", "cellpose", "yolo", "pipette"]),
)
@click.option("--angle", default=0, show_default=True, type=float)
@click.option("--z", default=0, show_default=True, type=int)
@click.option("--display", is_flag=True, type=bool)
@click.option("--classifier", default=None, type=str)
@click.option("--autoencoder", default=None, type=str)
def cli(image, model, angle, z, display, classifier, autoencoder):
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
    
    # Always create QApplication for GUI
    pg.mkQApp()
    
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
        neurons = do_neuron_detection(data, null_xform, model, do_3d, classifier, autoencoder)
        print(f"Detected {len(neurons)} neuron(s)")
        
        # Prepare data for display
        if do_3d:
            # For 3D data, we already have a stack
            display_data = data
        else:
            # For 2D data, create a fake stack with a single layer
            display_data = data[np.newaxis, ...]
        
        # Launch the whimsical viewer
        if display:
            viewer = WhimsicalViewer(display_data, neurons, f"Cell Detector - {model}")
            viewer.show()
            pg.exec()


if __name__ == "__main__":
    cli()
