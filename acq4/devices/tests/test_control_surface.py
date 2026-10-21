"""Tests for the device-agnostic control-surface abstraction.

Everything here runs headless against ``MockControlSurface``; no hardware and no real
Manager are involved. Control signals are delivered over a queued connection, so tests
pump the Qt event loop with :func:`pump` after injecting an event.

The base class declares no output API, so nothing here tests one. What it does test is the
machinery every surface's output rides on: the opaque appearance cache, ``_write<Op>``
dispatch, page suppression and repaint, and the :meth:`Control._blank` hook. The mock's own
output vocabulary (``setColor``/``setText``/``setImage``/``clear``) stands in for a real
surface's, and exists only to drive that machinery.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pyqtgraph as pg
import pytest

from acq4.devices.ControlSurface import (
    Control,
    ControlInUse,
    ControlSurface,
    UnsupportedControlFeature,
    acquireControlFromConfig,
    parseControlConfig,
)
from acq4.devices.MockControlSurface import MockControlSurface, MockControlSurfaceInterface
from acq4.util import Qt

IMG_KEY = ('img', 0, 0)
LIT_KEY = ('lit', 0, 0)


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


def makeSurface(qapp, name='MockSurface', **config):
    dm = MagicMock()
    return MockControlSurface(dm, dict(config), name)


@pytest.fixture
def surface(qapp):
    return makeSurface(qapp)


class UnrestrictedSurface(MockControlSurface):
    """A mock whose lit buttons show anything asked of them.

    The restriction is a word in the block's own output vocabulary, so lifting it is a
    different declaration rather than a different method.
    """

    LIT_BUTTON_CAPS = {
        'input': {'press': True},
        'output': {'color': True},
    }


# ------------------------------------------------------------------------- enumeration


class TestEnumeration:
    def test_controls_exist_up_front_unowned_and_undrawn(self, surface):
        control = surface.getControl('button', 0, IMG_KEY)
        assert isinstance(control, Control)
        assert control.owner is None
        assert control.cachedAppearance() is None
        assert surface.writes == []

    def test_controls_grouped_by_type(self, surface):
        controls = surface.controls(page=0)
        assert set(controls) == {'button', 'dial'}
        assert sorted(controls['dial']) == ['fader', 'jog']
        # 2x3 image buttons + 2x4 lit buttons
        assert len(controls['button']) == 6 + 8

    def test_control_identity(self, surface):
        control = surface.getControl('dial', 0, 'jog')
        assert control.surface is surface
        assert (control.type, control.page, control.key) == ('dial', 0, 'jog')
        assert control.name == 'Jog wheel'

    def test_grids_are_object_arrays_of_controls(self, surface):
        grids = surface.controlGrids(page=0)
        assert [g.shape for g in grids] == [(2, 3), (2, 4)]
        assert all(g.dtype == object for g in grids)
        assert grids[0][0, 0] is surface.getControl('button', 0, IMG_KEY)
        assert grids[0][1, 2] is surface.getControl('button', 0, ('img', 1, 2))

    def test_capabilities_are_per_control_and_copied(self, surface):
        image = surface.getControl('button', 0, IMG_KEY).capabilities()
        lit = surface.getControl('button', 0, LIT_KEY).capabilities()
        assert image['output']['image'] == (72, 72)
        # the lit buttons take a colour and nothing else; 'output' is the surface's own
        # vocabulary, so a thing a control cannot do is simply absent rather than False,
        # and a restriction on what it *can* do is spelled however that surface likes
        assert 'image' not in lit['output']
        assert lit['output']['color'] == 'noGreen'
        # mutating the returned dict must not affect the control
        image['output']['image'] = None
        assert surface.getControl('button', 0, IMG_KEY).capabilities()['output']['image']

    def test_the_base_class_has_no_opinion_about_output_capabilities(self, surface):
        # any word a surface cares to use, with no validation and no blessed keys
        surface._addControlBlock(
            'button',
            {'input': {'press': True}, 'output': {'smell': 'lavender', 'rumble': 7}},
            keys=['scratch'],
        )
        caps = surface.getControl('button', 0, 'scratch').capabilities()['output']
        assert caps == {'smell': 'lavender', 'rumble': 7}

    def test_configured_geometry(self, qapp):
        surface = makeSurface(
            qapp, buttons={'rows': 2, 'cols': 5}, litButtons={'rows': 4, 'cols': 8}
        )
        assert [g.shape for g in surface.controlGrids(page=0)] == [(2, 5), (4, 8)]

    def test_unknown_address_raises_keyerror(self, surface):
        with pytest.raises(KeyError):
            surface.getControl('button', 0, ('img', 99, 99))
        with pytest.raises(KeyError):
            surface.getControl('trackball', 0, IMG_KEY)


# ------------------------------------------------------------------------- acquisition


class TestAcquisition:
    def test_acquire_records_owner(self, surface):
        owner = object()
        control = surface.acquireControl('button', 0, IMG_KEY, owner=owner)
        assert control.owner is owner
        assert surface.getControl('button', 0, IMG_KEY).owner is owner

    def test_double_acquire_raises_naming_owner(self, surface):
        class Owner:
            def __repr__(self):
                return '<TheFirstOwner>'

        first = Owner()
        surface.acquireControl('button', 0, IMG_KEY, owner=first)
        with pytest.raises(ControlInUse) as exc:
            surface.acquireControl('button', 0, IMG_KEY, owner=object())
        assert 'TheFirstOwner' in str(exc.value)
        assert exc.value.owner is first

    def test_reacquire_by_same_owner_raises(self, surface):
        """A control is claimed once, period: the owner holding it gets no second claim."""
        owner = object()
        surface.acquireControl('button', 0, IMG_KEY, owner=owner)
        with pytest.raises(ControlInUse) as exc:
            surface.acquireControl('button', 0, IMG_KEY, owner=owner)
        assert exc.value.owner is owner
        assert surface.getControl('button', 0, IMG_KEY).owner is owner

    def test_release_then_reacquire_by_same_owner_works(self, surface):
        owner = object()
        control = surface.acquireControl('button', 0, IMG_KEY, owner=owner)
        control.release()
        assert control.owner is None
        assert surface.acquireControl('button', 0, IMG_KEY, owner=owner) is control

    def test_acquire_without_an_owner_raises(self, surface):
        """Ownership is the claim, so a None owner would leave the control looking free."""
        control = surface.getControl('button', 0, IMG_KEY)
        with pytest.raises(ValueError):
            control.acquire(None)
        with pytest.raises(ValueError):
            surface.acquireControl('button', 0, IMG_KEY, owner=None)
        assert control.owner is None
        with pytest.raises(TypeError):
            surface.acquireControl('button', 0, IMG_KEY)
        assert control.owner is None

    def test_acquire_unknown_address_raises_keyerror(self, surface):
        with pytest.raises(KeyError):
            surface.acquireControl('button', 0, ('img', 9, 9), owner=object())

    def test_release_blanks_and_frees(self, surface):
        owner = object()
        control = surface.acquireControl('button', 0, LIT_KEY, owner=owner)
        control.setColor('r')
        surface.clearWrites()
        surface.releaseControl(control)
        assert control.owner is None
        assert surface.writes[-1]['op'] == 'clear'
        surface.acquireControl('button', 0, LIT_KEY, owner=object())

    def test_release_of_a_control_with_nothing_to_blank_is_quiet(self, surface):
        # the absolute dial has no output at all, so the default _blank does nothing
        control = surface.acquireControl('dial', 0, 'fader', owner=object())
        control.release()
        assert control.owner is None
        assert surface.writes == []

    def test_a_failing_blank_still_frees_the_control(self, surface, caplog):
        control = surface.acquireControl('button', 0, LIT_KEY, owner=object())
        control._blank = lambda: (_ for _ in ()).throw(RuntimeError('link died'))
        with caplog.at_level('ERROR'):
            control.release()
        assert control.owner is None
        assert 'link died' in caplog.text

    def test_release_severs_the_old_owner_from_the_control(self, surface):
        """After release(), presses reach only the next owner's slots, not the old owner's."""
        first, second = [], []
        control = surface.acquireControl('button', 0, IMG_KEY, owner=object())
        control.sigPressed.connect(lambda ctl: first.append(ctl))
        control.release()

        surface.acquireControl('button', 0, IMG_KEY, owner=object())
        control.sigPressed.connect(lambda ctl: second.append(ctl))
        surface.mockPress('button', IMG_KEY)
        pump()
        assert first == []
        assert second == [control]

    def test_release_severs_every_input_the_base_class_owns(self, surface):
        heard = []
        control = surface.acquireControl('dial', 0, 'jog', owner=object())
        control.sigPressed.connect(lambda ctl: heard.append('press'))
        control.sigReleased.connect(lambda ctl: heard.append('release'))
        control.sigMoved.connect(lambda ctl, value: heard.append('move'))
        control.sigTouched.connect(lambda ctl, value: heard.append('touch'))
        control.release()

        surface.acquireControl('dial', 0, 'jog', owner=object())
        surface.mockPress('dial', 'jog')
        surface.mockRelease('dial', 'jog')
        surface.mockMove('dial', 'jog', 3)
        surface.mockTouch('dial', 'jog', value=None)
        pump()
        assert heard == []

    def test_a_consumer_that_disconnects_for_itself_still_releases_cleanly(self, surface):
        """release() does not raise when the owner already disconnected its own slots."""
        heard = []

        def slot(ctl):
            heard.append(ctl)

        control = surface.acquireControl('button', 0, IMG_KEY, owner=object())
        control.sigPressed.connect(slot)
        control.sigPressed.disconnect(slot)
        control.release()
        assert control.owner is None

    def test_a_failing_blank_still_severs_the_old_owner(self, surface):
        heard = []
        control = surface.acquireControl('button', 0, LIT_KEY, owner=object())
        control.sigPressed.connect(lambda ctl: heard.append(ctl))
        control._blank = lambda: (_ for _ in ()).throw(RuntimeError('link died'))
        control.release()

        surface.mockPress('button', LIT_KEY)
        pump()
        assert heard == []

    def test_multipatch_grid_slicing_pattern(self, qapp):
        surface = makeSurface(qapp, litButtons={'rows': 4, 'cols': 8})
        owner = object()
        grid = surface.controlGrids(page=0)[1]
        for control in grid[:, 4:6].flat:
            control.acquire(owner)
        assert [c.owner is owner for c in grid.flat].count(True) == 8
        assert grid[0, 3].owner is None


# ------------------------------------------------------------- a surface's own output


class TestSurfaceOwnedOutput:
    """The base class declares no output, so a surface's own vocabulary is all there is.

    ``MockControl`` stands in for a real surface's control class here: what a control can
    be asked for is what its own class offers, gated by what its block declared.
    """

    def test_the_generic_control_declares_no_output_api(self):
        for name in (
            'setImage',
            'setText',
            'setColor',
            'clear',
            'hasOutput',
            'setAnimation',
            'stopAnimation',
        ):
            assert not hasattr(Control, name), f"Control should not declare {name}()"

    def test_a_surface_reaches_its_own_output_through_its_control_class(self, surface):
        control = surface.getControl('button', 0, LIT_KEY)
        assert type(control) is not Control
        control.setColor('r')
        write = surface.writesFor(control)[-1]
        assert (write['op'], write['color']) == ('color', pg.mkColor('r'))

    def test_native_writes_for_each_declared_output(self, surface):
        control = surface.getControl('button', 0, IMG_KEY)
        image = Qt.QImage(72, 72, Qt.QImage.Format_ARGB32)
        control.setImage(image)
        assert surface.writesFor(control)[-1] == {
            'op': 'image',
            'control': control,
            'image': image,
        }
        control.setText('hi', color='w', background='k')
        assert surface.writesFor(control)[-1]['op'] == 'text'
        control.clear()
        assert surface.writesFor(control)[-1]['op'] == 'clear'

    def test_an_output_the_block_did_not_declare_is_refused(self, surface):
        # no rendering, no substitution: what a control cannot do, it will not fake
        control = surface.getControl('button', 0, LIT_KEY)
        with pytest.raises(UnsupportedControlFeature):
            control.setText('nope')
        with pytest.raises(UnsupportedControlFeature):
            control.setImage(Qt.QImage(8, 8, Qt.QImage.Format_ARGB32))

    def test_a_control_with_no_output_at_all_refuses_everything(self, surface):
        control = surface.getControl('dial', 0, 'fader')
        with pytest.raises(UnsupportedControlFeature):
            control.setColor('r')
        with pytest.raises(UnsupportedControlFeature):
            control.clear()

    def test_setcolor_is_native_for_every_colour_the_hardware_can_show(self, surface):
        control = surface.getControl('button', 0, LIT_KEY)
        for color in ('r', 'b', 'm', 'k', '#7f00c8', (12, 0, 200)):
            control.setColor(color)
            write = surface.writesFor(control)[-1]
            assert write['op'] == 'color'
            assert write['color'] == pg.mkColor(color), color

    def test_setcolor_raises_for_a_colour_the_hardware_cannot_show(self, surface):
        # strict, not approximate: nothing decides that green is near enough to something
        # else, and nothing quietly leaves the control dark
        control = surface.getControl('button', 0, LIT_KEY)
        control.setColor('r')
        surface.clearWrites()
        with pytest.raises(UnsupportedControlFeature):
            control.setColor('g')
        assert surface.writes == []
        # the rejected request is not cached, so a repaint replays the last good one
        assert control.cachedAppearance() == ('color', {'color': pg.mkColor('r')})

    def test_a_refused_colour_says_what_the_hardware_cannot_do(self, surface):
        # strictness is bearable because the refusal states the rule it broke
        with pytest.raises(UnsupportedControlFeature) as exc:
            surface.getControl('button', 0, LIT_KEY).setColor('g')
        assert pg.mkColor('g').name() in str(exc.value)
        assert 'green' in str(exc.value)

    def test_a_subclass_can_lift_the_restriction(self, qapp):
        # the rule is part of the block's declared output, so stand-in hardware that shows
        # anything simply declares something else
        surface = UnrestrictedSurface(MagicMock(), {}, 'UnrestrictedLit')
        control = surface.getControl('button', 0, LIT_KEY)
        control.setColor('g')
        assert surface.writesFor(control)[-1]['color'] == pg.mkColor('g')


class TestAppearanceCache:
    def test_cached_appearance_is_replayable(self, surface):
        control = surface.getControl('button', 0, LIT_KEY)
        control.setColor('r')
        op, kwds = control.cachedAppearance()
        assert op == 'color' and kwds == {'color': pg.mkColor('r')}
        surface.clearWrites()
        control.replayAppearance()
        assert surface.writesFor(control) == [
            {'op': 'color', 'control': control, 'color': pg.mkColor('r')}
        ]

    def test_replay_without_appearance_is_a_noop(self, surface):
        surface.getControl('button', 0, LIT_KEY).replayAppearance()
        assert surface.writes == []


class TestNativeAppearanceOps:
    """A surface's own appearance call is cached, replayed and page-gated.

    The operation vocabulary is entirely the surface's -- ``op`` names a ``_write<Op>``
    method -- so a control with something idiosyncratic to offer needs no base-class
    support for it, and the base class need not have heard of it.
    """

    def test_a_native_op_is_cached_and_page_gated(self, qapp):
        class BuzzControl(Control):
            def buzz(self, strength):
                self._setAppearance('buzz', strength=strength)

        class BuzzSurface(MockControlSurface):
            _controlClass = BuzzControl

            def _writeBuzz(self, control, strength):
                self.writes.append({'op': 'buzz', 'control': control, 'strength': strength})

        surface = BuzzSurface(MagicMock(), {}, 'Buzzy')
        onPage1 = surface.getControl('button', 1, LIT_KEY)
        onPage1.buzz(3)
        assert surface.writes == []  # page 1 is not active, so this is cached only
        assert onPage1.cachedAppearance() == ('buzz', {'strength': 3})

        surface.setCurrentPage(1)
        assert {'op': 'buzz', 'control': onPage1, 'strength': 3} in surface.writes

    def test_an_op_the_surface_cannot_write_is_an_error(self, surface):
        with pytest.raises(ValueError):
            surface._applyAppearance(surface.getControl('button', 0, LIT_KEY), 'levitate')


# ------------------------------------------------------------------------------- dials


class TestDials:
    def test_relative_dial_emits_deltas_and_reports_no_range(self, surface):
        control = surface.getControl('dial', 0, 'jog')
        caps = control.capabilities()['input']
        assert caps['mode'] == 'relative'
        assert not {'min', 'max', 'flat'} & set(caps)

        moves = []
        control.sigMoved.connect(lambda ctl, value: moves.append(value))
        surface.mockMove('dial', 'jog', 3)
        surface.mockMove('dial', 'jog', -1)
        pump()
        assert moves == [3, -1]

    def test_absolute_dial_reports_range(self, surface):
        caps = surface.getControl('dial', 0, 'fader').capabilities()['input']
        assert caps['mode'] == 'absolute'
        assert (caps['min'], caps['max'], caps['flat'], caps['fuzz']) == (-100, 100, 5, 3)

    def test_absolute_dial_suppresses_changes_below_fuzz(self, surface):
        control = surface.getControl('dial', 0, 'fader')
        moves = []
        control.sigMoved.connect(lambda ctl, value: moves.append(value))
        surface.mockMove('dial', 'fader', 50)
        surface.mockMove('dial', 'fader', 52)  # |52-50| < fuzz(3): suppressed
        surface.mockMove('dial', 'fader', 54)  # |54-50| >= fuzz: reported
        pump()
        assert moves == [50, 54]
        assert control.value() == 54

    def test_absolute_dial_reads_center_inside_flat(self, surface):
        control = surface.getControl('dial', 0, 'fader')
        moves = []
        control.sigMoved.connect(lambda ctl, value: moves.append(value))
        surface.mockMove('dial', 'fader', 50)
        surface.mockMove('dial', 'fader', 4)  # within flat(5) of the center
        surface.mockMove('dial', 'fader', -5)  # also within flat
        surface.mockMove('dial', 'fader', 20)
        pump()
        assert moves == [50, 0, 0, 20]

    def test_dial_press_and_release(self, surface):
        control = surface.getControl('dial', 0, 'jog')
        events = []
        control.sigPressed.connect(lambda ctl: events.append('press'))
        control.sigReleased.connect(lambda ctl: events.append('release'))
        surface.mockPress('dial', 'jog')
        surface.mockRelease('dial', 'jog')
        pump()
        assert events == ['press', 'release']

    def test_touch_carries_payload(self, surface):
        control = surface.getControl('button', 0, IMG_KEY)
        touched = []
        control.sigTouched.connect(lambda ctl, value: touched.append(value))
        surface.mockTouch('button', IMG_KEY, value={'x': 3})
        pump()
        assert touched == [{'x': 3}]


class TestCapabilityValidation:
    def test_relative_dial_may_not_declare_a_range(self, surface):
        with pytest.raises(ValueError, match='no range'):
            surface._addControlBlock(
                'dial',
                {'input': {'mode': 'relative', 'min': 0, 'max': 1}, 'output': {}},
                keys=['bad'],
            )

    def test_absolute_dial_needs_min_and_max(self, surface):
        with pytest.raises(ValueError, match='missing'):
            surface._addControlBlock(
                'dial', {'input': {'mode': 'absolute'}, 'output': {}}, keys=['bad']
            )

    def test_dial_needs_a_mode(self, surface):
        with pytest.raises(ValueError, match='mode'):
            surface._addControlBlock('dial', {'input': {}, 'output': {}}, keys=['bad'])

    def test_unhashable_key_is_rejected(self, surface):
        with pytest.raises(TypeError, match='hashable'):
            surface._addControlBlock('button', {'input': {'press': True}}, keys=[[0, 0]])

    def test_unknown_capability_section_is_rejected(self, surface):
        with pytest.raises(ValueError, match='unknown top-level'):
            surface._addControlBlock('button', {'press': True}, keys=['bad'])

    def test_duplicate_address_is_rejected(self, surface):
        with pytest.raises(ValueError, match='already declared'):
            surface._addControlBlock('button', {'input': {'press': True}}, keys=[IMG_KEY])

    def test_open_type_vocabulary(self, surface):
        surface._addControlBlock('trackball', {'input': {'press': False}}, keys=['left'])
        assert 'trackball' in surface.controls(page=0)
        assert surface.getControl('trackball', 1, 'left').type == 'trackball'


# ------------------------------------------------------------------------------- pages


class TestSurfaceTeardown:
    """``ControlSurface.quit()``, the base-class teardown that subclasses call via super()."""

    def test_quit_releases_every_control_on_every_page(self, surface):
        owner = object()
        page0 = surface.acquireControl('button', 0, IMG_KEY, owner=owner)
        page1 = surface.acquireControl('button', 1, IMG_KEY, owner=owner)
        surface.quit()
        assert page0.owner is None and page1.owner is None

    def test_quit_stops_routing_queued_events(self, surface):
        pressed = []
        control = surface.acquireControl('button', 0, IMG_KEY, owner=object())
        control.sigPressed.connect(lambda ctl: pressed.append(ctl))
        surface.mockPress('button', IMG_KEY)
        surface.quit()
        pump()
        assert pressed == []

    def test_quit_does_not_paint_a_surface_that_is_going_away(self, surface):
        # unlike release(), quit() does not blank the control
        control = surface.acquireControl('button', 0, LIT_KEY, owner=object())
        control.setColor('r')
        surface.clearWrites()
        surface.quit()
        assert control.owner is None
        assert surface.writes == []

    def test_quit_severs_the_owners_slots_too(self, surface):
        pressed = []
        control = surface.acquireControl('button', 0, IMG_KEY, owner=object())
        control.sigPressed.connect(lambda ctl: pressed.append(ctl))
        surface.quit()
        control.sigPressed.emit(control)
        assert pressed == []

    def test_quit_is_idempotent(self, surface):
        surface.acquireControl('button', 0, IMG_KEY, owner=object())
        surface.quit()
        surface.quit()


class TestPages:
    def test_default_page_bookkeeping(self, surface):
        assert surface.pageCount() == 2
        assert surface.pageNames() == ['Page 1', 'Page 2']
        assert surface.currentPage() == 0

    def test_configured_page_count_builds_controls_on_every_page(self, qapp):
        surface = makeSurface(qapp, pages=3)
        assert surface.pageCount() == 3
        page0 = {(c.type, c.key) for c in surface.allControls(page=0)}
        assert len(page0) == 2 * 3 + 2 * 4 + 2  # image buttons, lit buttons, two dials
        for page in range(3):
            assert [g.shape for g in surface.controlGrids(page=page)] == [(2, 3), (2, 4)]
            assert {(c.type, c.key) for c in surface.allControls(page=page)} == page0
            assert all(c.page == page for c in surface.allControls(page=page))

    def test_pages_hold_distinct_controls(self, surface):
        assert surface.getControl('button', 0, IMG_KEY) is not surface.getControl(
            'button', 1, IMG_KEY
        )

    def test_set_page_name(self, surface):
        surface.setPageName(1, 'Patching')
        assert surface.pageNames() == ['Page 1', 'Patching']

    def test_page_count_must_be_at_least_one(self, surface):
        with pytest.raises(ValueError, match='at least one page'):
            surface._setPageCount(0)

    def test_page_count_is_declared_once(self, qapp):
        surface = ControlSurface(MagicMock(), {}, 'Bare')
        surface._setPageCount(3)
        with pytest.raises(RuntimeError, match='already declared a page count'):
            surface._setPageCount(4)
        assert surface.pageCount() == 3

    def test_declaring_pages_after_controls_is_rejected(self, surface):
        # the failure this guards against is a block landing on page 0 alone
        with pytest.raises(RuntimeError, match='before its page count'):
            surface._setPageCount(4)
        assert surface.pageCount() == 2

    def test_a_surface_that_declares_no_page_count_has_one_page(self, qapp):
        surface = ControlSurface(MagicMock(), {}, 'Bare')
        assert surface.pageCount() == 1
        assert surface.pageNames() == ['Page 1']
        assert surface.controlGrids(page=0) == []

    def test_bad_page_index_raises(self, surface):
        with pytest.raises(IndexError):
            surface.setCurrentPage(7)
        with pytest.raises(IndexError):
            surface.controls(page=7)
        with pytest.raises(IndexError):
            surface.controlGrids(page=7)

    def test_a_software_surface_can_set_its_page(self, surface):
        assert surface.canSetCurrentPage() is True

    def test_a_surface_that_cannot_set_its_page_raises(self, surface):
        surface._canSetPage = False
        try:
            with pytest.raises(NotImplementedError, match='change page'):
                surface.setCurrentPage(1)
            assert surface.currentPage() == 0
        finally:
            surface._canSetPage = True

    def test_page_change_signal(self, surface):
        changed = []
        surface.sigPageChanged.connect(lambda dev, page: changed.append((dev, page)))
        surface.setCurrentPage(1)
        assert changed == [(surface, 1)]
        assert surface.currentPage() == 1

    def test_events_route_to_active_page_only(self, surface):
        page0 = surface.getControl('button', 0, IMG_KEY)
        page1 = surface.getControl('button', 1, IMG_KEY)
        pressed = []
        page0.sigPressed.connect(lambda ctl: pressed.append(0))
        page1.sigPressed.connect(lambda ctl: pressed.append(1))

        surface.mockPress('button', IMG_KEY)
        pump()
        assert pressed == [0]

        surface.setCurrentPage(1)
        surface.mockPress('button', IMG_KEY)
        pump()
        assert pressed == [0, 1]

    def test_an_event_belongs_to_the_page_that_was_showing_when_it_happened(self, surface):
        """A press goes to the page active when it was emitted, even if setCurrentPage()
        runs before the queued event is dispatched."""
        page0 = surface.getControl('button', 0, IMG_KEY)
        page1 = surface.getControl('button', 1, IMG_KEY)
        pressed = []
        page0.sigPressed.connect(lambda ctl: pressed.append(0))
        page1.sigPressed.connect(lambda ctl: pressed.append(1))

        surface.mockPress('button', IMG_KEY)
        surface.setCurrentPage(1)
        pump()
        assert pressed == [0]

    def test_every_event_kind_is_pinned_to_the_page_it_happened_on(self, surface):
        page0 = surface.getControl('dial', 0, 'jog')
        page1 = surface.getControl('dial', 1, 'jog')
        heard = []
        for page, control in ((0, page0), (1, page1)):
            control.sigReleased.connect(lambda ctl, p=page: heard.append((p, 'release')))
            control.sigMoved.connect(lambda ctl, value, p=page: heard.append((p, 'move')))
            control.sigTouched.connect(lambda ctl, value, p=page: heard.append((p, 'touch')))

        surface.mockRelease('dial', 'jog')
        surface.mockMove('dial', 'jog', 4)
        surface.mockTouch('dial', 'jog', value=None)
        surface.setCurrentPage(1)
        pump()
        assert heard == [(0, 'release'), (0, 'move'), (0, 'touch')]

    def test_explicit_inactive_page_event_is_dropped(self, surface):
        page1 = surface.getControl('button', 1, IMG_KEY)
        pressed = []
        page1.sigPressed.connect(lambda ctl: pressed.append(1))
        surface.mockPress('button', IMG_KEY, page=1)
        pump()
        assert pressed == []

    def test_an_unknown_operation_is_refused_on_an_inactive_page_too(self, surface):
        """_setAppearance raises for an op with no writer even on an inactive page, and
        caches nothing."""
        control = surface.getControl('button', 1, LIT_KEY)
        with pytest.raises(ValueError, match='no writer'):
            control._setAppearance('doesNotExist', x=1)
        assert control.cachedAppearance() is None

    def test_writes_to_inactive_page_are_cached_not_sent(self, surface):
        control = surface.getControl('button', 1, LIT_KEY)
        control.setColor('r')
        assert surface.writes == []
        assert control.cachedAppearance() == ('color', {'color': pg.mkColor('r')})

    def test_page_switch_repaints_cached_and_blanks_the_rest(self, surface):
        onPage1 = surface.getControl('button', 1, LIT_KEY)
        onPage1.setColor('r')
        surface.clearWrites()

        surface.setCurrentPage(1)
        replayed = surface.writesFor(onPage1)
        assert replayed[-1]['op'] == 'color'
        assert replayed[-1]['color'] == pg.mkColor('r')

        # a control with nothing cached is blanked through Control._blank, so the previous
        # page does not linger under this page's unclaimed controls
        blanked = surface.writesFor(surface.getControl('button', 1, ('lit', 0, 1)))
        assert blanked and blanked[-1]['op'] == 'clear'

        # ...and a control with no output at all is not asked for anything
        assert surface.writesFor(surface.getControl('dial', 1, 'fader')) == []

    def test_hardware_pages_skip_routing_and_gating(self, qapp):
        class HardwarePageSurface(MockControlSurface):
            _hardwarePages = True

            def __init__(self, *args):
                self.hardwarePageSets = []
                MockControlSurface.__init__(self, *args)

            def _setHardwarePage(self, page):
                self.hardwarePageSets.append(page)

        surface = HardwarePageSurface(MagicMock(), {}, 'HWPages')
        # appearance writes reach the hardware regardless of the active page
        surface.getControl('button', 1, LIT_KEY).setColor('r')
        assert len(surface.writes) == 1

        # events carry their own page and are not filtered
        pressed = []
        surface.getControl('button', 1, IMG_KEY).sigPressed.connect(lambda ctl: pressed.append(1))
        surface.mockPress('button', IMG_KEY, page=1)
        pump()
        assert pressed == [1]

        surface.clearWrites()
        surface.setCurrentPage(1)
        assert surface.hardwarePageSets == [1]
        assert surface.writes == []  # no software repaint

    def test_hardware_page_change_notification(self, qapp):
        class HardwarePageSurface(MockControlSurface):
            _hardwarePages = True

            def _setHardwarePage(self, page):
                pass

        surface = HardwarePageSurface(MagicMock(), {}, 'HWPages')
        changed = []
        surface.sigPageChanged.connect(lambda dev, page: changed.append(page))
        surface._handlePageChanged(1)
        pump()
        assert changed == [1]
        assert surface.currentPage() == 1


# ----------------------------------------------------------------------------- threads


class TestThreadSafety:
    def test_signals_are_emitted_on_the_gui_thread(self, surface):
        control = surface.getControl('button', 0, IMG_KEY)
        threads = []
        control.sigPressed.connect(lambda ctl: threads.append(Qt.QThread.currentThread()))

        worker = threading.Thread(target=surface.mockPress, args=('button', IMG_KEY))
        worker.start()
        worker.join()

        assert pumpUntil(lambda: len(threads) == 1)
        assert threads[0] is Qt.QThread.currentThread()

    def test_events_are_not_delivered_before_the_event_loop_runs(self, surface):
        control = surface.getControl('button', 0, IMG_KEY)
        pressed = []
        control.sigPressed.connect(lambda ctl: pressed.append(True))
        surface.mockPress('button', IMG_KEY)
        assert pressed == []  # queued, not direct
        pump()
        assert pressed == [True]

    def test_unknown_event_name_is_rejected_eagerly(self, surface):
        with pytest.raises(ValueError):
            surface._handleEvent('button', IMG_KEY, 'wiggle')

    def test_event_for_unknown_control_is_logged_not_raised(self, surface):
        surface._handleEvent('button', ('img', 42, 42), 'press')
        pump()  # must not raise


# ------------------------------------------------------------------------------ config


class TestConfigParsing:
    def test_canonical_spelling(self):
        spec = parseControlConfig({'device': 'Dock', 'type': 'dial', 'page': 1, 'key': [0, 2]})
        assert spec == {'device': 'Dock', 'type': 'dial', 'page': 1, 'key': (0, 2)}

    def test_defaults(self):
        spec = parseControlConfig({'device': 'Dock', 'key': 'jog'})
        assert spec == {'device': 'Dock', 'type': 'button', 'page': 0, 'key': 'jog'}

    def test_extra_keys_are_ignored(self):
        spec = parseControlConfig({'device': 'Dock', 'key': [0, 0], 'step': 5e-6})
        assert spec['key'] == (0, 0)

    def test_hotkey_alias_is_deprecated_but_works(self, caplog):
        with caplog.at_level('WARNING'):
            spec = parseControlConfig({'hotkey': {'device': 'XK', 'key': [7, 8]}})
        assert spec == {'device': 'XK', 'type': 'button', 'page': 0, 'key': (7, 8)}
        assert 'deprecated' in caplog.text

    def test_xkey_alias_is_deprecated_but_works(self, caplog):
        with caplog.at_level('WARNING'):
            spec = parseControlConfig({'xkey': ('XK', 7, 8)})
        assert spec == {'device': 'XK', 'type': 'button', 'page': 0, 'key': (7, 8)}
        assert 'deprecated' in caplog.text

    def test_bare_three_sequence_is_the_xkey_alias(self, caplog):
        with caplog.at_level('WARNING'):
            spec = parseControlConfig(['XK', 7, 8])
        assert spec == {'device': 'XK', 'type': 'button', 'page': 0, 'key': (7, 8)}
        assert 'deprecated' in caplog.text

    def test_missing_device_raises(self):
        with pytest.raises(ValueError):
            parseControlConfig({'key': [0, 0]})

    def test_missing_key_raises(self):
        with pytest.raises(ValueError):
            parseControlConfig({'device': 'Dock'})

    def test_garbage_raises(self):
        with pytest.raises(TypeError):
            parseControlConfig(7)


@pytest.fixture
def dm(monkeypatch):
    """Stand in for the global Manager that :func:`acquireControlFromConfig` looks up.

    The function resolves the manager through :func:`acq4.Manager.getManager`, so a fake in
    the singleton slot injects a device manager exactly as passing one used to.
    """
    fake = MagicMock()
    monkeypatch.setattr('acq4.Manager.Manager.single', fake)
    return fake


class TestAcquireFromConfig:
    def test_acquires_through_the_manager(self, surface, dm):
        dm.getDevice.return_value = surface
        owner = object()
        control = acquireControlFromConfig(
            {'device': 'MockSurface', 'type': 'dial', 'page': 0, 'key': 'jog'}, owner=owner
        )
        dm.getDevice.assert_called_once_with('MockSurface')
        assert control is surface.getControl('dial', 0, 'jog')
        assert control.owner is owner

    def test_list_key_from_yaml_becomes_a_tuple_address(self, surface, dm):
        dm.getDevice.return_value = surface
        control = acquireControlFromConfig(
            {'device': 'MockSurface', 'key': ['img', 0, 1]}, owner=object()
        )
        assert control is surface.getControl('button', 0, ('img', 0, 1))

    def test_unknown_address_raises_keyerror(self, surface, dm):
        dm.getDevice.return_value = surface
        with pytest.raises(KeyError):
            acquireControlFromConfig(
                {'device': 'MockSurface', 'key': ['img', 9, 9]}, owner=object()
            )

    def test_double_acquire_raises_control_in_use(self, surface, dm):
        dm.getDevice.return_value = surface
        conf = {'device': 'MockSurface', 'key': list(IMG_KEY)}
        acquireControlFromConfig(conf, owner='first')
        with pytest.raises(ControlInUse):
            acquireControlFromConfig(conf, owner='second')

    def test_non_surface_device_raises_typeerror(self, dm):
        dm.getDevice.return_value = object()
        with pytest.raises(TypeError):
            acquireControlFromConfig({'device': 'NotASurface', 'key': [0, 0]}, owner=object())

    def test_owner_is_required(self, surface, dm):
        dm.getDevice.return_value = surface
        conf = {'device': 'MockSurface', 'key': list(IMG_KEY)}
        with pytest.raises(TypeError):
            acquireControlFromConfig(conf)
        with pytest.raises(ValueError):
            acquireControlFromConfig(conf, owner=None)
        assert surface.getControl('button', 0, IMG_KEY).owner is None


# -------------------------------------------------------------------------------- misc


class TestAbstractBase:
    def test_an_appearance_op_with_no_writer_is_an_error(self, qapp):
        # the surface's side of the same contract: op names a _write<Op> or it is a bug
        surface = ControlSurface(MagicMock(), {}, 'Bare')
        surface._addControlBlock(
            'button', {'input': {'press': True}, 'output': {'glow': True}}, keys=['only']
        )
        control = surface.getControl('button', 0, 'only')
        with pytest.raises(ValueError, match='_writeGlow'):
            control._setAppearance('glow', level=3)
        assert control.cachedAppearance() is None

    def test_a_bare_surface_blanks_nothing(self, qapp):
        surface = ControlSurface(MagicMock(), {}, 'Bare')
        surface._setPageCount(2)
        surface._addControlBlock(
            'button', {'input': {'press': True}, 'output': {'glow': True}}, keys=['only']
        )
        # the default _blank does nothing, so neither release nor a page switch needs a
        # writer the surface has not written
        surface.getControl('button', 0, 'only').acquire(object()).release()
        surface.setCurrentPage(1)

    def test_hardware_pages_require_an_implementation(self, qapp):
        class Bare(ControlSurface):
            _hardwarePages = True

        surface = Bare(MagicMock(), {}, 'Bare')
        surface._setPageCount(2)
        with pytest.raises(NotImplementedError):
            surface.setCurrentPage(1)


class TestDeviceInterface:
    def test_interface_constructs_and_injects_events(self, surface):
        widget = surface.deviceInterface(None)
        assert isinstance(widget, MockControlSurfaceInterface)
        pressed = []
        surface.getControl('button', 0, IMG_KEY).sigPressed.connect(
            lambda ctl: pressed.append(True)
        )
        widget.findChildren(Qt.QPushButton)[0].setChecked(True)
        pump()
        assert pressed == [True]
        widget.deleteLater()
