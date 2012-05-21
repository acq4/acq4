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

Things that crash PyQt4 (of which there are many):
    - Model/View anything. TableView, TreeView, etc. They are too hard to program correctly, and any mistakes lead to untraceable crashing. Use PyQt's modeltest if needed.
    - Changing the bounds of graphicsitems without calling preparegeometrychange first
    - Situations where Qt auto-deletes objects, leaving the python wrapper alive. Make sure you keep references to the objects you want to stay alive, and remove bad references before they cause trouble.
        - joined widgets such as a scrollarea and its scroll bars. When the scrollarea is deleted, the scrollbars go as well, but any references to the scrollbars are NOT informed of this, so accessing those objects causes crash (Pyside does not have this problem)
        - parents auto-deleting children, tree items deleting child widgets when moved
        - GraphicsItems should NEVER keep a reference to the view they live in. (weakrefs are ok)
        - QMenus must not be deleted while they are executing an action (this commonly occurs if you have a 'delete' option in a context menu). Use a timer to delete the menu after exiting the action.
    - As always, be careful with multi-threading. Never access GUI objects outside the main thread. QTimers must only be accessed from the thread which owns them.
    - If graphicsView seems to be involved, try disabling OpenGL
        on 2.6+, OpenGL-enabled graphicsviews can crawl to a halt over time.
    - using QTimer.singleShot repeatedly can cause lockups


PySide: an alternative to PyQt4
    - Not mature yet
    - Developing quickly; may be a viable alternative in the near future..


Installing PyQt with debugging symbols:
---------------------------------------

on Linux:
    
::
    
    apt-get install libqt4-dbg python-qt4-dbg python-dbg
    gdb python
    >>> run acq4.py
        [crash]
    >>> backtrace
    
on Windows:
    Debugging on windows is a rotten pain. My first recommendation is to see if you can reproduce the bug in Linux. There are a few simulated devices that will allow you to use the camera and protocol runner modules on a testing machine. 
    
    If that isn't working out for you, then it's time to compile pyqt with debugging symbols.
    
    - We are going to install PyQt with GDB-style debugging symbols, but _without_ python debugging.
    - Hints: http://www.gubatron.com/blog/2007/02/23/how-to-build-pyqt4-for-windows/
    
    #. Download, install Qt SDK
    #. download sip and pyqt source
    #. unzip to a path with *no* spaces in the full path name
    #. Use Qt's mingw command prompt or VS's command prompt (not cmd, powershell, cygwin..)
    #. If sh is installed via cygwin, it must not be in the PATH during build
    #. set environment variables:  (example below is for mingw builds) ::
        
        > set QTMAKESPEC=win32-g++    (for mingw builds)
        > set QTDIR=C:\QtSDK\Desktop\Qt\4.7.3\mingw
        
    #. configure sip::
            
        > python configure.py -p win32-g++ --debug
        
    #. replace all occurrences of "python2X_d" with "python2X" in all Makefiles (unless you have debugging python installed). A short python script takes care of this::
            
        import os, re
        for path, sd, files in os.walk('.'):
            for f in files:
                if f != 'Makefile':
                    continue
                fn = os.path.join(path, f)
                print fn
                data = open(fn, 'r').readlines()
                fh = open(fn, 'w')
                for line in data:
                    line2 = re.sub(r'python(\d+)_d', 'python\\1', line)
                    fh.write(line2)
                fh.close()
    
    #. run mingw32-make or nmake for VS, but do *not* use cygwin's make. Note that just running mingw32-make install is often allowed, but will fail in this case. ::
            
        > mingw32-make 
        > mingw32-make install
        
    #. After installing, you should have sip_d.pyd. Rename this to sip.pyd
    #. repeat for pyqt source
    #. rename all installed \*_d.pyd files to \*.pyd (c:\\python26\\lib\\site-packages\\pyqt4\...) ::
        
        import os, re, glob
        for f in glob.glob('*_d.pyd'):
            f2 = re.sub('_d', '', f)
            os.rename(f, f2)
            print "%s -> %s" % (f, f2)

    #. This does not install .dll and .exe files. Copy these files from C:\\QtSDK\\Desktop\\Qt\\4.7.3\\mingw. I think DLLS should be in c:\\python26\\Lib\\site-packages\\PyQt4, and EXEs should be in \\bin from there (wherever you put them should be in PATH so windows can find the DLLs). 
    
    
Debugging ACQ4 with GDB
-----------------------

#. Start up::
        
    > gdb python
    ...
    (gdb) run -i acq4.py
        
#. Crash the program. You will not see any crash message immediately; it will appear frozen, but go back to the terminal window, and GDB should say something like this::

    Program received signal SIGSEGV, Segmentation fault.
        
   Alternately, if the program is genuinely frozen, then pressing Ctrl-C should get you back to a GDB prompt.
    
#. Get a backtrace::
    
    (gdb) backtrace
        
   The beginning of the backtrace should offer hints about what was happening when the crash/freeze occurred.
        
There are lots of easy ways you can crash python to test this. Here's one::
    
    from PyQt4 import QtGui
    app = QtGui.QApplication([])
    l = QtGui.QSpinBox().lineEdit()
    l.parent()
    