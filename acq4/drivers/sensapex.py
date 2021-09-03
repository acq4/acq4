from .. import getManager

try:
    from sensapex import UMP
except ImportError as err:
    msg = "Use of the sensapex driver requires sensapex package to be installed"
    if not err.args:
        err.args = (msg,)
    err.args = err.args + (msg,)
    raise


def handle_config(conf):
    for key, val in conf.items():
        if key == "debug":
            UMP.set_debug_mode(val)
        elif key == "driverPath":
            UMP.set_library_path(val)


handle_config(getManager().config.get("drivers", {}).get("sensapex", {}))
