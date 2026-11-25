import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest


@pytest.mark.parametrize(
    'trigger', ['last-window', 'application', 'manager', 'two-windows', 'keep-running']
)
def test_manager_shutdown(trigger, tmp_path):
    # A separate process gives each scenario its own QApplication and Manager singleton.
    test_file = Path(__file__).resolve()
    result = subprocess.run(
        [sys.executable, str(test_file), trigger],
        cwd=tmp_path,
        env={
            **os.environ,
            'QT_QPA_PLATFORM': 'offscreen',
            'PYTHONPATH': os.pathsep.join(
                [str(test_file.parents[2]), os.environ.get('PYTHONPATH', '')]
            ),
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def run_shutdown_scenario(trigger):
    import pyqtgraph as pg

    from acq4 import modules
    from acq4.devices.Device import Device
    from acq4.Manager import Manager
    from acq4.modules.Module import Module
    from acq4.util import Qt

    app = pg.mkQApp()
    # Module discovery is unrelated to shutdown and imports optional hardware dependencies.
    with patch.object(modules, 'importBuiltinClasses'):
        manager = Manager()
    assert Manager.single is manager
    events = []

    class RecordingDevice(Device):
        def quit(self):
            events.append(self.name())

    class RecordingModule(Module):
        def quit(self):
            events.append(self.name)
            super().quit()

    # The device creation registry holds weak references; keep these alive until shutdown.
    devices = [RecordingDevice(manager, {}, name) for name in ['first-device', 'second-device']]
    module = RecordingModule(manager, 'module', {})
    manager.modules[module.name] = module
    window = Qt.QWidget()
    window.show()
    observations = []
    timed_out = []

    def watchdog():
        timed_out.append(True)
        app.quit()

    timer = Qt.QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(watchdog)
    timer.start(5000)

    if trigger in ('two-windows', 'keep-running'):
        if trigger == 'two-windows':
            other_window = Qt.QWidget()
            other_window.show()
            finish = other_window.close
        else:
            app.setQuitOnLastWindowClosed(False)
            finish = app.quit

        def observe_and_finish():
            observations.append((manager.alreadyQuit, list(events)))
            finish()

        def close_first_window():
            window.close()
            Qt.QTimer.singleShot(50, observe_and_finish)

        action = close_first_window
    else:
        action = {'last-window': window.close, 'application': app.quit, 'manager': manager.quit}[
            trigger
        ]

    Qt.QTimer.singleShot(0, action)
    try:
        app.exec_()
        timer.stop()
        events.append('event-loop-returned')
        assert not timed_out, 'The event loop did not exit in response to the requested action'
        if trigger in ('two-windows', 'keep-running'):
            assert observations == [(False, [])]
        expected = ['module', 'second-device', 'first-device', 'event-loop-returned']
        assert events == expected, events
        assert manager.alreadyQuit
        assert not manager.modules

        # Repeated requests, including the atexit fallback, must not repeat device cleanup.
        manager.quit()
        manager.quit()
        assert events == expected, events
    finally:
        manager.quit()


if __name__ == '__main__':
    run_shutdown_scenario(sys.argv[1])
