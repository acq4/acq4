Modules
=======

Contents:

.. toctree::
    :maxdepth: 2
    
    Manager
    DataManager
    Camera
    Patch
    TaskRunner
    Imager
    Console

What is a Module?
-----------------

In short, a module is an almost-totally independent program which is launched by ACQ4 and has access to any of the services offered by ACQ4. Modules are free to do virtually anything they like--there are very few constraints on their code structure, behavior, appearance, etc. If the task you are trying to accomplish does not fit nicely into the existing modules, then it may be time to write a new one. 

How to Build a New Module
-------------------------

#. Create a new python module or package containing a subclass of acq4.modules.Module.Module. This should look something like::
    
    from acq4.modules.Module import Module
    
    class NewModuleClass(Module):

        # Optionally, indicate how the module will be described in the
        # Manager's menu of loadable modules:
        moduleDisplayName = "My New Module"
        moduleCategory = "Acquisition"

#. Define your class's ``__init__`` method::

   When ACQ4 instantiates your module, it will pass in three arguments:
   
   * manager - a reference to the Manager that created the module. This object provides lots of useful services like getDevice(), getModule(), getCurrentDir(), and createTask().
   * name - the name assigned to this module. This helps to differentiate multiple instances of the same module class.
   * config - an arbitrary and optional configuration structure (usually a dict) that provides the module any other instantiation data it needs.

   So your module should now look something like::
    
    class NewModuleClass(Module):
        moduleDisplayName = "My New Module"
        moduleCategory = "Acquisition"
        def __init__(self, manager, name, config):
            Module.__init__(self, manager, name, config)  ## call superclass __init__
            ...

#. Make sure your module is being imported. There are a few ways to do this.

   If you prefer to start ACQ4 directly (for example, by running ``python -m acq4``), then configure it to load your code
   at startup (see :ref:`userConfigurationStructure`)::

        # Option 1: add to the top of your default config file if your module is _importable_ (that is, if you 
        # expect calling `import my_module` from inside of ACQ4 to work correctly)
        imports: ['my_module']

        # Option 2: you can ask ACQ4 to directly exec() your code if it is not importable:
        execFiles: ['/path/to/my_file.py']

   Option 3: all modules that are found inside ``acq4/modules`` are automatically imported. If you think that your module should
   live inside ACQ4's directory structure rather than in a separate repository, then this is a good option.

   Option 4: If you are _not_ running ACQ4 directly (for example, you have your own main script from which you are importing acq4), then
   you are free to ensure that your module classes are imported any way you like.

#. If your module creates a Qt window, give the module a window() method that returns a reference to the window. This allows ACQ4 to assign window keyboard shortcuts::

    def window(self):
        return self._win

#. Optional: create a quit() method. This will be called when ACQ4 is quitting, allowing the module to clean up if needed.

#. Optional: create a default configuration (or many) for loading your module. In the 'modules' section of your configuration files, add a new section that looks like::
    
    My New Module:                 # Name that will appear in the manager window's menu of modules
        module: 'NewModuleClass'   # Name of the class to load
        config:
            ...  (data here will be passed to the config 
            ...  argument when instantiating the class)
            
   Each section like this that you create adds a new entry to the main Manager window, allowing users to easily access the module.
   By changing the contents of the 'config' section, it is possible to allow multiple instances of the module to be loaded with different settings.
