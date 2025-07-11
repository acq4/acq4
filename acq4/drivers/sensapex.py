from .. import getManager

try:
    from sensapex import UMP
except ImportError as err:
    msg = "Use of the sensapex driver requires sensapex package to be installed"
    if not err.args:
        err.args = (msg,)
    err.args = err.args + (msg,)
    raise

try:
    from sensapex import __version__
    version_info = tuple(map(int, __version__.split(".")))
except ImportError:
    __version__ = None
    version_info = (0,)


def handle_config(conf):
    for key, val in conf.items():
        if key == "debug":
            UMP.set_debug_mode(val)
        elif key == "driverPath":
            UMP.set_library_path(val)
        elif key == "address":
            UMP.set_default_address(val)
        elif key == "group":
            UMP.set_default_group(val)


handle_config(getManager().config.get("drivers", {}).get("sensapex", {}))
