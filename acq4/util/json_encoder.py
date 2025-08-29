import json

import numpy as np

from pyqtgraph import SRTTransform3D


class ACQ4JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, SRTTransform3D):
            return obj.saveState()
        return json.JSONEncoder.default(self, obj)
