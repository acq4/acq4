"""Seal-stage mutators."""

from .base import ProfileParamMutator


class SealTimeout(ProfileParamMutator):
    name = "seal_timeout"
    unit = "cell"
    params = {"seal": "autoSealTimeout"}
    conditions = [30.0, 60.0]
