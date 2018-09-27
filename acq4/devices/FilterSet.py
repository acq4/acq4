from .OptomechDevice import OptomechDevice
from .Device import Device


class FilterSet(Device, OptomechDevice):
    """Represents an optical filter or filter set.

    This device class has two main purposes:  (1) Providing access to metadata
    about filters in the optical path between a light source and the sample. 
    (2) Providing access to metadata about filters in the optical path between
    an imaging device and the sample.

    FilterSets may be simple pass-through optics like an ND filter placed in front of
    a light source, or they may have multiple beam paths like in a dichroic filter cube.

    For swappable filters, see the FilterWheel class.

    Configuration examples::

        Blue_Filter:
            Driver: "FilterSet"
            name: "Blue"
            description: "A combination blue bandpass and ND filter"
            optics:
                # order of filters always starts with closest-to-sample
                0:
                    model: "Semrock FF01-474/27"
                    passBands: ([460, 490])
                1:
                    model: "Unknown ND filter"
                    transmission: 0.13

        EGFP_FilterCube:
            driver: "FilterSet"
            name: "EGFP"
            description: "Epifluorescence filter cube for EGFP (blue excitation / green emission)"
            ports:  # filter cube has two ports for attaching children: excitation and emission

                # note: order of filters always starts with closest-to-sample, regardless of
                # whether this is an excitation or emission path
                excitation:  
                    0:
                        model: "Semrock FF506-Di03 (reflected)"
                        passBands: [(None, 505*nm)]  # reflects wavelengths < 505 nm
                    1:
                        model: "Semrock FF02-485/20"
                        passBands: [(473*nm, 498*nm)]  # transmits 473-498 nm
                emission:
                    0:
                        model: "Semrock FF506-Di03 (transmitted)"
                        passBands: [(505, None)]  # transmits wavelengths > 505 nm
                    1:
                        model: "Semrock FF01-524/24"
                        passBands: [(510*nm, 540*nm)]  # transmits 510-540 nm

    """
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)

        self.config = config

        # build config for optomechdevice
        omconfig = config.copy()
        optics = omconfig.pop('optics', {})
        ports = omconfig.pop('ports', {})
        if len(optics) > 0:
            assert 'default' not in ports, "Config cannot have both `optics` and `ports: default`"
            ports['default'] = optics

        omconfig['ports'] = list(ports.keys())

        # Ports can either be specified like:
        #    {'first_port': [{optic1}, {optic2}, ...], 'second_port': [...]}
        # or like:
        #    {'first_port': {0: {optic1}, 1: {optic2}, ...}, 'second_port': {...}}
        # (the second form is easier to write out in config files)
        for p, optics in ports.items():
            if isinstance(optics, list):
                continue
            elif isinstance(optics, dict):
                # convert {0:x, 1:y} dict to list
                keys = sorted(list(optics.keys()))
                assert len(set(keys)) == int(keys[-1]) + 1, "Optics dict must have contiguous integer keys; got: %r" % keys
                ports[p] = [optics[k] for k in keys]
            else:
                raise TypeError("Optics must be described by a list or a dict; got: %r" % optics)

        omconfig['optics'] = ports

        OptomechDevice.__init__(self, dm, omconfig, name)

    def description(self):
        return self._config.get('description')
