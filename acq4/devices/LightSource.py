"""Light-emitting devices, and how one shows its state on a control surface.

Besides :class:`LightSource` itself this module carries the two pieces of appearance a
light source needs and nobody else does: :func:`wavelengthToColor`, which turns a
source's configured wavelength into a colour to draw it in, and
:func:`renderSourceIndicator`, which draws one source's on/off indicator as an image.
Both live here rather than in a shared rendering module because they are this device's
idea of what a light source looks like -- an unlit LED is an open circle -- and not
anything a control surface, or any other consumer, has an opinion about.
"""

from __future__ import annotations

import math
from collections import OrderedDict

import pyqtgraph as pg

import acq4.util.Mutex as Mutex
from acq4.devices.ControlSurface import UnsupportedControlFeature, acquireControlFromConfig
from acq4.devices.Device import Device, TaskGui
from acq4.util import Qt
from pyqtgraph import SignalBlock

#: Wavelengths (m) bounding the range over which a spectral colour exists at all.
VISIBLE_RANGE = (380e-9, 780e-9)

#: Colour for a source past the long end of :data:`VISIBLE_RANGE` -- the rig's 850 nm IR
#: illuminator, say. Its light has no colour, and a literal spectral mapping fades to
#: black there, which on a key is indistinguishable from "off": a deep red instead says
#: "beyond red" while staying visible, and matches how an IR channel is conventionally
#: drawn.
INFRARED_COLOR = (170, 0, 0)

#: Colour for a source short of the visible range -- a UV LED -- by the same argument as
#: :data:`INFRARED_COLOR`, in the direction the spectrum was heading.
ULTRAVIOLET_COLOR = (150, 60, 230)

#: Colour for a source with no usable ``wavelength`` in its configuration: a white LED, a
#: broadband lamp, or simply an omission. Neutral white claims nothing about a spectrum,
#: which is exactly what is known about it.
UNKNOWN_WAVELENGTH_COLOR = (230, 230, 230)


def wavelengthToColor(wavelength) -> Qt.QColor:
    """Return a colour to draw a light source of *wavelength* in.

    Inside the visible range this is the usual piecewise-linear approximation of the
    spectrum, at full intensity: the dimming towards either end that a physically
    honest version applies is left out deliberately, because the result is drawn a
    centimetre across on a key and a 400 nm indicator faded to near-black reads as a
    dead key rather than as a violet one.

    Parameters
    ----------
    wavelength : float or None
        Wavelength in metres -- acq4 is SI throughout, so a 470 nm LED is ``470e-9``.
        None, a value that is not a finite positive number, or anything that is not a
        number at all, all mean "unknown" and give :data:`UNKNOWN_WAVELENGTH_COLOR`.

    Returns
    -------
    QColor
        The spectral colour, or one of :data:`INFRARED_COLOR`,
        :data:`ULTRAVIOLET_COLOR` and :data:`UNKNOWN_WAVELENGTH_COLOR` for the three
        cases that have no spectral colour.
    """
    try:
        nm = float(wavelength) * 1e9
    except (TypeError, ValueError):
        return Qt.QColor(*UNKNOWN_WAVELENGTH_COLOR)
    if not math.isfinite(nm) or nm <= 0:
        return Qt.QColor(*UNKNOWN_WAVELENGTH_COLOR)
    if nm < VISIBLE_RANGE[0] * 1e9:
        return Qt.QColor(*ULTRAVIOLET_COLOR)
    if nm > VISIBLE_RANGE[1] * 1e9:
        return Qt.QColor(*INFRARED_COLOR)

    if nm < 440:
        red, green, blue = (440 - nm) / 60, 0.0, 1.0
    elif nm < 490:
        red, green, blue = 0.0, (nm - 440) / 50, 1.0
    elif nm < 510:
        red, green, blue = 0.0, 1.0, (510 - nm) / 20
    elif nm < 580:
        red, green, blue = (nm - 510) / 70, 1.0, 0.0
    elif nm < 645:
        red, green, blue = 1.0, (645 - nm) / 65, 0.0
    else:
        red, green, blue = 1.0, 0.0, 0.0
    return Qt.QColor(round(red * 255), round(green * 255), round(blue * 255))


def renderSourceIndicator(label, color, filled: bool, size) -> Qt.QImage:
    """Draw one light source's on/off indicator as a ``QImage`` of *size*.

    A circle in the source's own colour, outlined while the source is off and filled
    while it is on -- an LED that is lit or not -- with the source's name under it. It is
    drawn on black, because that is what the rest of an unlit key is.

    Works on a ``QImage`` rather than a ``QPixmap`` so that it may be called from any
    thread, though a ``QApplication`` must exist first.

    Parameters
    ----------
    label : str or None
        Name of the source, drawn under the circle. None or empty draws the circle alone.
    color : QColor or colour spec
        The circle's colour; anything :func:`pyqtgraph.mkColor` accepts. See
        :func:`wavelengthToColor`.
    filled : bool
        Whether the source is on.
    size : tuple
        ``(width, height)`` in pixels, normally a control's declared image size.

    Returns
    -------
    QImage
    """
    width, height = int(size[0]), int(size[1])
    color = pg.mkColor(color)
    img = Qt.QImage(width, height, Qt.QImage.Format_ARGB32)
    img.fill(pg.mkColor('k'))

    label = '' if label is None else str(label)
    # the circle takes the upper two thirds and the name the bottom one; with no name to
    # draw, the circle has the whole face
    circleHeight = height if label == '' else height * 0.66
    diameter = min(width, circleHeight) * 0.66
    circle = Qt.QRectF(0, 0, diameter, diameter)
    circle.moveCenter(Qt.QPointF(width / 2.0, circleHeight / 2.0))
    textTop = int(circleHeight)
    textRect = Qt.QRect(2, textTop, max(1, width - 4), max(1, height - textTop - 2))
    flags = Qt.Qt.AlignCenter

    painter = Qt.QPainter(img)
    try:
        painter.setRenderHint(Qt.QPainter.Antialiasing)
        painter.setRenderHint(Qt.QPainter.TextAntialiasing)
        pen = Qt.QPen(color)
        pen.setWidthF(max(2.0, diameter * 0.12))
        painter.setPen(pen)
        painter.setBrush(color if filled else Qt.Qt.NoBrush)
        painter.drawEllipse(circle)
        if label != '':
            painter.setPen(pg.mkColor('w'))
            font = painter.font()
            # shrink to fit, as the key is small and the name is the rig integrator's
            for pointSize in range(max(4, textRect.height()), 3, -1):
                font.setPointSize(pointSize)
                bounds = Qt.QFontMetrics(font).boundingRect(textRect, flags, label)
                if bounds.width() <= textRect.width() and bounds.height() <= textRect.height():
                    break
            painter.setFont(font)
            painter.drawText(textRect, flags, label)
    finally:
        painter.end()
    return img


class LightSource(Device):
    """
    Abstract base class for light-emitting devices with one or more illumination sub-sources.
    
    Tracks the state and properties of light sources, providing unified control interface
    for devices with multiple channels (e.g., multi-wavelength LEDs).
    
    Configuration options:
    
    * **mock** (bool, optional): Whether to only pretend to be a light source. Default: False
    
    * **sources** (dict, optional): Named light source channels configuration
        - Key: Source name (e.g., 'Blue', 'Green')
        - Value: Source configuration dict containing:
            - **active** (bool, optional): Current on/off state of the source. This is updated
              at runtime; use *initialState* to request a state at startup. Default: False
            - **initialState** (bool or dict, optional): State to apply to the source when the
              device is created. May be a bool (True to turn the source on, False to turn it
              off) or a dict with optional 'active' (bool) and 'brightness' (float, 0.0-1.0)
              keys. If omitted, the source is left in whatever state the hardware is already in.
            - **adjustableBrightness** (bool, optional): Whether device supports brightness control. Default: False
            - **wavelength** (float, optional): Wavelength in meters (use units like 470*nm).
              Also picks the colour this source is drawn in on a control surface; see
              :func:`wavelengthToColor`.
            - **model** (str, optional): Hardware model identifier
            - **control** (dict, optional): A control-surface button that toggles this
              source and indicates while it is on. On a surface whose keys are displays
              the key shows the source's name under a circle in the source's colour,
              outlined while it is off and filled while it is on; on one whose keys are
              lit the key itself lights. See :meth:`_bindIndicator`.
    
    Example configuration::
    
        LEDLights:
            driver: 'CoolLEDLightSource'  # Note: LightSource is abstract; use a concrete subclass
            sources:
                Blue:
                    initialState: False  # make sure this LED is off at startup
                    adjustableBrightness: True
                    model: 'Thorlabs M470L3'
                    wavelength: 470 * nm
                    control:
                        device: 'PIKeyboard'
                        key: [7, 8]
                Green:
                    initialState:  # turn this LED on at startup, at half brightness
                        active: True
                        brightness: 0.5
                    adjustableBrightness: True
                    model: 'Thorlabs M505L3'
                    wavelength: 505 * nm
                    control:
                        device: 'PIKeyboard'
                        key: [7, 9]
    """

    # emitted when the on/off/brightness status of a light changes
    sigLightChanged = Qt.Signal(object, object)  # self, light_name

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.sourceConfigs = OrderedDict()  # [name: {'active': bool, 'wavelength': float, 'power': float, ...}, ...]
        self._lock = Mutex.Mutex()
        # control-surface buttons claimed by addSource(), each way round
        self._sourceControls = {}  # source name -> Control
        self._controlSources = {}  # Control -> source name
        # how each source's control shows its state, settled once by _bindIndicator();
        # a source whose control can indicate nothing has no entry here
        self._sourceIndicators = {}  # source name -> callable(bool)

    def quit(self):
        self._releaseControls()

    def _releaseControls(self):
        """Give back every source control claimed by :meth:`addSource`.

        A control holds a strong reference to its owner, so a light source that quit
        without releasing stays alive behind the surface, keeps answering its own keys,
        and leaves those addresses unclaimable -- a replacement source on the same key
        raises :class:`~acq4.devices.ControlSurface.ControlInUse`. A subclass with
        hardware to close overrides :meth:`quit` and calls this one.
        """
        for control in self._controlSources:
            control.release()
        self._sourceControls.clear()
        self._controlSources.clear()
        self._sourceIndicators.clear()

    def deviceInterface(self, win):
        return LightSourceDevGui(self)

    def taskInterface(self, taskRunner):
        return None  # TODO

    def validateSourceConfig(self, name, conf):
        """Check one source's configuration without acting on any of it.

        Subclasses extend this with what their own hardware needs -- a channel
        number, say -- so that a device can check every source it is about to
        build before it builds any of them. :meth:`addSource` applies
        *initialState*, which energises hardware, so a config error found partway
        through a set would otherwise leave the sources before it lit on a device
        that never finishes construction: absent from every UI, and with no object
        left that could switch them off.
        """
        state = conf.get('initialState')
        if state is not None:
            self._normalizedSourceState(name, state)

    def validateSourceConfigs(self, configs):
        """Validate a whole mapping of source configurations, acting on none.

        See :meth:`validateSourceConfig`. A device building several sources calls
        this before its add loop.
        """
        for name, conf in configs.items():
            self.validateSourceConfig(name, conf)

    def _normalizedSourceState(self, name, state):
        """Return *state* as a validated dict, raising ValueError if it is not one.

        *state* may be a bool (whether the source should be on) or a dict with
        optional 'active' (bool) and 'brightness' (float, normalized 0.0-1.0)
        keys. Brightness is checked against that range because it is normalized
        and the natural mistake is a percentage: a driver has no way to tell 50
        from a brightness it should obey, and formats it into a command the
        hardware cannot parse.
        """
        if not isinstance(state, dict):
            return {'active': bool(state)}
        unknown = set(state) - {'active', 'brightness'}
        if unknown:
            raise ValueError(
                f"Invalid light source state key(s) for ({self}, {name}): {sorted(unknown)}; "
                f"expected 'active' and/or 'brightness'")
        if 'brightness' in state:
            brightness = state['brightness']
            if isinstance(brightness, bool) or not isinstance(brightness, (int, float)):
                raise ValueError(
                    f"Invalid brightness for ({self}, {name}): {brightness!r}; expected a "
                    f"number from 0.0 to 1.0")
            if not 0.0 <= brightness <= 1.0:
                raise ValueError(
                    f"Brightness out of range for ({self}, {name}): {brightness!r}; "
                    f"brightness is normalized, so half brightness is 0.5, not 50")
        return dict(state)

    def addSource(self, name, conf):
        self.validateSourceConfig(name, conf)
        conf.setdefault("active", False)
        conf.setdefault("adjustableBrightness", False)
        self.sourceConfigs[name] = conf
        
        # Declare interface for this light source
        interface_name = f"{self.name()}:{name}"
        self.dm.declareInterface(interface_name, ['lightSource'], self)
        
        controlConf = conf.get('control')
        if controlConf is None and 'xkey' in conf:
            controlConf = {'xkey': conf['xkey']}
        if controlConf is not None:
            control = acquireControlFromConfig(controlConf, owner=self)
            self._sourceControls[name] = control
            self._controlSources[control] = name
            control.sigPressed.connect(self._controlPressed)
            self._bindIndicator(name, control)

        # Startup state is one-way: nothing restores the source's pre-ACQ4 state,
        # and no light source overrides quit(), so a lamp lit here stays lit
        # through ACQ4's own shutdown. Restoring it would mean putting back the
        # state found at startup only where the operator never touched the source
        # in between, which is a judgement nobody has asked these devices to make.
        if conf.get('initialState') is not None:
            self.setSourceState(name, conf['initialState'])

    def setSourceState(self, name, state):
        """Apply a combined on/off and brightness state to a light source.

        *state* may be a bool (whether the source should be on) or a dict with optional
        'active' (bool) and 'brightness' (float, normalized 0.0-1.0) keys. It is
        validated in full before any of it is applied, so a state that names an
        unknown key or an out-of-range brightness changes nothing.
        """
        state = self._normalizedSourceState(name, state)
        # brightness first so that activating the source uses the requested brightness
        if 'brightness' in state:
            self.setSourceBrightness(name, state['brightness'])
        if 'active' in state:
            self.setSourceActive(name, state['active'])

    def describe(self, onlyActive=True):
        """Return a description of the current state of all active light sources.

        If onlyActive is False, then information for all sources will be returned, whether or not they are active.
        """
        if onlyActive:
            return OrderedDict([(n, s) for n, s in self.sourceConfigs.items() if s['active']])
        else:
            return self.sourceConfigs.copy()

    def activeSources(self):
        """Return the names of all active light sources.
        """
        return [s['name'] for s in self.sourceConfigs if s['active']]

    def loadPreset(self, conf: str | dict):
        if conf == 'off':
            for c in self.sourceConfigs:
                self.setSourceActive(c, False)
            return
        chan = conf['channel']
        for c in self.sourceConfigs:
            self.setSourceActive(c, c == chan)
        if 'brightness' in conf:
            self.setSourceBrightness(chan, conf['brightness'])

    def sourceActive(self, name):
        """Return True if the named light source is currently active.
        """
        return self.sourceConfigs[name]['active']

    def setSourceActive(self, name, active):
        """Activate / deactivate a light source.
        """
        raise NotImplementedError()

    def setSourceActiveFromNamedButton(self, active):
        btn = self.sender()
        self.setSourceActive(btn.objectName(), active)

    def getSourceBrightness(self, name):
        """
        Optional, depending on hardware support.

        Returns
        -------
        float
            A brightness value normalized between 0.0 and 1.0
        """
        raise NotImplementedError()

    def setSourceBrightness(self, name, value):
        """
        Optional, depending on hardware support.

        Parameters
        ----------
        name : str
        value : float
            New brightness setting, normalized between 0.0 and 1.0.
        """
        raise NotImplementedError()

    def _bindIndicator(self, name, control):
        """Work out once how *control* can indicate whether source *name* is on.

        Output belongs to each control surface rather than to a generic interface, so this
        asks the control what it offers, keeping as much of the indicator as each one can
        carry:

        * a control with a display gets the whole thing: the source's name under a circle
          in the source's own colour (:func:`wavelengthToColor`), outlined while the
          source is off and filled while it is on -- see :func:`renderSourceIndicator`;
        * an X-Keys key gets ``setBacklight(blue, red)``, both LEDs lit while the source
          is on, because outlined-versus-filled means nothing to a key with no pixels;
        * any other colour-taking control gets that same "both LEDs lit", spelled
          magenta.

        Both of the light-only indicators are "both LEDs lit". That is what the X-Keys
        path has always produced -- it assigned to ``bl[row, col]``, and since the
        backlight array is ``(rows, cols, 2)`` that set *both* LEDs -- and magenta is
        exactly what a blue and a red LED lit together look like, where white has a green
        component two such LEDs cannot produce at all.

        Having the method is not proof the control has the output -- one control class
        covers a surface's keys *and* its dials, and an X-Keys jog wheel has no LEDs -- so
        each candidate is tried once, on the "off" state the source starts in, and one
        that refuses is passed over. Resolving it here means :meth:`_updateXkeyLight` is a
        call rather than a decision, and a control that can indicate nothing is said so
        once instead of on every switch.

        Parameters
        ----------
        name : str
            The source this control indicates.
        control : Control
            The control, already acquired for this device.
        """
        candidates = []
        imageSize = control.capabilities()['output'].get('image')
        if imageSize and hasattr(control, 'setImage'):
            # both frames up front: the colour and the size cannot change for the life of
            # the device, so a toggle is a write rather than a render
            color = wavelengthToColor(self.sourceConfigs[name].get('wavelength'))
            frames = {
                state: renderSourceIndicator(name, color, filled=state, size=tuple(imageSize))
                for state in (False, True)
            }
            candidates.append(lambda on: control.setImage(frames[bool(on)]))
        if hasattr(control, 'setBacklight'):
            candidates.append(lambda on: control.setBacklight(int(on), int(on)))
        if hasattr(control, 'setColor'):
            candidates.append(lambda on: control.setColor('m' if on else 'k'))
        for indicator in candidates:
            try:
                indicator(False)
            except UnsupportedControlFeature:
                continue  # the class offers it, this control does not
            self._sourceIndicators[name] = indicator
            return
        self.logger.warning(
            f"{self.name()}: {control} will not indicate whether source {name!r} is on; it"
            f" offers no output this device knows how to drive. The button still toggles"
            f" the source."
        )

    def _updateXkeyLight(self, name):
        """Light this source's control-surface button while the source is on.

        The name is historical -- the button need not be on an X-Keys -- and is kept
        because concrete subclasses call it. How the button is lit was decided once, by
        :meth:`_bindIndicator`.
        """
        indicator = self._sourceIndicators.get(name)
        if indicator is not None:
            indicator(self.sourceConfigs[name]['active'])

    def _controlPressed(self, control):
        """Toggle the light source bound to *control*."""
        name = self._controlSources[control]
        self.setSourceActive(name, not self.sourceActive(name))


class LightSourceDevGui(Qt.QWidget):
    def __init__(self, dev):
        """
        Parameters
        ----------
        dev : LightSource
        """
        super(LightSourceDevGui, self).__init__()
        self.dev = dev

        self.layout = Qt.QGridLayout()
        self.setLayout(self.layout)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.sourceActivationButtons = {}
        self.sourceBrightnessSliders = {}

        for i, name in enumerate(self.dev.sourceConfigs):
            conf = self.dev.sourceConfigs[name]
            if conf.get("adjustableBrightness", False):
                slider = Qt.QSlider()
                slider.setMaximum(100)
                slider.setMinimum(0)
                slider.setObjectName(name)
                slider_cont = Qt.QGridLayout()
                self.sourceBrightnessSliders[name] = slider
                slider.valueChanged.connect(self._sliderChanged)
                slider_cont.addWidget(slider, 0, 0)
                self.layout.addLayout(slider_cont, 0, i)
            btn = Qt.QPushButton(name)
            btn.setObjectName(name)
            btn.setCheckable(True)
            self.sourceActivationButtons[name] = btn
            self.layout.addWidget(btn, 1, i)
            btn.clicked.connect(self.dev.setSourceActiveFromNamedButton)
        self._updateValuesToMatchDev()
        self.dev.sigLightChanged.connect(self._updateValuesToMatchDev)

    def _sliderChanged(self, value):
        slider = self.sender()
        self.dev.setSourceBrightness(slider.objectName(), value / slider.maximum())

    def _updateValuesToMatchDev(self, dev=None, source=None):
        names = [source] if source is not None else list(self.dev.sourceConfigs)
        for name in names:
            button = self.sourceActivationButtons[name]
            with SignalBlock(button.clicked, self.dev.setSourceActiveFromNamedButton):
                button.setChecked(self.dev.sourceActive(name))
            if name in self.sourceBrightnessSliders:
                slider = self.sourceBrightnessSliders[name]
                with SignalBlock(slider.valueChanged, self._sliderChanged):
                    slider.setValue(int(self.dev.getSourceBrightness(name) * slider.maximum()))


class LightSourceTaskGui(TaskGui):
    def __init__(self, dev, taskRunner):
        super(LightSourceTaskGui, self).__init__(dev, taskRunner)
        self.dev = dev
        self.taskRunner = taskRunner
        # TODO?
