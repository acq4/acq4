"""Single accessor for the model paths in the rig's global ``misc`` config.

Keeps detection and tracking on the same cellpose checkpoint: they segment the
same tissue and disagree badly when they do not.
"""

_UNSET = object()


def segmenter_path(manager=_UNSET):
    """Path to the cellpose checkpoint this rig is configured to segment with.

    Returns None when nothing is configured, which leaves cellpose on its stock
    model. *manager* defaults to the running Manager, and None is an accepted
    answer rather than an error: a headless or partly-configured rig has no
    Manager and no configured model, and both mean the same thing here.
    """
    if manager is _UNSET:
        # Manager.single rather than getManager(), which raises when nothing is
        # running -- that is the unconfigured case, not a failure.
        from acq4.Manager import Manager

        manager = Manager.single
    if manager is None:
        return None
    return (manager.config.get("misc") or {}).get("segmenterPath")
