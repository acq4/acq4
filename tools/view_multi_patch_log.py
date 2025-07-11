import argparse

import sys

from acq4.filetypes.MultiPatchLog import MultiPatchLogWidget
from acq4.util import Qt
from acq4.util.DataManager import getFileHandle

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('log_file', help='Path to a MultiPatch log file')
    args = parser.parse_args()
    app = Qt.QApplication([])
    w = MultiPatchLogWidget()
    fh = getFileHandle(args.log_file)
    w.addLog(fh)
    w.show()
    sys.exit(app.exec_())
