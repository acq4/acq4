Debugging
=========


Python debugging and IDEs
-------------------------

We use Wing IDE Pro, many have also recommended Eric and Elipse + PyDev
All of these options offer a comprehensive set of debugging features.


Memory Leaks
------------

debug library has some tools for tracking down memory leaks:
    ObjTracker
    GarbageWatcher



Lockups, bus errors, segmentation faults
----------------------------------------

Things that crash PyQt4:
    - Model/View anything. TableView, TreeView, etc. They are too hard to program correctly, and any mistakes lead to untraceable crashing.
    - Changing the bounds of graphicsitems without calling preparegeometrychange first
    - Situations where Qt auto-deletes objects, leaving the python wrapper alive.
    (make sure you keep references to the objects you want to stay alive, and remove bad references before they cause trouble)
        - joined widgets such as a scrollarea and its scroll bars. When the scrollarea is deleted, the scrollbars go as well, but any references to the scrollbars are NOT informed of this, so accessing those objects causes crash (Pyside does not have this problem)
        - parents auto-deleting children, tree items deleting child widgets when moved
        - GraphicsItems should NEVER keep a reference to the view they live in. (weakrefs are ok)
    - As always, be careful with multi-threading. Never access GUI objects outside the main thread.
    - If graphicsView seems to be involved, try disabling OpenGL
        on 2.6+, OpenGL-enabled graphicsviews can crawl to a halt over time.
    - using QTimer.singleShot repeatedly can cause lockups


PySide: an alternative to PyQt4
    - Not mature yet
    - Developing quickly; may be a viable alternative in the near future..


Installing PyQt with debugging symbols:
    on Linux:
        apt-get install libqt4-dbg python-qt4-dbg python-dbg
        gdb python
        >>> run acq4.py
          [crash]
        >>> backtrace
        
    on Windows:
        Hints: http://www.gubatron.com/blog/2007/02/23/how-to-build-pyqt4-for-windows/
        Download, install Qt SDK
        download sip and pyqt source
        unzip to a path _with no spaces in the full path name_
        Use Qt's mingw command prompt or VS's command prompt (not cmd, powershell, cygwin..)
        - If sh is installed via cygwin, it must not be in the PATH during build
        - set QTMAKESPEC=win32-g++ (for mingw builds)
        - make sure QTDIR is set correctly as well (for me, it is C:\QtSDK\Desktop\Qt\4.7.3\mingw, but this may depend on your build environment.)
        - configure sip: 
            python configure.py -p win32-g++ --debug
        - replace "python26_d" with "python26" in all Makefiles
          (unless you can figure out how to get python26_d)
        - mingw32-make (or nmake for VS) install  (don't use cygwin's make)
        - Now configure without --debug and rebuild.
        - repeat for pyqt source
        - rename all installed *_d.pyd files to *.pyd (c:\python26\lib\site-packages\pyqt4\...)
        Note: this installs .dll and .exe files in the wrong location. (I think DLLS should be in /python26/Lib/site-packages/PyQt4, and EXEs should be in /bin from there)
    
