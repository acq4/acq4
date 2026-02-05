import json
from json.encoder import _make_iterencode

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


class IgorJSONEncoder(ACQ4JSONEncoder):
    """JSON encoder that converts NaN and Inf to strings for compatibility with Igor Pro."""
    def iterencode(self, o, _one_shot=False):
        # This is copied from stdlib pattern: provide a custom floatstr.
        def floatstr(x, allow_nan=self.allow_nan,
                     _repr=float.__repr__,
                     _inf=float('inf'),
                     _neginf=-float('inf')):
            if np.isnan(x):
                return '"NaN"'              # already JSON-quoted
            if x == _inf:
                return '"Inf"'
            if x == _neginf:
                return '"-Inf"'
            return _repr(x)

        _encoder = json.encoder.encode_basestring_ascii if self.ensure_ascii else json.encoder.encode_basestring

        # Most of these are internal defaults the stdlib uses
        markers = {} if self.check_circular else None
        _iterencode = _make_iterencode(
            markers, self.default, _encoder, self.indent, floatstr,
            self.key_separator, self.item_separator, self.sort_keys,
            self.skipkeys, self.allow_nan
        )
        return _iterencode(o, 0)
