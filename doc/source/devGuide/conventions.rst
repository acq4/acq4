Coding Conventions
==================

Code style
----------

Naming, name collisions
-----------------------

Logging
-------

ACQ4 uses JSON-formatted logging:

.. code-block:: python

    from acq4.logging_config import get_logger

    logger = get_logger(__name__)
    logger.info("Operation started", extra={'device': 'Camera1'})

Logs stream to JSON for structured analysis. The GUI log window supports real-time monitoring.
Module loggers follow the pattern ``acq4.device.ModuleName.DeviceName``.