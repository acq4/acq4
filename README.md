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

  * python 3.7
  * PyQt 5+
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

1. Download and install [Anaconda](https://www.anaconda.com/download/) or [Miniconda](https://docs.conda.io/en/latest/miniconda.html) for python 2.7 (64-bit recommended)

2. Create a conda environment for acq4 (windows users must do this from the anaconda prompt):

    ```bash
    conda create --name=acq4 python=3.7 pyqt=5 numpy scipy pyserial pyparsing pillow h5py
    conda activate acq4
    ```

3. Add latest version of pyqtgraph:

    ```bash
    pip install git+https://github.com/pyqtgraph/pyqtgraph@master#egg=pyqtgraph
    ```

4. Clone the ACQ4 source repository (this requires [git](https://git-scm.com/downloads) to be installed):

    ```bash
    git clone https://github.com/acq4/acq4.git
    ```

5. Install acq4 into your new conda environment:

    ```bash
    cd acq4
    python setup.py develop
    ```

Starting ACQ4
-------------

Activate your acq4 conda environment, then start acq4:

```bash
conda activate acq4
python -m acq4
```

This should load the main manager window, from which you can interact with some devices and load modules. 
