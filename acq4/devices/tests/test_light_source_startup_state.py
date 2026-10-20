"""What a light source does to the hardware while it is being constructed.

``initialState`` is the one configuration option that takes physical action as the
device is built, before any UI exists and before an operator can intervene. These
cover what it emits, what it emits it in, and what happens when the config it is
reading turns out to be wrong halfway through.

The CoolLED cases run the device's real io thread against a recording stand-in for
its serial port, so the commands asserted on are the ones the driver actually puts
on the wire and in the order it puts them there.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

# Both light sources reach a serial port through their drivers, and pyserial is an
# optional extra, so an install without one cannot import either module.
pytest.importorskip("serial")

import acq4.devices.CoolLEDLightSource as coolled_module
import acq4.devices.ThorlabsDC4100 as thorlabs_module
from acq4.devices.CoolLEDLightSource import CoolLEDLightSource
from acq4.devices.LightSource import LightSource
from acq4.devices.ThorlabsDC4100 import ThorlabsDC4100

TIMEOUT = 2.0


def wait_until(pred, timeout=TIMEOUT):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return False


class RecordingPort:
    """Stands in for the CoolLED's SerialDevice, recording what is written to it.

    Responses are queued by the test and handed back one line at a time, which is
    how the real device volunteers its status string.
    """

    def __init__(self, *args, **kwds):
        self.writes = []
        self._responses = []
        self._lock = threading.Lock()
        self.closed = False
        #: the device that opened this port, so the fixture can quit it
        self.device = None

    def write(self, data):
        with self._lock:
            self.writes.append(data.decode("utf-8"))

    def hasDataToRead(self):
        with self._lock:
            return bool(self._responses)

    def readline(self):
        with self._lock:
            return self._responses.pop(0).encode("utf-8")

    def close(self):
        self.closed = True

    def queueResponse(self, line):
        with self._lock:
            self._responses.append(line)

    def commands(self):
        """Every command written so far, split back out of the write buffer."""
        with self._lock:
            return [c for c in "".join(self.writes).split("\n") if c]


def statusLine(a=("F", 0), b=("F", 0), c=("F", 0)):
    """The 21-character status string the hardware reports.

    One group per channel: the channel letter, 'S', 'N' or 'F' for on or off, and
    three digits of intensity, at the offsets ``_handleData`` reads.
    """
    return (f"CSSAS{a[0]}{a[1]:03d}"
            f"BS{b[0]}{b[1]:03d}"
            f"CS{c[0]}{c[1]:03d}")


@pytest.fixture
def port(monkeypatch):
    """Install the recording port, and quit whatever device the test built.

    The io thread is the production one, so the loop under test -- buffer, write,
    read, dispatch -- is the real one; it is made a daemon only so that a device
    left unquit by a failing test cannot outlive the session. Devices are quit at
    teardown, because an io thread still polling every 200 ms for the rest of the
    run perturbs the timing-sensitive tests later in it.
    """
    made = []

    def makePort(*args, **kwds):
        made.append(RecordingPort())
        return made[-1]

    def daemonThread(target, name=None):
        return threading.Thread(target=target, name=name, daemon=True)

    monkeypatch.setattr(coolled_module, "SerialDevice", makePort)
    monkeypatch.setattr(coolled_module, "Thread", daemonThread)
    yield made
    for p in made:
        if p.device is not None:
            p.device.quit()


@pytest.fixture
def dc4100(monkeypatch):
    """The DC4100 serial driver, replaced by a recorder; the device is real."""
    driver = MagicMock()
    driver.get_brightness.return_value = 50.0
    monkeypatch.setattr(thorlabs_module, "DC4100Driver", lambda port=None: driver)
    return driver


def makeCoolLED(sources, port):
    dev = CoolLEDLightSource(MagicMock(), {"port": "COM1", "sources": sources}, "CoolLED")
    port[0].device = dev
    return dev, port[0]


# ------------------------------------------------------------------ brightness range


class TestBrightnessIsRangeChecked:
    """Brightness is normalized 0.0-1.0; a percentage is a hundredfold error.

    Unchecked, ``brightness: 50`` reaches the CoolLED as ``CSSASN5000`` -- a
    ten-character frame on a nine-character protocol -- and ``-0.2`` as
    ``CSSASF-20``. The format string's ``:03d`` is a minimum width, not a clamp.
    """

    @pytest.mark.parametrize("value", [50, 100, -0.2, 1.5, float("nan")])
    def test_a_brightness_outside_zero_to_one_is_refused(self, value, port):
        with pytest.raises(ValueError, match="rightness"):
            makeCoolLED({"A": {"initialState": {"brightness": value}}}, port)

    def test_the_refusal_happens_before_anything_is_written(self, port):
        with pytest.raises(ValueError):
            makeCoolLED({"A": {"initialState": {"brightness": 50}}}, port)

        time.sleep(0.25)
        assert port[0].commands() == [], "a refused brightness still reached the port"

    @pytest.mark.parametrize("value", [0, 0.0, 0.5, 1, 1.0])
    def test_a_brightness_in_range_is_accepted(self, value, port):
        makeCoolLED({"A": {"initialState": {"brightness": value}}}, port)

    def test_an_unknown_state_key_is_refused(self, port):
        with pytest.raises(ValueError, match="intensity"):
            makeCoolLED({"A": {"initialState": {"intensity": 0.5}}}, port)


# ------------------------------------------------------- CoolLED: on at zero intensity


class TestTheHardwareBrightnessIsReadBeforeActivating:
    """``initialState: True`` must not enable a channel at 0%.

    Every CoolLED command carries the on/off bit and the intensity together, so
    activating a channel whose brightness has never been read sends ``CSSASN000``:
    enabled, dark. The device then reports ``active=True``, the control-surface
    indicator lights and the UI agrees -- and because the hardware honestly
    confirms 000, the disagreement never resolves.
    """

    def test_no_enabled_at_zero_command_is_sent_at_construction(self, port):
        dev, p = makeCoolLED({"A": {"initialState": True}}, port)

        time.sleep(0.25)
        assert "CSSASN000" not in p.commands(), "the channel was enabled at 0%"

    def test_the_source_is_not_reported_active_until_it_is(self, port):
        dev, p = makeCoolLED({"A": {"initialState": True}}, port)

        time.sleep(0.25)
        assert dev.sourceActive("A") is False, "reported on while nothing had been sent"

    def test_the_status_is_requested(self, port):
        dev, p = makeCoolLED({"A": {"initialState": True}}, port)

        assert wait_until(lambda: "CSS?" in p.commands()), \
            "never asked the hardware what brightness it was at"

    def test_the_state_is_applied_at_the_reported_brightness(self, port):
        """Once the hardware has said 70%, `initialState: True` means on at 70%."""
        dev, p = makeCoolLED({"A": {"initialState": True}}, port)
        p.queueResponse(statusLine(a=("F", 70)))

        assert wait_until(lambda: "CSSASN070" in p.commands()), \
            f"never enabled the channel at the reported brightness; sent {p.commands()}"
        assert dev.sourceActive("A") is True

    def test_a_state_carrying_its_own_brightness_does_not_wait(self, port):
        """Only a state that needs a brightness it was not given has to wait."""
        dev, p = makeCoolLED({"A": {"initialState": {"active": True, "brightness": 0.5}}}, port)

        assert wait_until(lambda: "CSSASN050" in p.commands()), \
            f"configured brightness never applied; sent {p.commands()}"
        assert "CSS?" not in p.commands(), "waited on a status it did not need"

    def test_a_channel_with_no_initial_state_is_left_alone(self, port):
        dev, p = makeCoolLED({"A": {"wavelength": 470e-9}}, port)
        p.queueResponse(statusLine(a=("N", 80)))

        time.sleep(0.3)
        assert [c for c in p.commands() if c.startswith("CSSAS")] == [], \
            "a source with no initialState was commanded anyway"


class TestExplicitOffDoesNotFlashTheLedOn:
    """``{active: False, brightness: 0.5}`` is the one config whose intent is plain.

    This device derives nothing: the on/off bit is carried over from the state the
    channel is already in, so setting a brightness cannot light a dark channel.
    """

    def test_no_on_command_is_emitted_for_an_explicit_off(self, port):
        dev, p = makeCoolLED({"A": {"initialState": {"active": False, "brightness": 0.5}}}, port)

        assert wait_until(lambda: "CSSASF050" in p.commands()), \
            f"never set the configured brightness; sent {p.commands()}"
        onCommands = [c for c in p.commands() if c.startswith("CSSASN")]
        assert onCommands == [], f"an explicit off flashed the LED on: {onCommands}"

    def test_an_explicit_off_with_no_brightness_does_not_zero_the_channel(self, port):
        """`CSSASF000` would turn the channel off and wipe its intensity with it."""
        dev, p = makeCoolLED({"A": {"initialState": False}}, port)
        p.queueResponse(statusLine(a=("N", 80)))

        assert wait_until(lambda: "CSSASF080" in p.commands()), \
            f"never turned the channel off at its own brightness; sent {p.commands()}"
        assert "CSSASF000" not in p.commands(), "turning the channel off zeroed it"

    def test_setting_the_brightness_of_a_dark_channel_leaves_it_dark(self, port):
        dev, p = makeCoolLED({"A": {}}, port)
        p.queueResponse(statusLine(a=("F", 0)))
        time.sleep(0.25)

        dev.setSourceBrightness("A", 0.4)

        assert wait_until(lambda: "CSSASF040" in p.commands()), \
            f"brightness change did not keep the channel off; sent {p.commands()}"
        assert dev.sourceActive("A") is False

    def test_setting_the_brightness_of_a_lit_channel_leaves_it_lit(self, port):
        dev, p = makeCoolLED({"A": {}}, port)
        p.queueResponse(statusLine(a=("N", 80)))
        assert wait_until(lambda: dev.sourceActive("A"))

        dev.setSourceBrightness("A", 0.4)

        assert wait_until(lambda: "CSSASN040" in p.commands()), \
            f"brightness change switched a lit channel off; sent {p.commands()}"


# --------------------------------------------------- a config error partway through


class TestAConfigErrorEnergisesNothing:
    """A device that raises partway through construction is never registered.

    It is absent from every UI and has no object left that could switch a lamp
    off, so whatever it lit stays lit until the config is fixed and ACQ4 is
    restarted. Every source is therefore checked before any of them is applied.
    """

    def test_a_later_source_missing_its_channel_leaves_the_earlier_one_dark(self, dc4100):
        with pytest.raises(ValueError, match="channel"):
            ThorlabsDC4100(
                MagicMock(),
                {
                    "sources": {
                        "Blue": {"channel": 1, "initialState": True},
                        "Green": {"wavelength": 525e-9},
                    },
                },
                "DC4100",
            )

        assert dc4100.set_led_channel_state.call_args_list == [], \
            "Blue's LED was switched on before Green's config was found to be bad"

    def test_a_valid_config_still_applies_its_initial_state(self, dc4100):
        ThorlabsDC4100(
            MagicMock(),
            {"sources": {"Blue": {"channel": 1, "initialState": True}}},
            "DC4100",
        )

        dc4100.set_led_channel_state.assert_called_once_with(1, True)

    def test_a_later_sources_bad_initial_state_leaves_the_earlier_one_dark(self, port):
        with pytest.raises(ValueError):
            makeCoolLED(
                {"A": {"initialState": True}, "B": {"initialState": {"brightness": 50}}},
                port,
            )

        time.sleep(0.25)
        assert port[0].commands() == [], "channel A was commanded before B was validated"


# -------------------------------------------------------------- the base-class contract


class FakeLightSource(LightSource):
    """Concrete LightSource that only remembers what it was told, in order."""

    def __init__(self, dm, config, name):
        super().__init__(dm, config, name)
        self.calls = []

    def setSourceActive(self, name, active):
        self.calls.append(("active", name, active))
        self.sourceConfigs[name]["active"] = bool(active)

    def getSourceBrightness(self, name):
        return self.sourceConfigs[name].get("brightness", 0.0)

    def setSourceBrightness(self, name, value):
        self.calls.append(("brightness", name, value))
        self.sourceConfigs[name]["brightness"] = value


class TestSetSourceState:
    def test_a_bare_bool_is_an_active_state(self):
        dev = FakeLightSource(MagicMock(), {}, "Lamp")
        dev.addSource("Blue", {})

        dev.setSourceState("Blue", True)

        assert dev.calls == [("active", "Blue", True)]

    def test_brightness_precedes_activation(self):
        """So that the source comes on at the brightness that was asked for."""
        dev = FakeLightSource(MagicMock(), {}, "Lamp")
        dev.addSource("Blue", {})

        dev.setSourceState("Blue", {"active": True, "brightness": 0.5})

        assert dev.calls == [("brightness", "Blue", 0.5), ("active", "Blue", True)]

    def test_an_out_of_range_brightness_is_refused_before_anything_is_set(self):
        dev = FakeLightSource(MagicMock(), {}, "Lamp")
        dev.addSource("Blue", {})

        with pytest.raises(ValueError, match="rightness"):
            dev.setSourceState("Blue", {"active": True, "brightness": 50})

        assert dev.calls == []

    def test_the_error_names_the_source(self):
        dev = FakeLightSource(MagicMock(), {}, "Lamp")
        dev.addSource("Blue", {})

        with pytest.raises(ValueError, match="Blue"):
            dev.setSourceState("Blue", {"brightness": 50})
