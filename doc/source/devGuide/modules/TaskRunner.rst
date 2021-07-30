.. _devModulesTaskRunner:

Task Runner Module
==================


Architecture
------------

* Dock system
* Task execution thread

Device Interfaces
-----------------

Any device may implement a Task Runner interface that provides the user a graphical interface for controlling that device from the Task Runner. The basic API for this interface is defined in the TaskGui base class (acq4/devices/Device.py).



.. _devModulesTaskRunnerAnalysis:

Online Analysis
---------------


The Task Runner provides a plugin interface for developing :ref:`online analysis <userModulesTaskRunnerAnalysis>` modules. The basic API for this interface is defined in the AnalysisModule base class (acq4/modules/TaskRunner/analysisModules/AnalysisModule.py). The task runner generates its list of available modules by searching the `acq4/modules/TaskRunner/analysisModules` directory for importable modules. Each module must define a subclass of AnalysisModule. 
    
Example 1: we can create a very simple analysis module that prints the data structures collected by the task runner:
    
    #. Create a directory `acq4/modules/TaskRunner/analysisModules/TestAnalysis/`
    #. Create a new file `acq4/modules/TaskRunner/analysisModules/TestAnalysis/__init__.py`
    #. Within this file, define a subclass of AnalysisModule::
        
           from ..AnalysisModule import AnalysisModule
           from pprint import pprint
           
           class TestAnalysisModule(AnalysisModule):
               def newFrame(self, data):
                   print("== Received new task results ==")
                   pprint(data)

    #. Start up ACQ4, load a TaskRunner, and then check "TestAnalysis". An empty dock will appear (we did not define
       a user interface), and running the task will cause information about the task to be printed on the console. 
    
