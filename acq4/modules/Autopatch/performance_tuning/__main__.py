"""Opens the performance tuning review window on its own, without an Autopatch window to arm against."""

import sys

from acq4.util import Qt

from .window import TuningWindow


def main():
    app = Qt.QApplication.instance() or Qt.QApplication(sys.argv)
    window = TuningWindow(autopatch=None)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
