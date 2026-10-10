"""MagellanPMD: StageDriver for a multi-drop RS-485 bus of PMD Magellan single-axis controllers."""
from __future__ import annotations

from acq4.drivers.stage import RequestFuture, StageDriver
from .backend import MagellanBackend


class MagellanPMD(StageDriver):
    """StageDriver over a :class:`MagellanBackend`; thread-safe, future-based.

    Positions are in driver units (``counts_per_unit`` encoder counts each).
    ``move_to(pos, speed, acceleration=None, jerk=None, profile=None)``: see
    :class:`MagellanBackend` for speed scaling and profiles. A move that includes an
    unphased (uncommutated) axis fails with NotCommutatedError.

    Parameters
    ----------
    axes : dict
        Axis name -> node ID.
    poll_interval, stop_timeout, position_change_threshold :
        As for :class:`StageDriver`; *stop_timeout* also goes to the backend.
    **backend_kwds :
        Passed to :class:`MagellanBackend`.
    """

    def __init__(self, axes: dict, *, poll_interval: float = 0.025, stop_timeout: float = 5.0,
                 position_change_threshold=None, **backend_kwds):
        backend = MagellanBackend(axes, stop_timeout=stop_timeout, **backend_kwds)
        super().__init__(backend, poll_interval=poll_interval, stop_timeout=stop_timeout,
                         position_change_threshold=position_change_threshold)

    def commutate(self, axes: list | None = None, drive_levels=(2048, 4096, 8192),
                  confirm: bool | None = None) -> RequestFuture:
        """Queue :meth:`MagellanBackend.commutate`. Does not interrupt moves; call only when idle.

        For startup after a power cycle, tests and standalone scripts. Result
        ``{axis: drive level used, or None if already phased}``. Declined: ``wait()`` raises
        MoveCancelled; failure: RequestFailed caused by CommutationError. Raises ValueError
        at once for unknown axes.
        """
        axes = self._axes_arg(axes)
        return self._run(self._backend.commutate, axes, tuple(drive_levels), confirm,
                         reason=f'commutate axes {", ".join(axes)}')

    def home(self, axes: list | None = None) -> RequestFuture:
        """Queue :meth:`MagellanBackend.home`; interrupts any active move first.

        Result ``{axis: vane position in the previous frame}``. Raises ValueError at once for
        unknown axes.
        """
        axes = self._axes_arg(axes)
        return self._run(self._backend.home, axes, interrupt=True, reason=f'home axes {", ".join(axes)}')

    def set_enabled(self, enabled: bool, axes: list | None = None, reason: str = '') -> RequestFuture:
        """Queue :meth:`MagellanBackend.set_enabled`. Raises ValueError at once for unknown axes."""
        axes = self._axes_arg(axes)
        what = f"{'enable' if enabled else 'disable'} axes {', '.join(axes)}"
        return self._run(self._backend.set_enabled, bool(enabled), axes, reason,
                         reason=f'{what}: {reason}' if reason else what)

    def is_enabled(self, timeout: float = 5.0) -> dict:
        """Axis -> True if in full closed-loop servo, freshly read. Blocks."""
        return self._run(self._backend.is_enabled, reason='read operating mode').wait(timeout)

    def get_limits(self, timeout: float = 5.0) -> dict:
        """Limit switch states, ``{'x': {'neg': bool, 'pos': bool}, ...}``, freshly read. Blocks."""
        return self._run(self._backend.get_limits, reason='read limit switches').wait(timeout)

    def _axes_arg(self, axes) -> list:
        axes = list(self.axes) if axes is None else list(axes)
        unknown = set(axes) - set(self.axes)
        if unknown:
            raise ValueError(f'unknown axes {sorted(unknown)}')
        return axes
