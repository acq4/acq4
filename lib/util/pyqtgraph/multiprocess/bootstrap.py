"""For starting up remote processes"""
import sys, pickle

if __name__ == '__main__':
    name, port, authkey, targetStr, path = pickle.load(sys.stdin)
    if path is not None:
        ## rewrite sys.path without assigning a new object--no idea who already has a reference to the existing list.
        while len(sys.path) > 0:
            sys.path.pop()
        sys.path.extend(path)
    print "bootstrap path:", sys.path
    import pyqtgraph
    print "bootstrap pyqtgraph:", pyqtgraph.__file__
    import pyqtgraph.multiprocess.processes
    target = pickle.loads(targetStr)
    target(name, port, authkey)
    sys.exit(0)
