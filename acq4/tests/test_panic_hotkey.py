"""The focus-independent panic key (see "Panic Lock Spec.md" §4.1).

The Esc ``QShortcut`` only fires when an ACQ4 window is active and the Qt event
loop is servicing it. ``GlobalPanicHotkey`` watches the keyboard from a plain
daemon thread instead, so it works with another application in front and does not
depend on the event loop -- a wedged GUI thread being exactly when a panic key
matters most.

It is off by default and enabled with the ``panicHotkey`` config option, because
it fires wherever the key is pressed, including in other applications.
"""

from __future__ import annotations

import sys
import threading
import time

import pytest

from acq4.panic import GlobalHalt, GlobalPanicHotkey, parse_hotkey


TIMEOUT = 2.0

requires_windows = pytest.mark.skipif(
    sys.platform != "win32", reason="the global panic key is implemented for Windows only"
)


def wait_until(pred, timeout=TIMEOUT):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return False


class TestHotkeyParsing:
    @pytest.mark.parametrize(
        "spec, expected",
        [
            (False, None),
            (None, None),
            ("", None),
            (True, (0x1B, [])),
            ("Esc", (0x1B, [])),
            ("escape", (0x1B, [])),
            ("Ctrl+Alt+Esc", (0x1B, [0x11, 0x12])),
            ("ctrl+shift+f12", (0x7B, [0x11, 0x10])),
            ("Alt+P", (ord("P"), [0x12])),
        ],
    )
    def test_specs(self, spec, expected):
        assert parse_hotkey(spec) == expected

    @pytest.mark.parametrize("spec", ["Ctrl+Nope", "Hyper+Esc", "Ctrl+", 17, 3.5])
    def test_bad_specs_raise_value_error(self, spec):
        with pytest.raises(ValueError):
            parse_hotkey(spec)

    def test_the_error_names_the_offending_token(self):
        with pytest.raises(ValueError, match="unknown key 'nope'"):
            parse_hotkey("Ctrl+Nope")
        with pytest.raises(ValueError, match="unknown modifier 'hyper'"):
            parse_hotkey("Hyper+Esc")


class TestDisabledByDefault:
    def test_a_falsy_spec_starts_nothing(self):
        hk = GlobalPanicHotkey(GlobalHalt(), False)
        assert hk.enabled is False
        hk.start()  # no-op
        assert hk._thread is None

    def test_starting_a_disabled_hotkey_never_halts(self):
        gh = GlobalHalt()
        GlobalPanicHotkey(gh, False).start()
        time.sleep(0.15)
        assert gh.halted is False


def countHalts(globalHalt):
    """Record every halt() the hotkey makes, and return the list.

    Counted at the call rather than through sigHaltRequested: these tests build no
    QApplication (the whole point of the feature is that it needs neither a window
    nor an event loop), so Qt would have nowhere to deliver a signal. The signal
    itself is covered in test_panic_lock.py under qtbot.
    """
    calls = []
    real = globalHalt.halt

    def counting(reason=None):
        calls.append(reason)
        return real(reason) if reason is not None else real()

    globalHalt.halt = counting
    return calls


class _FakeKeyboard:
    """Stands in for GetAsyncKeyState so the poll loop can be driven exactly."""

    def __init__(self):
        self.down = set()
        self._lock = threading.Lock()

    def __call__(self, vk):
        with self._lock:
            return -32768 if vk in self.down else 0  # high bit = currently down

    def press(self, *vks):
        with self._lock:
            self.down.update(vks)

    def release(self, *vks):
        with self._lock:
            self.down.difference_update(vks)


@pytest.fixture
def rig():
    gh = GlobalHalt()
    kb = _FakeKeyboard()
    made = []

    def build(spec):
        hk = GlobalPanicHotkey(gh, spec)
        if hk.enabled:
            hk._getKeyState = kb
            hk.pollInterval = 0.005
            hk.start()
        made.append(hk)
        return hk

    yield gh, kb, build
    for hk in made:
        hk.stop()


@requires_windows
class TestPolling:
    def test_pressing_the_key_halts_the_rig(self, rig):
        gh, kb, build = rig
        build("Esc")

        assert gh.halted is False
        kb.press(0x1B)

        assert wait_until(lambda: gh.halted), "Esc did not latch the rig"
        assert "panic key" in gh.reason

    def test_holding_the_key_halts_once(self, rig):
        """Edge-triggered: a held key must not re-halt every poll."""
        gh, kb, build = rig
        halts = countHalts(gh)
        build("Esc")

        kb.press(0x1B)
        assert wait_until(lambda: gh.halted)
        time.sleep(0.1)  # many poll intervals

        assert len(halts) == 1, f"held key re-halted {len(halts)} times"

    def test_a_second_press_halts_again(self, rig):
        """Releasing and pressing again is a fresh 'I mean it' (§3)."""
        gh, kb, build = rig
        halts = countHalts(gh)
        build("Esc")

        kb.press(0x1B)
        assert wait_until(lambda: gh.halted)
        kb.release(0x1B)
        time.sleep(0.05)
        kb.press(0x1B)

        assert wait_until(lambda: len(halts) == 2), f"got {len(halts)} halts"

    def test_a_chord_requires_every_modifier(self, rig):
        gh, kb, build = rig
        build("Ctrl+Alt+Esc")

        kb.press(0x1B)  # bare Esc -- must be ignored
        time.sleep(0.08)
        assert gh.halted is False, "bare Esc fired a Ctrl+Alt+Esc binding"

        kb.press(0x11)  # + Ctrl, still short one modifier
        time.sleep(0.08)
        assert gh.halted is False

        kb.press(0x12)  # + Alt -- now complete
        assert wait_until(lambda: gh.halted)

    def test_the_reason_is_recorded(self, rig):
        gh, kb, build = rig
        build("Esc")
        kb.press(0x1B)
        assert wait_until(lambda: gh.halted)
        assert gh.reason == "User pressed the global panic key"

    def test_a_raising_key_read_does_not_kill_the_thread(self, rig):
        """It is the panic key; it must survive a transient failure."""
        gh, kb, build = rig
        hk = build("Esc")

        calls = []

        def flaky(vk):
            calls.append(vk)
            if len(calls) < 3:
                raise OSError("transient")
            return kb(vk)

        hk._getKeyState = flaky
        time.sleep(0.06)
        kb.press(0x1B)

        assert wait_until(lambda: gh.halted), "the poll thread died on a transient error"

    def test_stop_ends_the_thread(self, rig):
        gh, kb, build = rig
        hk = build("Esc")
        assert wait_until(lambda: hk._thread.is_alive())

        hk.stop()

        assert wait_until(lambda: not hk._thread.is_alive()), "poll thread outlived stop()"


@requires_windows
class TestAgainstTheRealKeyboardApi:
    """Prove the real API is wired up, without synthesising a keypress.

    Sending a real Esc to the whole desktop from a test would be hostile -- it
    would land in whatever window happens to be focused. So this only checks that
    the real GetAsyncKeyState is bound and answers sanely for a key nobody is
    holding; the press/release behaviour is covered above against the fake.
    """

    def test_the_real_api_is_bound_and_reads_a_key(self):
        hk = GlobalPanicHotkey(GlobalHalt(), "Ctrl+Alt+Esc")
        assert hk.enabled
        assert hk._isDown(0x1B) in (True, False)
