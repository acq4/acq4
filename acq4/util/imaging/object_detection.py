from __future__ import annotations

from functools import lru_cache
from pickle import UnpicklingError
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
from pyqtgraph.debug import printExc
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
        return rmt_this.do_pipette_tip_detection(rmt_array.data, angle, _timeout=600)


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
                w.addWidget(imv, 0, i)
            analysis_window = w
            w.resize(900, 300)

        views = analysis_window.views
        views[0].setImage(scaled.image.T)
        views[0].target.setPos(*scaled_pos_rc[::-1])
        views[1].setImage(cropped.image.T)
        views[1].target.setPos(*cropped_pos_rc[::-1])
        views[0].setImage(image.image.T)
        views[0].target.setPos(*image_pos_rc[::-1])

        w.show()

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
def detect_neurons(
    frames: Frame | list[Frame],
    model: str = "healthy-cellpose",
    classifier: str = None,
    autoencoder: str = None,
    diameter: int = 35,
    xy_scale: float = 0.32e-6,
    z_scale: float = 1e-6,
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
            rmt_array.data, transform, model, do_3d, classifier, autoencoder, diameter, xy_scale, z_scale, _timeout=60
        )


def do_neuron_detection(
    data: np.ndarray,
    transform: SRTTransform3D,
    model: str = "healthy-cellpose",
    do_3d: bool = False,
    classifier: str = None,
    autoencoder: str = None,
    diameter: int = 35,
    xy_scale: float = 0.32e-6,
    z_scale: float = 1e-6,
    n: int = 10,
) -> list:
    if model == "healthy-cellpose":
        return _do_healthy_neuron_detection(data, transform, classifier, autoencoder, diameter, xy_scale, z_scale, n)
    elif model == "cellpose":
        return _do_neuron_detection_cellpose(data, transform, do_3d)
    elif model == "yolo":
        return _do_neuron_detection_yolo(data, transform)
    else:
        raise ValueError(f"Unknown model {model}")


_classifier = None
_autoencoder = None


def _do_healthy_neuron_detection(
    data: np.ndarray, transform, classifier, autoencoder, diameter, xy_scale, z_scale, n: int = 10
):
    global _classifier, _autoencoder
    from acq4.util.healthy_cell_detector.train_nn_classifier import get_health_ordered_cells, load_classifier as nn_load
    from acq4.util.healthy_cell_detector.train_rf_classifier import load_classifier as rf_load
    from acq4.util.healthy_cell_detector.models import NeuronAutoencoder
    import torch

    if _classifier is None:
        try:
            _classifier = nn_load(classifier)
            _classifier.model.eval()
        except (AttributeError, UnpicklingError):
            _classifier = rf_load(classifier)
    if _autoencoder is None:
        _autoencoder = NeuronAutoencoder.load(autoencoder).to("cuda" if torch.cuda.is_available() else "cpu")
        _autoencoder.eval()
    cells = get_health_ordered_cells(data, _classifier, _autoencoder, diameter, xy_scale, z_scale)
    return [
        (transform.map(center[::-1] - (31, 31, 10)), transform.map(center[::-1] + (31, 31, 10)))
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
        batch_size=1,
        channel_axis=1,
        z_axis=z_axis,
        do_3D=False,  # this version of do_3D tries to detect on XZ and YZ
        stitch_threshold=stitch_threshold,  # this triggers the correct 3D algorithm
        cellprob_threshold=0.0,
        flow_threshold=None,
        normalize={
            'lowhigh': None,
            'percentile': [1.0, 99.0],
            'normalize': True,
            'norm3D': True,
            'sharpen_radius': 0,
            'smooth_radius': 0,
            'tile_norm_blocksize': 0,
            'tile_norm_smooth3D': 1,
            'invert': False,
        },
    )
    print(f"cellpose found {masks_pred[0].max()} distinct cells")
    return masks_pred[0]


@lru_cache(maxsize=1)
def get_cyto3_model():
    from cellpose import models

    return models.Cellpose(gpu=True, model_type="cyto3")


class NeuronBoxViewer(pg.QtWidgets.QMainWindow):
    """A GUI for viewing 3D image stacks with bounding boxes."""

    def __init__(self, data, neurons, title="Cell Viewer"):
        global viewer_window
        super().__init__()
        viewer_window = self
        
        # Set up keyboard shortcuts
        self.quit_shortcut = pg.QtWidgets.QShortcut(pg.QtGui.QKeySequence("Ctrl+Q"), self)
        self.quit_shortcut.activated.connect(self.close)

        self.data = data  # ijk
        self.neurons = neurons  # [(start, end), ...] in xyz
        self.current_z = len(data) // 2 if len(data) > 1 else 0
        self.max_z = len(data) - 1
        self.cell_viewers = []  # Keep track of open cell viewers

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

        # Instructions
        instructions = pg.QtWidgets.QLabel("Click on a cell to view normalized 3D extraction")
        instructions.setStyleSheet("color: #555; font-style: italic;")
        layout.addWidget(instructions)

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
        self.image_view.setImage(self.data[self.current_z], autoLevels=True, autoRange=False)

        # Clear existing ROIs
        for roi in self.roi_items:
            self.image_view.removeItem(roi)
        self.roi_items = []

        # Add new ROIs with appropriate colors
        for i, neuron in enumerate(self.neurons):
            start, end = neuron

            # Determine if the bounding box is above, below, or at the current z-level
            z_min, z_max = self._get_z_range(neuron)

            if self.current_z < z_min:
                pen = pg.mkPen("b", width=2)  # Blue for above
                hover_pen = pg.mkPen("b", width=3)  # Slightly thicker on hover
            elif self.current_z > z_max:
                pen = pg.mkPen("r", width=2)  # Red for below
                hover_pen = pg.mkPen("r", width=3)  # Slightly thicker on hover
            else:
                pen = pg.mkPen("g", width=2)  # Green for current
                hover_pen = pg.mkPen("g", width=3)  # Slightly thicker on hover

            # Create a clickable ROI
            roi = ClickableROI(start[:2], size=end[:2] - start[:2], pen=pen, hover_pen=hover_pen, index=i, parent=self)
            self.image_view.addItem(roi)
            self.roi_items.append(roi)

    def _get_z_range(self, neuron):
        """Determine the z-range of a neuron bounding box."""
        start, end = neuron

        # If we have 3D coordinates
        if len(start) > 2 and len(end) > 2:
            return start[2], end[2]

        return 0, 0

    def open_cell_viewer(self, index):
        """Open a normalized-for-autoencoder view of the selected cell"""
        neuron = self.neurons[index]
        start, end = neuron

        try:
            # Extract the region around the cell center
            region = self.data[
                     int(max(0, start[2])) : int(min(self.data.shape[0], end[2])),
                     int(max(0, start[1])) : int(min(self.data.shape[1], end[1])),
                     int(max(0, start[0])) : int(min(self.data.shape[2], end[0])),
             ]
            # region = extract_region(self.data, center, xy_scale, z_scale)

            # Create a viewer for the extracted region
            viewer = CellRegionViewer(region, f"Cell {index+1} Normalized")
            viewer.show()

            # Keep a reference to prevent garbage collection
            self.cell_viewers.append(viewer)

        except Exception as e:
            printExc("Could not extract cell region")
            pg.QtWidgets.QMessageBox.warning(self, "Extraction Error", f"Could not extract cell region: {str(e)}")


class ClickableROI(pg.ROI):
    """An ROI that can be clicked to open a cell viewer"""

    def __init__(self, pos, size, index, parent, pen=None, hover_pen=None, **kwargs):
        super().__init__(pos, size, pen=pen, **kwargs)
        self.index = index
        self.parent = parent
        self.hover_pen = hover_pen if hover_pen is not None else pen
        self.default_pen = pen
        self.setAcceptHoverEvents(True)

    def hoverEnterEvent(self, ev):
        self.setPen(self.hover_pen)
        self.update()

    def hoverLeaveEvent(self, ev):
        self.setPen(self.default_pen)
        self.update()

    def mouseClickEvent(self, ev):
        if ev.button() == pg.QtCore.Qt.LeftButton:
            self.parent.open_cell_viewer(self.index)
            ev.accept()
        else:
            super().mouseClickEvent(ev)


class CellRegionViewer(pg.QtWidgets.QMainWindow):
    """A viewer for displaying extracted cell regions"""

    def __init__(self, region_data, title="Cell Region Viewer"):
        super().__init__()

        # Region data should be shape (z, y, x) or (1, y, x)
        self.region_data = region_data

        # Setup UI
        self.setWindowTitle(title)
        self.resize(400, 500)

        # Create central widget and layout
        central_widget = pg.QtWidgets.QWidget()
        layout = pg.QtWidgets.QVBoxLayout()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        # Create image view
        self.image_view = pg.ImageView()
        layout.addWidget(self.image_view)

        # If we have a 3D region, add z controls
        if region_data.shape[0] > 1:
            # Z slider
            slider_layout = pg.QtWidgets.QHBoxLayout()
            layout.addLayout(slider_layout)

            slider_layout.addWidget(pg.QtWidgets.QLabel("Z Layer:"))
            self.z_slider = pg.QtWidgets.QSlider(pg.QtCore.Qt.Horizontal)
            self.z_slider.setMinimum(0)
            self.z_slider.setMaximum(region_data.shape[0] - 1)
            self.z_slider.setValue(region_data.shape[0] // 2)
            self.z_slider.valueChanged.connect(self.update_z)
            slider_layout.addWidget(self.z_slider)

            self.z_label = pg.QtWidgets.QLabel(f"{region_data.shape[0] // 2}/{region_data.shape[0] - 1}")
            slider_layout.addWidget(self.z_label)

            # Display initial z slice
            self.current_z = region_data.shape[0] // 2
            self.image_view.setImage(region_data[self.current_z])
        else:
            # Just display the 2D image
            self.image_view.setImage(region_data[0])

    def update_z(self, z):
        self.current_z = z
        self.z_label.setText(f"{self.current_z}/{self.region_data.shape[0] - 1}")
        self.image_view.setImage(self.region_data[self.current_z])


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
@click.option("--diameter", default=35, type=int)
@click.option("--xy-scale", default=0.32e-6, type=float)
@click.option("--z-scale", default=1e-6, type=float)
@click.option("--count", default=10, type=int)
def cli(image, model, angle, z, display, classifier, autoencoder, diameter, xy_scale, z_scale, count):
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
        neurons = do_neuron_detection(
            data, null_xform, model, do_3d, classifier, autoencoder, diameter, xy_scale, z_scale, count
        )
        print(f"Detected {len(neurons)} neuron(s)")

        # Prepare data for display
        if do_3d:
            # For 3D data, we already have a stack
            display_data = data
        else:
            # For 2D data, create a fake stack with a single layer
            display_data = data[np.newaxis, ...]

        # Launch the viewer
        if display:
            viewer = NeuronBoxViewer(display_data, neurons, f"Cell Detector - {model}")
            viewer.show()
            pg.exec()


if __name__ == "__main__":
    cli()
