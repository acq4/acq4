Introduction
============

How Difficult Will It Be?
-------------------------

In part, you get to decide. ACQ4 has many layers of abstraction frameworks, but you aren't required to use any of them. 
Many services provided by the ACQ4 can simply be imported into other existing applications.


Where Should I Start?
---------------------

First: Ask! No reason to start off in the wrong direction.

*The very-short answer:* If you want to add support for a device, read the devices section. If you want to add new experimental functionality, consider writing a module (module section) or adding new functionality to protocolrunner (link). If you want to add new analysis, read the analysis section.

*The very-long answer:* When developing new functionality for ACQ4, it is important to remember that ACQ4 is a _platform_ that provides many commonly used services to the developer. However, some of these services are only available within the context of a specific framework. I will attempt to make this very abstract statement somewhat more concrete with specific examples. 

Let's say you just bought a shiny new imaging device and you'd like to integrate it into ACQ4. You're probably hoping to:
    * Control the device from within ACQ4
    * Use the device synchronously with other devices managed by ACQ4
    * Store data from the device along with data from other devices
    
There are a few approaches you could take to accomplish these goals:
    * Write a new Module which exclusively controls the device
    * Write a new Device class, allowing ACQ4 to do some automated control of the device
    * Write a new Camera subclass, allowing ACQ4 to have (perhaps) fully automatic control 
    
Each approach has benefits and drawbacks. Writing a new module has probably the lowest learning curve, since this approach takes advantage of very few of the services offered through ACQ4 (and thus the programmer needs very little ACQ4-specific programming knowledge). A module is, put most simply, just another program that can be launched from the ACQ4 manager window. There are virtually no restrictions on the way a module must look or operate. So why write a module within ACQ4 at all? Modules do benefit from a few important services: 
    * Modules can request that ACQ4 run acquisition protocols using any combination of devices that support the protocol interface. For example, you may want to operate your device from the module while simultaneously controlling and recording from a MultiClamp amplifier. Rather than write your own MultiClamp support, it is much easier to simply ask ACQ4 to handle this for you.
    * Modules can request that data be stored in standard locations with meta-data. Asking ACQ4 to do your data storage and retrieval for you helps ensure that your data is stored in a way that is consistent with the rest of ACQ4 and will be readily accessible when doing analysis.
    * Modules can communicate directly with other modules or devices. Any code running within ACQ4 may request access to another Device (see Manager.getDevice) or Module (see Manager.getModule) 
    
So we see that by operating within the ACQ4 framework, some useful services become available. If we go one step deeper, we might decide to create a Device class that encapsulates control of the device. The immediate benefit to this approach is that the device may become available for previously-existing modules to use. For example, if the new Device class implements the protocol interface, then it can be included by any other module in ACQ4's acquisition protocols. If it implements the ProtocolRunner interface, it can be operated from within the Protocol Runner, possibly obviating the need for a new module altogether. Implementing a new Device class is likely to be a much more powerful and flexible approach; however, this may come with somewhat more complex programming requirements.

Finally, we might discover that nearly everything we want to do with our new hardware is very similar to ACQ4's existing camera functionality. In this case, it would be best to implement a Device class that is also a subclass of Camera (which is itself a subclass of Device). By doing so, we can use our new hardware in the existing camera module and we get all of the pre-written device interfaces for free. This is a vastly simpler task than implementing a completely new Device. The drawback is that it may become more difficult to use the device in ways not originally supported by the generic Camera class.

To reiterate: there are a variety of options for adding new functionality to ACQ4 (only a few of which were covered here). Lower-level frameworks (such as Module) are generally easier to program at first, but higher-level frameworks, although they have a steeper learning curve, may offer power, flexibility, and features that were difficult to achieve otherwise. As always, the best place to start may be to ask the core developers for advice.
