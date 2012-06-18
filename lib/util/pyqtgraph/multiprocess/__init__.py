"""
Multiprocessing utility library
(parallelization done the way I like it)

Luke Campagnola
2012.06.10

This library provides:
  - simple mechanism for starting a new python interpreter process that can be controlled from the original process
  - proxy system that allows objects hosted in the remote process to be used as if they were local
  - Qt signal connection between processes

Example:
  
    ## start new process, start listening for events from remote
    proc = QtProcess('remote_plotter')
    proc.startEventTimer()

    ## import pyqtgraph on remote end, assign to local variable
    rpg = proc._import('pyqtgraph')
    
    ## use rpg exactly as if it were a local pyqtgraph module
    win = rpg.GraphicsWindow()
    plt1 = win.addPlot()
    p1 = plt.plot([1,5,2,4,3])
    p1.setPen('g')

    ## even connect signals from remote process to local functions
    def viewChanged(*args):
        print "Remote view changed:", args
    plt1.sigViewChanged.connect(viewChanged)

TODO:
    - deferred attribute lookup
    
    - attributes of proxy should inherit defaultReturnMode
    - additionally, proxies should inherit defaultReturnMode from the Process that generated them
        - and _import should obey defaultReturnMode ?
    - can we make process startup asynchronous since it takes so long?
        - Process can defer sending requests until remote process is ready
        
        
        
"""

from processes import *
