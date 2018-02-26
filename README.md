ACQ4
====

Neurophysiology acquisition and analysis for Python

<http://www.acq4.org>

ACQ4 is a platform for data acquisition, management, and analysis in neurophysiology
experiments, especially focusing on patch clamp electrophysiology, optogenetics, 
and related techniques. It is used both as a platform for developing customized
data acquisition tools and as an application that handles the most common
requirements in whole-cell recording, calcium imaging, and photostimulation.


Requirements
------------

  * python 2.7
  * PyQt 4.9+
  * numpy, scipy
  * six
  * h5py
  * optional:
      * pyopengl
      * pyserial
      * pyparsing 2.0.3  (later versions do not work)
      * pillow


Documentation
-------------

http://www.acq4.org/documentation


Support
-------

Post at the [mailing list / forum](https://groups.google.com/forum/?fromgroups#!forum/acq4)


Installation
------------


The easiest way to get all of the requirements is by installing the Anaconda
python distribution plus a few extra packages. 

1. Download and install [Anaconda](https://www.anaconda.com/download/) for python 2.7 (64-bit recommended)

2. Install the correct versions of a few packages:

```bash
       $ conda install pyserial pyqt=4 pyparsing=2.0.3
```

3. Clone the ACQ4 source repository::

```bash
       $ git clone https://github.com/acq4/acq4.git
```

4. Run `python -m acq4` from the source directory, or install with `python setup.py install` and run using `acq4`.


