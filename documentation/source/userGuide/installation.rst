Installation
============

ACQ4 depends on several free software packages to work properly.
    
    #. Python 2.7
    #. Numpy
    #. Scipy
    #. PyQt 4.8
    #. h5py

These are the minimal requirements to run ACQ4 (eg, for data analysis). For data acquisition, there are extra requirements:
    
    #. pyparsing
    #. pyserial (only if using serial devices--Sutter MP285, serial mice, etc)
    
You also need to make sure that the drivers for your devices are installed and working properly. 


Windows Installation
--------------------

In Windows, there is currently no way to install all requirements in one shot (sorry, maybe later).
Download and install all prerequisites in order:
    
#. Python 2.7: http://python.org
#. PyQt4: http://www.riverbankcomputing.co.uk/software/pyqt/download  (Be sure to get the version built for python 2.7)
#. Numpy *and* Scipy: http://scipy.org/Download (look for the 'superpack' files for python 2.7)
#. h5py:  http://code.google.com/p/h5py/downloads/list   (Windows installer for Python 2.7)
#. pypasring version *1.5.2* http://sourceforge.net/projects/pyparsing/files/pyparsing/pyparsing-1.5.2/  (later versions do not work yet)
#. pyserial: http://pypi.python.org/pypi/pyserial

I know it is tempting to use easy_install for this. Don't. 
Once all prerequisites are installed, download ACQ4 (stable or development branch):
    
#. Download and install bazaar: http://wiki.bazaar.canonical.com/Download
#. Start a command shell (or powershell or cygwin, if you prefer) and download a copy of the ACQ4 code:
    
::
    
    bzr branch lp:acq4
    
If all goes well, you now have everything ready and can proceed to configuration.




Linux Installation
------------------

Make all your windows-using friends jealous:

::

    $ sudo apt-get install python-qt4 python-pyserial python-scipy python-pyparsing python-h5py bazaar
    $ bzr branch lp:acq4
    
    
OSX Installation
----------------

Ask MBK.
