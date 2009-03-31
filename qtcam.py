# -*- coding: utf-8 -*-
from lib.DeviceManager import *
import lib.DataManager as DataManager
import os, sys
from numpy import *

config = 'config/default.cfg'
if len(sys.argv) > 1:
    config = sys.argv[1]
config = os.path.abspath(config)

dm = DeviceManager(config)
datam = DataManager.createDataHandler('junk/data')

camDev = dm.getDevice('Camera')
qtcam = dm.loadModule('Camera', camDev)