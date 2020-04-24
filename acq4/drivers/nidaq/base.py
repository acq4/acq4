from __future__ import print_function, absolute_import


class NIDAQError(Exception):
    def __init__(self, errCode, msg):
        Exception.__init__(self, msg)
        self.errCode = errCode

