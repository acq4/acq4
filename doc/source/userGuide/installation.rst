Installation
============

ACQ4 depends on several free software packages to work properly. In most cases, these packages are easiest to install using the Anaconda python distribution:

1. Download and install `Anaconda <https://www.anaconda.com/download/>`_ or `Miniconda <https://docs.conda.io/en/latest/miniconda.html>`_.

2. Clone the ACQ4 source repository (this requires `git <https://git-scm.com/downloads>`_ to be installed)::

    git clone https://github.com/acq4/acq4.git
    cd acq4

3. Create a conda environment for acq4 (windows users must do this from the anaconda prompt)::

    conda env create --name=acq4 --file=tools/requirements/qt5-generic.yml
    conda activate acq4

4. Install acq4 into your new conda environment::

    python setup.py develop


Improving performance with GPU
------------------------------

ACQ4 can use nVidia GPUs to improve performance if the `cupy` python package is installed. See the `cupy documentation <https://docs.cupy.dev/en/stable/install.html>`_ for more information on configuring CUDA and cupy correctly.

If you have a CUDA-supported GPU, this is highly recommended.

Starting ACQ4
-------------

Activate your acq4 conda environment, then start acq4::

    conda activate acq4
    python -m acq4

This should load the main manager window, from which you can interact with some devices and load modules.


Legacy Python 2 support
-----------------------

For systems that still require python 2 support, the ``python2`` git branch contains the most recent ACQ4 version known to support python 2. More information can be found in the README for that branch: https://github.com/acq4/acq4/tree/python2
