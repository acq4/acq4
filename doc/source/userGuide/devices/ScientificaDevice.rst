.. _ScientificaDevice:

Scientifica
===========

.. currentmodule:: acq4.devices.Scientifica

.. autoclass:: Scientifica
    :members:
    :undoc-members:
    :show-inheritance:


Zero Offset Calibration
-----------------------

Scientifica devices track position internally relative to a hardware zero point, which is retained
across power cycles. It only needs to be re-established if a motor has slipped or was physically
rotated while powered off.

Two buttons in the device's Manager dock control this:

* **"Zero position"**: Declares the current position to be zero on all axes.
* **"Auto-set zero position"**: Drives each axis to its mechanical limit switch and sets that as
  zero. Per-axis variants ("Auto-set X/Y/Z zero") are also available. A confirmation dialog
  appears before any movement begins.

Consistency between ``axisScale``, ``autoZeroDirection``, and ``limits``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Three configuration values must be self-consistent:

1. **``params -> axisScale``**: Absolute value is set by the manufacturer and should not be
   changed. The *sign* determines which physical direction of motion corresponds to positive
   position values. The Scientifica default gives +Z = downward (toward the sample). On some
   devices the sign cannot be changed.

2. **``autoZeroDirection``** (default ``(-1, -1, -1)``): The direction each axis is driven when
   auto-zeroing — ``-1`` drives toward very negative position, ``+1`` toward very positive.
   Choose the value that sends each axis toward a **safe** limit switch (one where an unobstructed
   move is guaranteed). After zeroing, that limit switch becomes position 0.

3. **``limits``**: Software-enforced (min, max) position range in **device position coordinates**
   (micrometers, the same units returned by ``getPosition()`` — *not* meters). After zeroing, one
   end of the range is 0 (at the zero limit switch) and the other end is the signed travel distance
   in µm. Positions slightly outside the configured range near the physical limit switches are
   normal.

Example
~~~~~~~

With the Scientifica default (+Z = downward), the top of travel is in the negative direction.
``autoZeroDirection[Z] = -1`` drives upward to the top limit switch (Z = 0); the full downward
range is then positive::

    autoZeroDirection: -1, -1, -1
    limits:
        z: 0, 20000    # µm (= 20 mm of downward travel)

If the sign of ``axisScale[Z]`` is flipped so that +Z = upward, the top of travel is in the
positive direction and ``autoZeroDirection[Z] = +1`` is needed; the full downward range is then
negative::

    autoZeroDirection: -1, -1, 1
    limits:
        z: -20000, 0    # µm
