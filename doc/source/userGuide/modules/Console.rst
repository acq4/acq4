.. _userModulesConsole:

Console Module
==============

The Console module provides an interactive Python prompt for development, introspection, and debugging.

    .. figure:: images/console.png

The default namespace for the Console module has three useful objects imported:
    
* **np**: the NumPy library
* **pg**: the PyQtGraph library
* **man**: the ACQ4 central Manager

Example uses
------------

Direct interaction with devices::
    
    clamp = man.getDevice('Clamp1')
    clamp.setMode('vc')
    clamp.setParam('BridgeBalResist',  15e6)

Quick data manipulation::
    
    data = man.getCurrentDir()['Clamp1.ma'].read()
    pri = data['Channel': 'primary'].asarray()
    pg.plot(np.fft(pri))

