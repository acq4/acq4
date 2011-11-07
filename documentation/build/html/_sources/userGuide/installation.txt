Installation
============

ACQ4 depends on several free software packages to work properly.
    
* Python 2.7
* Numpy
* Scipy
* PyQt 4.8
* h5py

These are the minimal requirements to run ACQ4 (eg, for data analysis). For data acquisition, there are extra requirements:
    
* pyparsing
* pyserial (only if using serial devices--Sutter MP285, arduino, serial mice, etc)
    
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
#. Python Imaging Library: http://www.pythonware.com/products/pil/

I know it is tempting to use easy_install or cygwin for this. Don't. 
Once all prerequisites are installed, download ACQ4 (stable or development branch):
    
#. Download and install bazaar: http://wiki.bazaar.canonical.com/Download
#. Start a command shell (or powershell or cygwin, if you prefer) and download a copy of the ACQ4 code::
    
    bzr branch lp:acq4
    
If all goes well, you now have everything ready and can proceed to configuration.




Linux Installation
------------------

Make all your windows-using friends jealous::

    $ sudo apt-get install python-qt4 python-qt4-gl python-qt4-gl python-pyserial python-scipy python-pyparsing python-h5py python-imaging bzr
    $ bzr branch lp:acq4
    
    
OSX Installation
----------------

#. Download Qt SDK (see code.activestate.com/pypm/pyqt4 for a link to their recommended qt version)
#. Download ActiveState Python (free community edition)
#. run::
    pypm install pyqt4 pyparsing h5py numpy scipy pil
#. If you get a complaint about 64-bit compatibility, run python in 32-bit mode (see manpage)

    
#. Optional:
    - find uic executable by::
        pypm files pyqt4 | grep pyuic
    - Add correct directory PATH
    - Edit pyuic4 to point correctly to pyuic.py



OSX Alternate Installation Method
---------------------------------

These instructions are for building on MacOSX 10.5. If you're building on 10.6 or 10.7 some of these libraries will be available as binaries. 

You will need to have xcode installed on your machine.

Download and install the following packages in order:
    
#. **Python 2.7**: http://python.org (available as a dmg)
#. **Bazaar**: http://wiki.bazaar.canonical.com/Download (This needs to be done before installing Qt/PyQt)
#. | **Qt 4.7**: http://qt.nokia.com 
   | Unfortunately the SDK installation does not work on 10.5 - But installing the libraries should be fine. 
   | The libraries are available as dmg
   
#. | **SIP** (I used 4.12.3): http://www.riverbankcomputing.com/software/sip/download.
   | From the SIP directory in a Terminal:
       
   ::

        $ python configure.py
        $ make
        $ make install
        
#. | **PyQt4**: http://www.riverbankcomputing.co.uk/software/pyqt/download
   | Be sure to get the version built for python 2.7 and the Qt version you installed.
   | In a terminal navigate to the PyQt4 folder:
       
   ::
        
        $ python configure.py
        $ make
        $ make install
        
#. | **Numpy**: http://numpy.scipy.org
   | Make sure you get the version for python 2.7, this may involve searching through files instead of simply getting the latest version.
   | I use numpy 1.6.0 which is available as a .dmg
#. | **Scipy**: http://numpy.scipy.org
   | Same deal as numpy, I used scipy 0.9.0
#. **ZLib**: http://zlib.net ::

            $ ./configure
            $ make test
            $ sudo make install
            
#. | **Python Imaging Library (PIL)**: http://www.pythonware.com/products/pil
   | Get the PIL-1.1.7.tar.gz package.
   | Unpack it and in Terminal navigate to the PIL folder and:
       
   ::

        $ python setup.py install
        
#. **PyParsing**: http://pyparsing.wikispaces.com ::

        $ python setup.py install
        
#. | **HDF5**: http://www.hdfgroup.org/HDF5
   | Download the source code (I used version 1.8.7).
   | Unpack it and navigate to the folder in terminal 
   
   ::

        $ ./configure --prefix=/usr/local/hdf5
        $ make
        $ make check           # If check succeeds, go on..
        $ sudo make install
        $ make check-install
        
#. | **h5py**: http://code.google.com/p/h5py
   | I use version 1.3.1.
   | Navigate to the folder in terminal and:
       
   ::

        $ python setup.py build --hdf5=/usr/local/hdf5
        $ python setup.py install
        
#. Finally, navigate to the place where you would like to store acq4. ::

        $ bzr branch lp:acq4
        
That's it, you're done and ready to setup configuration files.