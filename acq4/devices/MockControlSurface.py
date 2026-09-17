"""Hardware-free :class:`~acq4.devices.ControlSurface.ControlSurface` implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyqtgraph as pg

from acq4.devices.ControlSurface import Control, ControlSurface, UnsupportedControlFeature
from acq4.util import Qt

if TYPE_CHECKING:
    import acq4


class MockControl(Control):
    """One control of a :class:`MockControlSurface`, which shows things by recording them.

    Output is each surface's own business, so this stand-in has an output API of its own
    rather than inheriting one: :meth:`setColor`, :meth:`setText`, :meth:`setImage` and
    :meth:`clear`, each refused on a control whose block does not declare it. Nothing is
    drawn and nothing is rendered -- every accepted write is appended to
    :attr:`MockControlSurface.writes` for a test to read back.

    The vocabulary is deliberately the shape a real display-bearing surface has (see
    :class:`acq4.devices.StreamDock.streamdock.StreamDockControl`), so a consumer that
    speaks it can be exercised without hardware. A consumer that wants an X-Keys key's two
    LEDs finds no ``setBacklight`` here and should be tested against
    :class:`acq4.devices.XKeys.XKeys` itself.
    """

    def _output(self) -> dict:
        return self._capabilities['output']

    def _require(self, feature: str) -> None:
        """Raise unless this control's block declares *feature*."""
        if not self._output().get(feature):
            raise UnsupportedControlFeature(f"{self} has no {feature} output")

    def setColor(self, color) -> None:
        """Show *color*, or raise if this control's stand-in hardware could not.

        A block declaring ``color: 'noGreen'`` stands in for a key lit by one blue and one
        red LED, as an X-Keys key is, and refuses any colour with a green component. The
        refusal is the generic exception: a real surface with an idiosyncratic colour space
        is free to raise a subclass of its own carrying more detail, and what matters here
        is only that an impossible request fails rather than being approximated.
        """
        self._require('color')
        color = pg.mkColor(color)
        if self._output().get('color') == 'noGreen' and color.green() != 0:
            raise UnsupportedControlFeature(
                f"{self} cannot show {color.name()}; it stands in for a key lit by one blue"
                f" and one red LED, so any colour with a green component is impossible"
            )
        self._setAppearance('color', color=color)

    def setText(self, text, color=None, background=None) -> None:
        """Show *text*, with an optional text and background colour."""
        self._require('text')
        self._setAppearance('text', text=text, color=color, background=background)

    def setImage(self, image) -> None:
        """Show *image*, recorded exactly as given -- nothing here scales or converts."""
        self._require('image')
        self._setAppearance('image', image=image)

    def clear(self) -> None:
        """Blank this control.

        Raises
        ------
        UnsupportedControlFeature
            If this control has no output at all, and so nothing to blank.
        """
        if not any(self._output().values()):
            raise UnsupportedControlFeature(f"{self} has no output to clear")
        self._setAppearance('clear')

    def _blank(self) -> None:
        """Blank this control on release and on a page switch, if it has any output."""
        if any(self._output().values()):
            self.clear()


class MockControlSurface(ControlSurface):
    """Simulated control surface for testing, demonstration and rigs without hardware.

    Offers four blocks, chosen so that both dial modes and a refused output can be
    exercised without hardware:

    * a **display button** block, keyed ``('img', row, col)``, which shows images, text and
      any colour -- the shape of a Stream Dock key;
    * a **lit button** block, keyed ``('lit', row, col)``, which shows a colour and nothing
      else, and whose stand-in hardware refuses any colour with a green component --
      mimicking a key lit by one blue and one red LED, as an X-Keys key is (see
      :attr:`LIT_BUTTON_CAPS`);
    * a **relative dial**, keyed ``'jog'``, pressable, with a display;
    * an **absolute dial**, keyed ``'fader'``, with an evdev-style range including a centre
      deadzone (``flat``) and a noise floor (``fuzz``), and no output at all.

    Pages are emulated in software by the base class.

    Output
    ------
    Output is the surface's own business, so this one has an API of its own on
    :class:`MockControl`: ``setColor``, ``setText``, ``setImage`` and ``clear``, each
    refused where the block does not declare it. Nothing is drawn anywhere; every accepted
    write is appended to :attr:`writes` for inspection. Tests and interactive users inject
    activity with :meth:`mockPress`, :meth:`mockRelease`, :meth:`mockMove` and
    :meth:`mockTouch`, or through the device-rack widget.

    Configuration options:

    * **pages** (int, optional): Number of software-emulated pages. Default: 2

    * **buttons** (dict, optional): Shape of the display button block as ``{'rows': int,
      'cols': int}``. Default: ``{'rows': 2, 'cols': 3}``

    * **litButtons** (dict, optional): Shape of the lit-but-displayless button block as
      ``{'rows': int, 'cols': int}``. Default: ``{'rows': 2, 'cols': 4}``

    * **imageSize** (tuple, optional): ``(width, height)`` of the display buttons'
      displays, in pixels. Default: ``(72, 72)``

    Example configuration::

        MockSurface:
            driver: 'MockControlSurface'
            pages: 3
            buttons: {'rows': 2, 'cols': 5}
            litButtons: {'rows': 4, 'cols': 8}
    """

    #: The control class carrying this surface's output API.
    _controlClass = MockControl

    #: Capabilities of the display button block.
    IMAGE_BUTTON_CAPS = {
        'input': {'press': True},
        'output': {'image': (72, 72), 'text': True, 'color': True},
    }

    #: Capabilities of the lit-but-displayless button block. ``'noGreen'`` is this
    #: surface's own word for the restriction its stand-in hardware has -- a key lit by one
    #: blue and one red LED can show any colour with no green component and no other -- and
    #: it lives in the block's ``output``, which the base class passes through without
    #: opinion, because that is where a surface says what its hardware can do. A subclass
    #: whose buttons should show anything overrides this with ``{'color': True}``.
    LIT_BUTTON_CAPS = {
        'input': {'press': True},
        'output': {'color': 'noGreen'},
    }

    #: Capabilities of the relative dial.
    RELATIVE_DIAL_CAPS = {
        'input': {'press': True, 'mode': 'relative', 'resolution': 1},
        'output': {'image': (200, 100)},
    }

    #: Capabilities of the absolute dial.
    ABSOLUTE_DIAL_CAPS = {
        'input': {
            'press': False,
            'mode': 'absolute',
            'min': -100,
            'max': 100,
            'flat': 5,
            'fuzz': 3,
            'resolution': 1,
        },
        'output': {},
    }

    def __init__(self, deviceManager: acq4.Manager.Manager, config: dict, name: str):
        ControlSurface.__init__(self, deviceManager, config, name)

        #: Every appearance write, in order, as dicts with an ``'op'`` key.
        self.writes: list[dict] = []

        imageSize = tuple(config.get('imageSize', (72, 72)))
        buttons = config.get('buttons', {'rows': 2, 'cols': 3})
        lit = config.get('litButtons', {'rows': 2, 'cols': 4})

        self._setPageCount(int(config.get('pages', 2)))

        imageCaps = dict(self.IMAGE_BUTTON_CAPS)
        imageCaps['output'] = dict(imageCaps['output'], image=imageSize)
        self.imageButtonShape = (int(buttons['rows']), int(buttons['cols']))
        self._addControlBlock(
            'button',
            imageCaps,
            keys=[
                ('img', row, col)
                for row in range(self.imageButtonShape[0])
                for col in range(self.imageButtonShape[1])
            ],
            shape=self.imageButtonShape,
        )

        self.litButtonShape = (int(lit['rows']), int(lit['cols']))
        self._addControlBlock(
            'button',
            self.LIT_BUTTON_CAPS,
            keys=[
                ('lit', row, col)
                for row in range(self.litButtonShape[0])
                for col in range(self.litButtonShape[1])
            ],
            shape=self.litButtonShape,
        )

        self._addControlBlock(
            'dial', self.RELATIVE_DIAL_CAPS, keys=['jog'], names={'jog': 'Jog wheel'}, grid=False
        )
        self._addControlBlock(
            'dial', self.ABSOLUTE_DIAL_CAPS, keys=['fader'], names={'fader': 'Fader'}, grid=False
        )

    # --- event injection --------------------------------------------------------------

    def mockPress(self, type='button', key=None, page=None):
        """Pretend the user pressed a control. Safe to call from any thread."""
        self._handleEvent(type, key, 'press', page=page)

    def mockRelease(self, type='button', key=None, page=None):
        """Pretend the user released a control. Safe to call from any thread."""
        self._handleEvent(type, key, 'release', page=page)

    def mockMove(self, type='dial', key=None, value=0, page=None):
        """Pretend the user moved a dial.

        *value* is a delta for the relative dial and an absolute position for the absolute
        one. Safe to call from any thread.
        """
        self._handleEvent(type, key, 'move', value=value, page=page)

    def mockTouch(self, type='button', key=None, value=None, page=None):
        """Pretend the user touched a control. Safe to call from any thread."""
        self._handleEvent(type, key, 'touch', value=value, page=page)

    # --- write recording --------------------------------------------------------------

    def writesFor(self, control: Control) -> list[dict]:
        """Return the recorded writes for *control*, in order."""
        return [w for w in self.writes if w['control'] is control]

    def clearWrites(self):
        """Forget all recorded writes."""
        self.writes = []

    def _writeColor(self, control: MockControl, color: Qt.QColor):
        self.writes.append({'op': 'color', 'control': control, 'color': color})

    def _writeText(self, control: MockControl, text, color, background):
        self.writes.append(
            {
                'op': 'text',
                'control': control,
                'text': text,
                'color': color,
                'background': background,
            }
        )

    def _writeImage(self, control: MockControl, image):
        self.writes.append({'op': 'image', 'control': control, 'image': image})

    def _writeClear(self, control: MockControl):
        self.writes.append({'op': 'clear', 'control': control})

    # --- device rack UI ---------------------------------------------------------------

    def deviceInterface(self, win) -> MockControlSurfaceInterface:
        return MockControlSurfaceInterface(self)


class MockControlSurfaceInterface(Qt.QWidget):
    """Device-rack widget for driving a :class:`MockControlSurface` by hand."""

    def __init__(self, dev: MockControlSurface):
        Qt.QWidget.__init__(self)
        self.dev = dev
        layout = Qt.QGridLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)

        self.pageSpin = Qt.QSpinBox()
        self.pageSpin.setRange(0, dev.pageCount() - 1)
        self.pageSpin.setPrefix('page ')
        self.pageSpin.setValue(dev.currentPage())
        self.pageSpin.valueChanged.connect(dev.setCurrentPage)
        layout.addWidget(self.pageSpin, 0, 0)

        row = 1
        for grid in dev.controlGrids(page=0):
            for (r, c), control in zip(
                [(r, c) for r in range(grid.shape[0]) for c in range(grid.shape[1])], grid.flat
            ):
                btn = Qt.QPushButton(str(control.key))
                btn.setCheckable(True)
                btn.toggled.connect(self._makeButtonHandler(control))
                layout.addWidget(btn, row + r, c)
            row += grid.shape[0]

        jogDown = Qt.QPushButton('jog -')
        jogDown.clicked.connect(lambda: self.dev.mockMove('dial', 'jog', -1))
        jogUp = Qt.QPushButton('jog +')
        jogUp.clicked.connect(lambda: self.dev.mockMove('dial', 'jog', 1))
        layout.addWidget(jogDown, row, 0)
        layout.addWidget(jogUp, row, 1)

        caps = dev.getControl('dial', 0, 'fader').capabilities()['input']
        self.fader = Qt.QSlider(Qt.Qt.Horizontal)
        self.fader.setRange(int(caps['min']), int(caps['max']))
        self.fader.valueChanged.connect(lambda v: self.dev.mockMove('dial', 'fader', v))
        layout.addWidget(self.fader, row + 1, 0, 1, 4)

    def _makeButtonHandler(self, control: Control):
        def handler(checked, control=control):
            if checked:
                self.dev.mockPress(control.type, control.key)
            else:
                self.dev.mockRelease(control.type, control.key)

        return handler
