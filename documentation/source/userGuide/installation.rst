Installation
============

ACQ4 depends on several free software packages to work properly.
    
    #. Python 2.6
    #. Numpy
    #. Scipy
    #. PyQt 4.x  (PySide support in development)

These are the minimal requirements to run ACQ4 (eg, for data analysis). For data acquisition, there are extra requirements:
    
    #. pyparsing
    #. pyserial (only if using serial devices--Sutter MP285, serial mice, etc)
    
You also need to make sure that the drivers for your devices are installed and working properly. 

Windows Installation
--------------------

1. Download Python 2.7 from python.org and install.
2. Download PyQt4 from http://www.riverbankcomputing.co.uk/software/pyqt/download and install. Be sure to get the version built for python 2.7.
3. Download Numpy and Scipy from http://scipy.org/Download, install. (look for the 'superpack' files for python 2.7)
4. Edit path to include c:\python27 and c:\python27\scripts
5. Download pypasring version 1.5.2 (later versions do not work yet)
6. Download pyserial

I know it is tempting to use easy_install for this. Don't. 
Once all prerequisites are installed, download ACQ4 (stable or development branch) 


Linux Installation
------------------

Make all your windows-using friends jealous:

::

    $ sudo apt-get install python-qt4 python-pyserial python-scipy python-pyparsing
    
    
OSX Installation
----------------

Ask MBK.
