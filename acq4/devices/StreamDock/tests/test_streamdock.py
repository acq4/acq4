"""Event routing and appearance replay for the Stream Dock surface.

No hardware, no VSD Craft and no profile on disk: the device is constructed with its
startup thread stubbed out, then driven through the same entry point a real connection
uses -- ``_onMessage`` with a JSON string -- against a fake websocket that records what
gets sent back. Control signals arrive over a queued connection, so tests pump the Qt
event loop after injecting an event.
"""

from __future__ import annotations

import base64
import json
import time
from unittest.mock import MagicMock

import pyqtgraph as pg
import pytest

from acq4.devices.StreamDock import profile, render
from acq4.devices.StreamDock.streamdock import StreamDock
from acq4.util import Qt

BUTTON_ACTION = f'{profile.PLUGIN_UUID}.button'
KNOB_ACTION = f'{profile.PLUGIN_UUID}.knob'


def pump(iterations=3):
    """Deliver queued Qt events so that control signals arrive."""
    for _ in range(iterations):
        Qt.QApplication.processEvents()


def pumpUntil(predicate, timeout=5.0):
    """Pump the event loop until *predicate* is true or *timeout* elapses."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        Qt.QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


class FakeWebSocket:
    """Stands in for ``websocket.WebSocketApp``, recording everything sent to it."""

    def __init__(self):
        self.sent = []

    def send(self, raw):
        self.sent.append(json.loads(raw))

    def close(self):
        pass

    def eventsFor(self, event=None):
        return [m for m in self.sent if event is None or m['event'] == event]


def willAppear(context, role, page, row, col, generator=profile.GENERATOR_TAG):
    """One ``willAppear``, carrying the identity the profile generator baked in.

    ``willAppear`` reports no page or profile id of its own, and the order keys appear in
    follows whichever page the user opened first, so this is the only reproducible address.
    """
    return {
        'event': 'willAppear',
        'action': BUTTON_ACTION if role == 'button' else KNOB_ACTION,
        'context': context,
        'device': 'VSDN4Pro',
        'payload': {
            'controller': 'Keypad' if role == 'button' else 'Knob',
            'coordinates': {'column': col, 'row': row},
            'settings': {
                'generator': generator,
                'pageId': f'PAGE{page}',
                'pageLabel': f'acq4 {page + 1}',
                'pageIndex': page,
                'role': role,
                'row': row,
                'column': col,
            },
            'state': 0,
        },
    }


def hardwareEvent(event, context, **payload):
    return {'event': event, 'context': context, 'payload': payload}


def decodeImage(payload: str) -> Qt.QImage:
    """Decode a ``setImage`` payload back into the image the panel would show."""
    assert payload.startswith('data:image/png;base64,')
    image = Qt.QImage()
    assert image.loadFromData(base64.b64decode(payload.split(',', 1)[1]))
    return image


def ink(image: Qt.QImage, background='k') -> set:
    """Return the pixels of *image* that are not *background*: the label itself.

    Comparing these is how these tests ask whether two keys show the same text in the same
    place at the same size, without caring what colour either of them is.
    """
    rgb = pg.mkColor(background).rgb()
    return {
        (x, y)
        for y in range(image.height())
        for x in range(image.width())
        if image.pixel(x, y) != rgb
    }


@pytest.fixture
def offline(tmp_path, monkeypatch):
    """Keep construction away from this machine's Stream Dock installation.

    Stubbing ``_startup`` is what keeps these tests off the real machine -- it is the only
    code path that installs the plugin, rewrites a profile or cycles VSD Craft -- and
    pointing the two files ``__init__`` itself reads at empty temp paths makes the
    geometry check a no-op instead of machine-dependent.
    """
    monkeypatch.setattr(StreamDock, '_startup', lambda self: None)
    monkeypatch.setattr(profile, 'CONFIG_INI', tmp_path / 'absent.ini')
    monkeypatch.setattr(profile, 'WS_META_FILE', tmp_path / 'absent.json')


def makeDock(config=None, name='Dock'):
    """Construct a StreamDock wired to a fake websocket. Requires the *offline* fixture."""
    dev = StreamDock(
        MagicMock(),
        (
            {'pages': 2, 'buttons': {'rows': 2, 'cols': 5}, 'dials': {'rows': 1, 'cols': 3}}
            if config is None
            else config
        ),
        name,
    )
    dev.socket = FakeWebSocket()
    dev._ws = dev.socket
    dev._connected.set()
    dev._queueReady.set()
    return dev


@pytest.fixture
def dock(qapp, offline):
    dev = makeDock()
    try:
        yield dev
    finally:
        dev.quit()


def connect(control):
    """Record every signal *control* emits, as ``(name, value)`` pairs."""
    events = []
    control.sigPressed.connect(lambda ctl: events.append(('press', None)))
    control.sigReleased.connect(lambda ctl: events.append(('release', None)))
    control.sigMoved.connect(lambda ctl, value: events.append(('move', value)))
    control.sigTouched.connect(lambda ctl, value: events.append(('touch', value)))
    return events


def feed(dock, *messages):
    """Push messages through the same entry point the websocket callback uses."""
    for message in messages:
        dock._onMessage(dock._ws, json.dumps(message))


# ------------------------------------------------------------------------------ layout


class TestLayout:
    def test_blocks_and_pages_come_from_config(self, dock):
        assert dock.pageCount() == 2
        assert dock.pageNames() == ['acq4 1', 'acq4 2']
        assert [g.shape for g in dock.controlGrids(page=0)] == [(2, 5), (1, 3)]
        controls = dock.controls(page=0)
        assert len(controls['button']) == 10
        assert len(controls['dial']) == 3

    def test_configured_page_count_builds_controls_on_every_page(self, qapp, offline):
        dev = makeDock(
            {'pages': 3, 'buttons': {'rows': 2, 'cols': 5}, 'dials': {'rows': 1, 'cols': 3}}
        )
        try:
            assert dev.pageCount() == 3
            assert dev.pageNames() == ['acq4 1', 'acq4 2', 'acq4 3']
            page0 = {(c.type, c.key) for c in dev.allControls(page=0)}
            assert len(page0) == 2 * 5 + 1 * 3  # every button, plus every dial
            for page in range(3):
                assert [g.shape for g in dev.controlGrids(page=page)] == [(2, 5), (1, 3)]
                assert {(c.type, c.key) for c in dev.allControls(page=page)} == page0
                assert all(c.page == page for c in dev.allControls(page=page))
        finally:
            dev.quit()

    def test_key_is_addressed_within_its_own_block(self, dock):
        # button (0, 0) is the first button, not panel row 0, which holds the dials
        assert dock.getControl('button', 0, (0, 0)).type == 'button'
        assert dock.getControl('dial', 0, (0, 0)).type == 'dial'
        with pytest.raises(KeyError):
            dock.getControl('dial', 0, (1, 0))

    def test_capabilities(self, dock):
        button = dock.getControl('button', 0, (0, 0)).capabilities()
        assert button['input'] == {'press': True}
        assert button['output']['image'] == (72, 72)
        assert button['output']['text'] is True
        # 'output' is this device's own vocabulary and says nothing about a light, because
        # a key has none: setColor fills the display
        assert 'color' not in button['output']

        dial = dock.getControl('dial', 0, (0, 0)).capabilities()
        assert dial['input']['mode'] == 'relative'
        assert dial['input']['press'] is True
        assert dial['output']['image'] == (200, 100)
        assert not {'min', 'max', 'flat'} & set(dial['input'])

    def test_the_display_api_lives_on_this_surface_not_the_base_class(self, dock):
        from acq4.devices.ControlSurface import Control
        from acq4.devices.StreamDock.streamdock import StreamDockControl

        control = dock.getControl('button', 0, (0, 0))
        assert isinstance(control, StreamDockControl)
        for name in ('setImage', 'setText', 'setColor', 'clear', 'setAnimation'):
            assert hasattr(control, name), name
            assert not hasattr(Control, name), name
        # and nothing pretends a key has an LED pair to switch
        assert not hasattr(control, 'setBacklight')

    def test_hardware_pages(self, dock):
        assert dock._hardwarePages is True

    def test_an_empty_block_is_not_declared(self, qapp, offline):
        dev = makeDock({'dials': {'rows': 0, 'cols': 0}}, 'NoKnobs')
        try:
            assert [g.shape for g in dev.controlGrids(page=0)] == [(2, 5)]
            assert 'dial' not in dev.controls(page=0)
        finally:
            dev.quit()

    def test_zero_pages_is_rejected(self, qapp, offline):
        with pytest.raises(ValueError, match='pages'):
            makeDock({'pages': 0})

    def test_a_layout_larger_than_the_panel_is_a_startup_error(
        self, qapp, offline, tmp_path, monkeypatch
    ):
        ini = tmp_path / 'StreamDockConfig.ini'
        ini.write_text(
            '[StreamDockCurrentDevice]\nDevice=VSDN4Pro\n\n'
            '[VSDN4ProDeviceConfig]\nDeviceUUID=VSDN4Pro\nsdProfileName=p.sdProfile\n',
            encoding='utf-8',
        )
        meta = tmp_path / 'ws-meta.json'
        meta.write_text(
            json.dumps(
                {'info': {'devices': [{'name': 'VSDN4Pro', 'size': {'columns': 5, 'rows': 3}}]}}
            ),
            encoding='utf-8',
        )
        monkeypatch.setattr(profile, 'CONFIG_INI', ini)
        monkeypatch.setattr(profile, 'WS_META_FILE', meta)

        with pytest.raises(profile.ProfileError, match='VSDN4Pro is 3x5'):
            makeDock({'buttons': {'rows': 3, 'cols': 5}, 'dials': {'rows': 1, 'cols': 3}})


# ----------------------------------------------------------------------- event routing


class TestEventRouting:
    def test_scripted_stream_reaches_the_right_controls(self, dock):
        button = connect(dock.getControl('button', 0, (1, 2)))
        dial = connect(dock.getControl('dial', 0, (0, 1)))

        feed(
            dock,
            willAppear('ctx-btn', 'button', 0, 1, 2),
            willAppear('ctx-dial', 'dial', 0, 0, 1),
            hardwareEvent('keyDown', 'ctx-btn'),
            hardwareEvent('keyUp', 'ctx-btn'),
            hardwareEvent('dialRotate', 'ctx-dial', ticks=3),
            hardwareEvent('dialRotate', 'ctx-dial', ticks=-2),
            hardwareEvent('dialDown', 'ctx-dial'),
            hardwareEvent('dialUp', 'ctx-dial'),
        )
        pump()

        assert button == [('press', None), ('release', None)]
        assert dial == [('move', 3), ('move', -2), ('press', None), ('release', None)]

    def test_events_carry_the_page_they_came_from(self, dock):
        page0 = connect(dock.getControl('button', 0, (0, 0)))
        page1 = connect(dock.getControl('button', 1, (0, 0)))

        feed(
            dock,
            willAppear('ctx-p0', 'button', 0, 0, 0),
            willAppear('ctx-p1', 'button', 1, 0, 0),
            hardwareEvent('keyDown', 'ctx-p1'),
            hardwareEvent('keyDown', 'ctx-p0'),
        )
        pump()

        # the same (type, key) on two pages stays two distinct controls -- the failure mode
        # the old first-come context assignment had
        assert page1 == [('press', None)]
        assert page0 == [('press', None)]

    def test_dial_press_uses_dialdown_not_dialpress(self, dock):
        dial = connect(dock.getControl('dial', 0, (0, 0)))
        feed(
            dock,
            willAppear('ctx', 'dial', 0, 0, 0),
            # the names the old code listened for, which the hardware never sends
            hardwareEvent('dialPress', 'ctx'),
            hardwareEvent('dialRelease', 'ctx'),
        )
        pump()
        assert dial == []

        feed(dock, hardwareEvent('dialDown', 'ctx'), hardwareEvent('dialUp', 'ctx'))
        pump()
        assert dial == [('press', None), ('release', None)]

    def test_zero_tick_rotation_is_dropped(self, dock):
        dial = connect(dock.getControl('dial', 0, (0, 0)))
        feed(
            dock,
            willAppear('ctx', 'dial', 0, 0, 0),
            hardwareEvent('dialRotate', 'ctx', ticks=0),
            hardwareEvent('dialRotate', 'ctx'),
        )
        pump()
        assert dial == []

    def test_touch_tap_carries_its_position(self, dock):
        button = connect(dock.getControl('button', 0, (0, 0)))
        feed(
            dock,
            willAppear('ctx', 'button', 0, 0, 0),
            hardwareEvent('touchTap', 'ctx', tapPos=[10, 20]),
        )
        pump()
        assert button == [('touch', [10, 20])]

    def test_willdisappear_unbinds(self, dock):
        button = connect(dock.getControl('button', 0, (0, 0)))
        feed(dock, willAppear('ctx', 'button', 0, 0, 0))
        feed(dock, {'event': 'willDisappear', 'context': 'ctx', 'payload': {}})
        feed(dock, hardwareEvent('keyDown', 'ctx'))
        pump()
        assert button == []

    def test_hand_placed_keys_are_ignored(self, dock):
        button = connect(dock.getControl('button', 0, (0, 0)))
        feed(
            dock,
            # a key the user placed in VSD Craft: empty Settings, no generator tag
            {
                'event': 'willAppear',
                'action': BUTTON_ACTION,
                'context': 'ctx-manual',
                'payload': {'coordinates': {'column': 0, 'row': 1}, 'settings': {}},
            },
            hardwareEvent('keyDown', 'ctx-manual'),
        )
        pump()
        assert button == []

    def test_a_stale_profile_address_is_reported_not_raised(self, dock, caplog):
        with caplog.at_level('WARNING'):
            feed(dock, willAppear('ctx', 'button', 0, 9, 9))
            feed(dock, hardwareEvent('keyDown', 'ctx'))
            pump()
        assert 'stale' in caplog.text

    def test_settings_from_an_older_generator_spelling_still_bind(self, dock):
        # 'knob' was the role name the demo generator wrote for a rotary control
        dial = connect(dock.getControl('dial', 0, (0, 2)))
        feed(dock, willAppear('ctx', 'knob', 0, 0, 2))
        feed(dock, hardwareEvent('dialRotate', 'ctx', ticks=1))
        pump()
        assert dial == [('move', 1)]

    def test_routine_events_are_not_warned_about(self, dock, caplog):
        with caplog.at_level('WARNING'):
            feed(
                dock,
                willAppear('ctx', 'button', 0, 0, 0),
                {'event': 'titleParametersDidChange', 'context': 'ctx', 'payload': {}},
                {'event': 'deviceDidConnect', 'device': 'VSDN4Pro'},
                {'event': 'didReceiveSettings', 'context': 'ctx', 'payload': {}},
            )
            pump()
        assert caplog.text == ''

    def test_non_json_is_logged_not_raised(self, dock, caplog):
        with caplog.at_level('WARNING'):
            dock._onMessage(dock._ws, 'not json at all')
        assert 'Non-JSON' in caplog.text

    def test_signals_are_emitted_on_the_gui_thread(self, dock):
        control = dock.getControl('button', 0, (0, 0))
        threads = []
        control.sigPressed.connect(lambda ctl: threads.append(Qt.QThread.currentThread()))
        feed(dock, willAppear('ctx', 'button', 0, 0, 0), hardwareEvent('keyDown', 'ctx'))
        assert threads == []  # queued, not delivered inline on the websocket thread
        pump()
        assert threads == [Qt.QThread.currentThread()]


class TestPageSwitching:
    """VSD Craft has no page-change command, so the generic setter must refuse."""

    def test_the_surface_reports_that_it_cannot_set_the_page(self, dock):
        assert dock.canSetCurrentPage() is False

    def test_setcurrentpage_raises_rather_than_restarting_vsd_craft(self, dock, monkeypatch):
        touched = []
        for name in ('write_json', 'stop_vsd_craft', 'launch_vsd_craft'):
            monkeypatch.setattr(profile, name, lambda *a, _n=name, **k: touched.append(_n))
        with pytest.raises(NotImplementedError, match='change page'):
            dock.setCurrentPage(1)
        assert touched == []  # nothing touched the profile or the application

    def test_a_refused_switch_leaves_the_reported_page_alone(self, dock):
        changed = []
        dock.sigPageChanged.connect(lambda dev, page: changed.append(page))
        with pytest.raises(NotImplementedError):
            dock.setCurrentPage(1)
        pump(5)
        assert dock.currentPage() == 0  # still whatever the hardware last reported
        assert changed == []  # and no signal claiming otherwise

    def test_an_invalid_page_is_rejected_before_the_capability_check(self, dock):
        with pytest.raises(IndexError):
            dock.setCurrentPage(99)


class TestPageReporting:
    def test_a_willappear_from_another_page_reports_the_page_change(self, dock):
        changed = []
        dock.sigPageChanged.connect(lambda dev, page: changed.append(page))
        feed(dock, willAppear('ctx', 'button', 1, 0, 0))
        assert pumpUntil(lambda: changed == [1])
        assert dock.currentPage() == 1

    def test_no_page_change_is_reported_for_the_current_page(self, dock):
        changed = []
        dock.sigPageChanged.connect(lambda dev, page: changed.append(page))
        feed(dock, willAppear('ctx', 'button', 0, 0, 0))
        pump(5)
        assert changed == []


# -------------------------------------------------------------------------- appearance


class TestAppearance:
    def test_image_is_sent_as_a_png_data_uri(self, dock):
        control = dock.getControl('button', 0, (0, 0))
        feed(dock, willAppear('ctx', 'button', 0, 0, 0))
        image = Qt.QImage(72, 72, Qt.QImage.Format_ARGB32)
        image.fill(Qt.QColor('r'))
        control.setImage(image)

        assert pumpUntil(lambda: dock.socket.eventsFor('setImage'))
        message = dock.socket.eventsFor('setImage')[-1]
        assert message['context'] == 'ctx'
        assert message['payload']['image'].startswith('data:image/png;base64,')
        assert message['payload']['target'] == 0

    def test_an_image_is_scaled_to_the_control_size(self, dock):
        control = dock.getControl('dial', 0, (0, 0))
        feed(dock, willAppear('ctx', 'dial', 0, 0, 0))
        control.setImage(Qt.QImage(10, 10, Qt.QImage.Format_ARGB32))

        assert pumpUntil(lambda: dock.socket.eventsFor('setImage'))
        payload = dock.socket.eventsFor('setImage')[-1]['payload']['image']
        decoded = decodeImage(payload)
        assert (decoded.width(), decoded.height()) == (200, 100)

    def test_a_label_is_drawn_by_acq4_rather_than_by_the_panel(self, dock):
        # setTitle would be a shorter message, but the panel firmware draws a title at
        # its own fixed size: a label acq4 has not drawn is a label acq4 cannot size
        control = dock.getControl('button', 0, (0, 0))
        feed(dock, willAppear('ctx', 'button', 0, 0, 0))
        control.setText('Seal')

        assert pumpUntil(lambda: dock.socket.eventsFor('setImage'))
        assert dock.socket.eventsFor('setTitle') == []

    def test_a_label_looks_the_same_highlighted_as_unhighlighted(self, dock):
        # the reason every label is drawn: a key used to change the size and shape of its
        # text the moment a consumer highlighted it with a background colour
        control = dock.getControl('button', 0, (0, 0))
        feed(dock, willAppear('ctx', 'button', 0, 0, 0))

        control.setText('aboveTarget')
        assert pumpUntil(lambda: dock.socket.eventsFor('setImage'))
        pump(5)  # and let the repaint that follows willAppear settle
        plain = decodeImage(dock.socket.eventsFor('setImage')[-1]['payload']['image'])

        drawn = len(dock.socket.eventsFor('setImage'))
        control.setText('aboveTarget', color='k', background='y')
        assert pumpUntil(lambda: len(dock.socket.eventsFor('setImage')) > drawn)
        lit = decodeImage(dock.socket.eventsFor('setImage')[-1]['payload']['image'])

        # the same glyphs in the same places at the same size; only the colours differ
        assert ink(plain, 'k') == ink(lit, 'y')
        assert dock.socket.eventsFor('setTitle') == []

    def test_a_long_single_word_is_drawn_at_the_standard_size(self, dock):
        # 'aboveTarget' has no space to wrap at, so fitting it on width alone drew it at
        # 8pt on one line; broken at its camelCase seam it reaches the standard size that
        # every other label on the panel is drawn at
        control = dock.getControl('button', 0, (0, 0))
        feed(dock, willAppear('ctx', 'button', 0, 0, 0))
        control.setText('aboveTarget')

        assert pumpUntil(lambda: dock.socket.eventsFor('setImage'))
        drawn = decodeImage(dock.socket.eventsFor('setImage')[-1]['payload']['image'])
        assert ink(drawn) == ink(render.renderTextImage('aboveTarget', render.KEY_SIZE))
        assert render.fitText('aboveTarget', render.KEY_SIZE).pointSize == (
            render.standardPointSize(render.KEY_SIZE)
        )

    def test_a_control_with_no_display_falls_back_to_the_native_title(self, dock):
        # nothing acq4 supports is like this, but the capability dictionary allows it,
        # and a title at the firmware's own size beats no label at all
        control = dock.getControl('button', 0, (0, 0))
        control._capabilities = {'input': {'press': True}, 'output': {'text': True}}
        feed(dock, willAppear('ctx', 'button', 0, 0, 0))
        control.setText('Seal')

        assert pumpUntil(lambda: dock.socket.eventsFor('setTitle'))
        assert dock.socket.eventsFor('setTitle')[-1]['payload']['title'] == 'Seal'
        assert dock.socket.eventsFor('setImage') == []

    def test_a_label_costs_one_small_image_per_write(self, dock):
        # drawing every label is more traffic than a title string, but not much of it: a
        # key label is about a kilobyte and a knob strip a few, so the 4 Hz repaint a
        # Stage axis readout does is tens of kB/s on a loopback socket
        button = dock.getControl('button', 0, (0, 0))
        dial = dock.getControl('dial', 0, (0, 0))
        feed(dock, willAppear('ctx-b', 'button', 0, 0, 0), willAppear('ctx-d', 'dial', 0, 0, 0))
        button.setText('aboveTarget', background='b')
        dial.setText('X\n-12.345 mm')

        assert pumpUntil(lambda: len(dock.socket.eventsFor('setImage')) >= 2)
        sent = {m['context']: m['payload']['image'] for m in dock.socket.eventsFor('setImage')}
        assert len(sent['ctx-b']) < 4096
        assert len(sent['ctx-d']) < 8192

    def test_setcolor_renders_a_solid_image(self, dock):
        control = dock.getControl('button', 0, (0, 0))
        feed(dock, willAppear('ctx', 'button', 0, 0, 0))
        control.setColor('g')
        assert pumpUntil(lambda: dock.socket.eventsFor('setImage'))

    def test_clear_blanks_both_image_and_title(self, dock):
        control = dock.getControl('button', 0, (0, 0))
        feed(dock, willAppear('ctx', 'button', 0, 0, 0))
        control.setText('Seal')
        assert pumpUntil(lambda: dock.socket.eventsFor('setImage'))
        control.clear()
        # the title is blanked as well, even though labels no longer use it: a profile or
        # a hand-built page can have left one on the key
        assert pumpUntil(
            lambda: dock.socket.eventsFor('setTitle')
            and dock.socket.eventsFor('setTitle')[-1]['payload']['title'] == ''
        )
        blanked = decodeImage(dock.socket.eventsFor('setImage')[-1]['payload']['image'])
        assert ink(blanked) == set()

    def test_writes_to_an_unbound_address_are_only_cached(self, dock):
        control = dock.getControl('button', 0, (0, 0))
        control.setText('Seal')  # nothing has appeared, so there is no context to send to
        pump(5)
        assert dock.socket.sent == []
        assert control.cachedAppearance() == (
            'text',
            {'text': 'Seal', 'color': None, 'background': None},
        )

    def test_queued_messages_coalesce_per_kind(self, dock):
        control = dock.getControl('button', 0, (0, 0))
        feed(dock, willAppear('ctx', 'button', 0, 0, 0))
        dock._connected.clear()  # freeze the sender so the queue can be inspected
        for text in ('a', 'b', 'c'):
            control.setText(text)
        assert dock.backlog() == 1
        dock._connected.set()
        dock._queueReady.set()
        assert pumpUntil(lambda: dock.socket.eventsFor('setImage'))
        drawn = decodeImage(dock.socket.eventsFor('setImage')[-1]['payload']['image'])
        assert ink(drawn) == ink(render.renderTextImage('c', render.KEY_SIZE))

    def test_animation_frames_are_skipped_while_the_queue_is_busy(self, dock):
        control = dock.getControl('button', 0, (0, 0))
        feed(dock, willAppear('ctx', 'button', 0, 0, 0))
        frames = []
        for color in ('r', 'g'):
            frame = Qt.QImage(72, 72, Qt.QImage.Format_ARGB32)
            frame.fill(Qt.QColor(color))
            frames.append(frame)
        control.setAnimation(frames, 0.01)
        assert pumpUntil(lambda: len(dock.socket.eventsFor('setImage')) >= 2, timeout=3.0)

        dock._connected.clear()
        control.setText('busy')
        assert dock.backlog() == 1
        before = len(dock.socket.sent)
        dock._animationTick()
        assert len(dock.socket.sent) == before  # the frame was dropped, not queued
        control.stopAnimation()


class TestReplayOnReappearance:
    def test_appearance_is_replayed_when_an_address_comes_back(self, dock):
        control = dock.getControl('button', 0, (0, 0))
        feed(dock, willAppear('ctx-1', 'button', 0, 0, 0))
        control.setText('Seal')
        assert pumpUntil(lambda: dock.socket.eventsFor('setImage'))

        # VSD Craft restarts: every context dies, the Control and its cache do not
        dock._onDisconnected()
        assert dock._addressByContext == {}
        dock.socket = FakeWebSocket()
        dock._ws = dock.socket
        dock._connected.set()

        # the same control reappears under a brand new context
        feed(dock, willAppear('ctx-2', 'button', 0, 0, 0))
        assert pumpUntil(lambda: dock.socket.eventsFor('setImage'))
        message = dock.socket.eventsFor('setImage')[-1]
        assert message['context'] == 'ctx-2'
        drawn = decodeImage(message['payload']['image'])
        assert ink(drawn) == ink(render.renderTextImage('Seal', render.KEY_SIZE))

    def test_nothing_is_replayed_for_a_control_never_drawn_on(self, dock):
        feed(dock, willAppear('ctx', 'button', 0, 0, 0))
        pump(5)
        assert dock.socket.sent == []

    def test_an_animation_resumes_after_a_reconnect(self, dock):
        control = dock.getControl('button', 0, (0, 0))
        feed(dock, willAppear('ctx-1', 'button', 0, 0, 0))
        frame = Qt.QImage(72, 72, Qt.QImage.Format_ARGB32)
        frame.fill(Qt.QColor('b'))
        control.setAnimation([frame], 0.01)
        assert pumpUntil(lambda: dock.socket.eventsFor('setImage'))

        dock._onDisconnected()
        dock.socket = FakeWebSocket()
        dock._ws = dock.socket
        dock._connected.set()
        feed(dock, willAppear('ctx-2', 'button', 0, 0, 0))
        assert pumpUntil(lambda: dock.socket.eventsFor('setImage'), timeout=3.0)
        control.stopAnimation()


# ------------------------------------------------------------------------- link health
#
# A registration VSD Craft accepts and then ignores is the one fault that looks entirely
# healthy from inside acq4: the socket is open, the send queue drains, and every
# appearance is discarded for want of a context. These cover the two things that make it
# visible -- the watchdog that drops such a session, and the warning when a draw for a key
# on the visible page has nowhere to go.


class RecordingLogger:
    """Collects log calls so a test can assert what was reported, and at what level."""

    def __init__(self):
        self.records = []

    def __getattr__(self, level):
        def record(message, *args, **kwds):
            self.records.append((level, str(message)))

        return record

    def at(self, level):
        return [message for name, message in self.records if name == level]


@pytest.fixture
def logged(dock):
    """Replace the device's logger with a recorder."""
    recorder = RecordingLogger()
    dock.logger = recorder
    return recorder


def bind(dock, context, role, page, row, col):
    """Bring one control onto the panel, the way a real willAppear would."""
    feed(dock, willAppear(context, role, page, row, col))
    pump()


def test_watchdog_drops_a_session_that_reports_no_keys(dock, logged):
    """No willAppear means nothing acq4 draws can arrive, so the link is not worth keeping."""
    closed = []
    dock._ws.close = lambda: closed.append(True)

    dock._checkBindings('SESSION-UUID')

    assert dock._staleSession is True
    assert closed == [True]
    assert any('reported none of' in m for m in logged.at('error'))


def test_watchdog_leaves_a_working_session_alone(dock, logged):
    closed = []
    dock._ws.close = lambda: closed.append(True)
    bind(dock, 'ctx-a', 'button', 0, 0, 0)

    dock._checkBindings('SESSION-UUID')

    assert dock._staleSession is False
    assert closed == []
    assert logged.at('error') == []


def test_watchdog_is_silent_once_disconnected(dock, logged):
    """The connect loop is already handling it; a second complaint adds nothing."""
    dock._connected.clear()
    dock._checkBindings('SESSION-UUID')
    assert dock._staleSession is False
    assert logged.at('error') == []


def test_disconnect_cancels_the_watchdog(dock):
    """Otherwise it fires against the next session and drops a healthy one."""
    dock._startBindingWatchdog('SESSION-UUID')
    timer = dock._bindingTimer
    assert timer is not None
    dock._onDisconnected()
    assert dock._bindingTimer is None
    assert not timer.is_alive() or timer.finished.is_set()


def test_undeliverable_draw_on_the_visible_page_warns(dock, logged):
    """The silence that hid this: an unbound visible key used to drop its image quietly."""
    control = dock.getControl('button', 0, (0, 0))
    control.setText('clean')
    pump()

    assert dock.backlog() == 0  # nothing was queued -- there was nowhere to send it
    warnings = logged.at('warning')
    assert any('never reported it' in m for m in warnings), warnings


def test_undeliverable_draw_is_rate_limited(dock, logged):
    """A Stage axis readout repaints at 4 Hz; one warning per fault, not per frame."""
    control = dock.getControl('button', 0, (0, 0))
    for _ in range(20):
        control.setText('x')
        pump()
    assert len(logged.at('warning')) == 1


def test_draw_for_an_unseen_page_is_not_a_fault(dock, logged):
    """Page 1 is not on the panel, so its keys have no context by design."""
    assert dock.currentPage() == 0
    dock.getControl('button', 1, (0, 0)).setText('later')
    pump()
    assert logged.at('warning') == []


def test_bound_control_draws_without_warning(dock, logged):
    bind(dock, 'ctx-a', 'button', 0, 0, 0)
    dock.getControl('button', 0, (0, 0)).setText('clean')
    pump()
    assert logged.at('warning') == []
    assert pumpUntil(lambda: dock.socket.eventsFor('setImage'))


def test_session_report_surfaces_bridge_problems_once(dock, logged):
    """bootstrap.js writes its failures into the file because its console goes nowhere."""
    meta = {
        'ws': 'ws://127.0.0.1:18618',
        'pluginUUID': 'SESSION-A',
        'reaped': [526112],
        'errors': ['could not kill bridge pid 999: Access is denied'],
    }
    dock._reportSession(meta, 'SESSION-A')
    dock._reportSession(meta, 'SESSION-A')

    assert len(logged.at('warning')) == 1
    assert 'could not kill bridge pid 999' in logged.at('warning')[0]
    assert any('cleared 1 stale predecessor' in m for m in logged.at('info'))

    dock._reportSession(meta, 'SESSION-B')
    assert len(logged.at('warning')) == 2


def test_recovery_restarts_vsd_craft_and_waits_for_the_new_bridge(dock, logged, monkeypatch):
    calls = []
    monkeypatch.setattr(profile, 'restart_vsd_craft', lambda: calls.append('restart'))
    monkeypatch.setattr(profile, 'wait_for_plugin', lambda newer_than=0.0: True)

    dock._recoverSession('no keys were reported')

    assert calls == ['restart']
    assert any('Restarting VSD Craft' in m for m in logged.at('warning'))


def test_recovery_is_rate_limited(dock, logged, monkeypatch):
    """A fault this cannot fix must not turn into a VSD Craft restart loop."""
    calls = []
    monkeypatch.setattr(profile, 'restart_vsd_craft', lambda: calls.append('restart'))
    monkeypatch.setattr(profile, 'wait_for_plugin', lambda newer_than=0.0: True)

    dock._recoverSession('first')
    dock._recoverSession('second')

    assert calls == ['restart']


def test_recovery_reports_a_restart_that_did_not_help(dock, logged, monkeypatch):
    """Silence here would leave a blank panel and no explanation."""
    monkeypatch.setattr(profile, 'restart_vsd_craft', lambda: None)
    monkeypatch.setattr(profile, 'wait_for_plugin', lambda newer_than=0.0: False)

    dock._recoverSession('no keys were reported')

    assert any('no ACQ4 bridge republished' in m for m in logged.at('error'))


def test_recovery_reports_a_restart_it_could_not_perform(dock, logged, monkeypatch):
    def boom():
        raise RuntimeError('VSD Craft would not close')

    monkeypatch.setattr(profile, 'restart_vsd_craft', boom)
    dock._recoverSession('no keys were reported')
    assert any('Could not restart VSD Craft' in m for _, m in logged.records)
