from __future__ import print_function


class NIDAQError(Exception):
    def __init__(self, errCode, msg):
        Exception.__init__(self, msg)
        self.errCode = errCode

