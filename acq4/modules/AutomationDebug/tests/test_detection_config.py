"""Tests for AutomationDebug health-model config reading.

Cover that _health_model_config pulls the model paths and score cutoffs from the
global ``misc`` config and defaults each to None when unset.
"""

from types import SimpleNamespace

from acq4.modules.AutomationDebug.detection import _health_model_config


def test_health_model_config_reads_misc():
    manager = SimpleNamespace(
        config={
            "misc": {
                "segmenterPath": "/s",
                "autoencoderPath": "/a",
                "classifierPath": "/c",
                "resnetClassifierPath": "/r",
                "scoreCutoffs": [0.1, 0.2, 0.3, 0.4, 0.5],
            }
        }
    )
    assert _health_model_config(manager) == {
        "segmenter": "/s",
        "autoencoder": "/a",
        "classifier": "/c",
        "resnet_classifier": "/r",
        "score_cutoffs": [0.1, 0.2, 0.3, 0.4, 0.5],
    }


def test_health_model_config_defaults_to_none():
    manager = SimpleNamespace(config={})
    assert _health_model_config(manager) == {
        "segmenter": None,
        "autoencoder": None,
        "classifier": None,
        "resnet_classifier": None,
        "score_cutoffs": None,
    }
