import base64
import struct
import zlib

import numpy as np

from acq4.drivers.dovermotion.motionsynergy_client import get_client
from ..Stage import Stage, MoveFuture


def _make_color_image(r, g, b, size=72):
    """Return a solid-color PNG as a base64 data URI for Stream Dock buttons."""
    def _chunk(tag, data):
        c = tag + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)

    ihdr = struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0)
    row = b'\x00' + bytes([r, g, b] * size)
    idat = zlib.compress(row * size)
    png = (
        b'\x89PNG\r\n\x1a\n'
        + _chunk(b'IHDR', ihdr)
        + _chunk(b'IDAT', idat)
        + _chunk(b'IEND', b'')
    )
    return 'data:image/png;base64,' + base64.b64encode(png).decode('ascii')


_AXIS_ENABLED_IMG = _make_color_image(40, 167, 69)   # green
_AXIS_DISABLED_IMG = _make_color_image(180, 30, 30)  # red


class DoverStage(Stage):
    """
    A DoverMotion stage device.
    """

    def __init__(self, man, config: dict, name):
        Stage.__init__(self, man, config, name)
        self.msapi = get_client(dll_path=config["dllPath"])
        self.dev = self.msapi['smartstage']
        self.dev.default_acceleration = config.get("defaultAcceleration", 50.0)
        self.dev.enable()
        self._lastMove = None
        self.posChanged(self.dev.pos(refresh=True))
        self.dev.set_callback(self.posChanged)
        man.declareInterface(name, ['stream_dock'], self)

    def axes(self):
        return "x", "y", "z"

    def capabilities(self):
        """Return a structure describing the capabilities of this device"""
        if "capabilities" in self.config:
            return self.config["capabilities"]
        else:
            return {
                "getPos": (True, True, True),
                "setPos": (True, True, True),
                "limits": (False, False, False),
            }

    def stop(self, reason=None):
        """Stop the stage immediately."""
        return self.dev.stop()

    def _getPosition(self):
        return self.dev.pos()

    @property
    def positionUpdatesPerSecond(self):
        return 1 / self.dev.control_thread.poll_interval

    def _move(self, pos, speed, linear, **kwds):
        speed = self._interpretSpeed(speed)
        self._lastMove = DoverMoveFuture(self, pos, speed)
        return self._lastMove

    def targetPosition(self):
        """Return the target position of the last move command."""
        if self._lastMove is not None:
            return self._lastMove.target
        else:
            return None

    # def deviceInterface(self, win):
    #     return DoverStageInterface(self, win)

    def configure_dock(self, stream_dock_device):
        """Register Stream Dock toggle buttons for enabling / disabling each axis.

        One button per axis (X, Y, Z).  The button background is green when the
        axis is enabled and red when it is disabled.
        """
        buttons = []
        for i, axis_name in enumerate(self.axes()):
            def make_on_appear(i):
                def on_appear(context):
                    enabled = self.dev.is_enabled()
                    img = _AXIS_ENABLED_IMG if (enabled is not None and enabled[i]) else _AXIS_DISABLED_IMG
                    stream_dock_device.setImage(context, img)
                return on_appear

            btn = stream_dock_device.add_button(
                axis_name.upper(),
                on_press=lambda i=i: self._toggle_axis(i),
                on_appear=make_on_appear(i),
            )
            buttons.append(btn)

        def _update_colors(enabled_state):
            for i, btn in enumerate(buttons):
                if btn.context is not None:
                    img = _AXIS_ENABLED_IMG if enabled_state[i] else _AXIS_DISABLED_IMG
                    stream_dock_device.setImage(btn.context, img)

        # self.dev.add_enabled_state_callback(_update_colors)

    def _toggle_axis(self, axis_index):
        """Toggle the enabled state of a single axis."""
        enabled = self.dev.is_enabled()
        if enabled is not None and enabled[axis_index]:
            self.dev.disable_axis(axis_index)
        else:
            self.dev.enable_axis(axis_index)

    def quit(self):
        self.dev.set_callback(None)


class DoverMoveFuture(MoveFuture):
    """Provides access to a move-in-progress on a Dover stage."""

    def __init__(self, dev, pos, speed):
        MoveFuture.__init__(self, dev, pos, speed)
        self.dev = dev
        self.target = np.asarray(pos)
        self._future = self.dev.dev.move(list(pos), self.speed * 1e3)
        self._future.set_callback(self._future_finished)

    def _future_finished(self, req_fut):
        self._taskDone(
            interrupted=req_fut.error._get_value() is not None,
            error=req_fut.error._get_value(),
            excInfo=req_fut.exc_info._get_value(),
        )
