Installation
============

ACQ4 depends on several free software packages to work properly. In most cases, these packages are easiest to install using
the Anaconda python distribution (see below):
    
* Python 2.7
* numpy
* scipy
* PyQt
* h5py
* pillow

These are the minimal requirements to run ACQ4 (eg, for data analysis). For data acquisition, there are extra requirements:
    
* pyparsing
* pyserial (only if using serial devices--Sutter MP285, arduino, serial mice, etc)

You also need to make sure that the drivers for your devices are installed and working properly. 


Windows / OSX Installation
--------------------

For Windows and OSX we recommend using the Anaconda python distribution because it contains prebuilt packages
satisfying nearly all dependencies of ACQ4.

* Most users will begin by installing the 64-bit, Python 2.7 version of Anaconda (https://www.continuum.io/downloads)
  The Installer will ask whether to add Anaconda to the PATH environment variable; we recommend _enabling_ this option
  for the 64-bit install although it is not strictly required.

* If you have a device for which only 32-bit drivers are available (such as MultiClamp or P.I. X-Keys), then you
  will need to install the 32-bit, Python 2.7 Anaconda as well. 
  The Installer will ask whether to add Anaconda to the PATH environment variable; we recommend _disabling_ this option
  for the 32-bit install.

* ACQ4 depends on PyQt4, but the more recent versions of Aanconda (starting with 4.2.0) ship with PyQt5 by default. It is necessary to downgrade this package:

            > conda install pyqt=4

* If you require access to a serial device (Scientifica, Coherent, Sutter, etc.) then you must manually install the `pyserial`
  module using pip or conda:

            > pip install pyserial

* Install git (www.git-scm.com) and then clone the acq4 git repository. This downloads all current code into a new directory called
  `acq4`::
        
            > git clone https://github.com/acq4/acq4.git
            
* To start ACQ4, run ``python -m acq4`` from the source directory, or install with ``python setup.py install``


Linux Installation
------------------

Linux users may use Anaconda as described above, or install the python dependencies from their distribution's package manager. For example::

    $ sudo apt-get install python-qt4 python-qt4-gl python-qt4-sql python-pyserial\
      python-scipy python-pyparsing python-h5py python-imaging python-opengl git
    
Next, clone the ACQ4 code::
    
    $ git clone https://github.com/acq4/acq4.git

Or if you prefer, install from pypi (these packages lag behind the current development code)::

    $ sudo pip install acq4
    
If you wish to develop modules / devices / analysis, you will probably need a few more packages: qt4-designer pyqt4-dev-tools

To start ACQ4, run::
    
    $ python -m acq4
    
