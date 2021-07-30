try:
    from sensapex import UMP
except ImportError as err:
    msg = "Use of the sensapex driver requires sensapex package to be installed"
    if not err.args:
        err.args = (msg,)
    err.args = err.args + (msg,)
    raise
