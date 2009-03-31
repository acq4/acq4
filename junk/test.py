#!/usr/bin/python

################################################################################
import sys, re, os

from PyQt4.QtCore import *
from PyQt4.QtGui import *

# load the gui...
import mockup


################################################################################
# One class for the main program:
################################################################################

class PyMockup(QMainWindow, mockup.Ui_MainWindow):

   def __init__(self, parent=None):
       super(PyMockup, self).__init__(parent)
       self.setupUi(self)

   @pyqtSignature("")
   def on_pushButton_2_clicked(self):
       print "pb 2 was clicked"

   @pyqtSignature("bool")
   def on_checkBox_2_clicked(self, chk):
       if chk is True:
           print "cb2 is checked"
       else:
           print "cb2 is unchecked"

   @pyqtSignature("int")
   def on_dial_2_valueChanged(self, value):
       print "dial2: %d" % (value)

################################################################################
#
# main entry
#

if __name__ == "__main__":
# check the hardware first
   app = QApplication(sys.argv)
   MainWindow = PyMockup()
   MainWindow.show()
   sys.exit(app.exec_())
