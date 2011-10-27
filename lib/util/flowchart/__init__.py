from pyqtgraph.flowchart import *
from pyqtgraph.flowchart.library import loadLibrary
import os

loadLibrary(libPath=os.path.dirname(os.path.abspath(__file__))) ## automatically pulls in Nodes found in all files in this directory.
