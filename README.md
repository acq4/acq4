ACQ4
====

Neurophysiology acquisition and analysis for Python

Copyright 2013 Luke Campagnola, University of North Carolina at Chapel Hill

<http://www.acq4.org>


Contributors
------------

  * Luke Campagnola   ('luke.campagnola@%s.com' % 'gmail')
  * Megan Kratz
  * Paul Manis
  * Antonin Blot
  * Michael Graupner

Requirements
------------

  * python 2.7
  * PyQt 4.9+
  * numpy, scipy
  * h5py
  * optional:
      * pyopengl
      * pyserial
      * pyparsing
      * pillow



Documentation
-------------

http://www.acq4.org/documentation


Support
-------

Post at the [mailing list / forum](https://groups.google.com/forum/?fromgroups#!forum/acq4)


Installation
------------


Windows
'''''''

There are two basic methods of installing ACQ4 on windows:

1. Download one of the .exe installers from acq4.org; these contain a complete python distribution with all of the packages listed below. This is the quickest way to get running if you do not plan on developing new code within ACQ4.

2. Prepare a complete python distribution. This is preferred if you plan to develop new code within ACQ4. All packages must match the version (2.7) and architecture (32 or 64bit) of the python version to be installed.

	* Download and install packages in order:
	    * Python 2.7 (www.python.org/download)
	    * PyQt4 4.10 (www.riverbankcomputing.com/software/pyqt/download)
	    * NumPy-MKL 1.7 (http://www.lfd.uci.edu/~gohlke/pythonlibs/)
	    * SciPy 0.13 (http://www.lfd.uci.edu/~gohlke/pythonlibs/)
	    * h5py 2.2 (http://www.lfd.uci.edu/~gohlke/pythonlibs/)
	    * Pillow 2.3 (http://www.lfd.uci.edu/~gohlke/pythonlibs/)
	    * pyserial 2.7 (http://www.lfd.uci.edu/~gohlke/pythonlibs/)
	    * PyOpenGL 3.0 (http://www.lfd.uci.edu/~gohlke/pythonlibs/)
	    * PyParsing 2.0 (http://www.lfd.uci.edu/~gohlke/pythonlibs/)
    * Install git (www.git-scm.com), then clone the acq4 repository: `git cone https://github.com/acq4/acq4.git`
    * Run `python -m acq4` from the source directory, or install with `python setup.py install`


Linux, OSX
''''''''''

1. Install git and all required python packages via your distribution's package manager. On OSX, we recommend homebrew. For example::

```bash
       $ sudo apt-get install git python-numpy python-scipy python-h5py\
         python-pillow python-opengl python-qt4 python-pyserial python-pyparsing
```

2. Clone the ACQ4 source repository::

```bash
       $ git clone https://github.com/acq4/acq4.git`
```

3. Run `python -m acq4` from the source directory, or install with `python setup.py install` and run using `acq4`.


