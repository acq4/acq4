"""Tests for WebcamCamera device enumeration and naming.

Covers the pure description-formatting and de-duplication helpers plus the
name-based selection logic. A hardware integration test runs against any real
camera present on the machine and is skipped when none is attached.
"""

from __future__ import annotations

import pytest

from acq4.devices.WebcamCamera.webcam_camera import WebcamCamera

# --- description formatting -------------------------------------------------


def test_format_uses_card_with_manufacturer_and_ids():
    rec = {
        "index": 0,
        "card": "FHD Camera: FHD Camera",
        "manufacturer": "SunplusIT Inc",
        "product": "FHD Camera",
        "vendor_id": "5986",
        "product_id": "213a",
        "serial": "01.00.00",
        "bus_info": "usb-0000:00:14.0-1",
    }
    desc = WebcamCamera._format_device_description(rec)
    assert desc.startswith("FHD Camera: FHD Camera")
    assert "SunplusIT Inc" in desc
    assert "[5986:213a]" in desc
    assert "[serial:01.00.00]" in desc
    assert "[usb-0000:00:14.0-1]" in desc


def test_format_does_not_duplicate_manufacturer_already_in_label():
    rec = {"index": 1, "card": "Logitech Webcam C920", "manufacturer": "Logitech"}
    desc = WebcamCamera._format_device_description(rec)
    # manufacturer is already part of the label; should not be appended again
    assert desc.count("Logitech") == 1


def test_format_falls_back_to_manufacturer_product_then_index():
    assert WebcamCamera._format_device_description(
        {"index": 2, "manufacturer": "Acme", "product": "EyeCam"}
    ).startswith("Acme EyeCam")
    # nothing identifying at all -> stable "Camera N" label
    assert WebcamCamera._format_device_description({"index": 3}) == "Camera 3"


def test_format_omits_missing_fields():
    desc = WebcamCamera._format_device_description({"index": 0, "card": "Some Cam"})
    assert desc == "Some Cam"


# --- de-duplication ---------------------------------------------------------


def test_dedupe_numbers_identical_descriptions_in_index_order():
    devices = [(0, "Acme EyeCam"), (2, "Acme EyeCam"), (1, "Other Cam")]
    out = dict(WebcamCamera._dedupe_device_descriptions(devices))
    assert out[1] == "Other Cam"  # unique name untouched
    assert out[0] == "Acme EyeCam #1"  # lowest index gets #1
    assert out[2] == "Acme EyeCam #2"


def test_dedupe_leaves_unique_descriptions_unchanged():
    devices = [(0, "Cam A"), (1, "Cam B")]
    assert WebcamCamera._dedupe_device_descriptions(devices) == devices


# --- name-based selection ---------------------------------------------------


def _patch_devices(monkeypatch, devices):
    monkeypatch.setattr(WebcamCamera, "_enumerate_devices", staticmethod(lambda: devices))


def test_find_by_name_substring_case_insensitive(monkeypatch):
    _patch_devices(
        monkeypatch,
        [
            (0, "FHD Camera: FHD Camera by SunplusIT Inc [5986:213a]"),
            (2, "FHD Camera: FHD IR Camera by SunplusIT Inc [5986:213a]"),
        ],
    )
    assert WebcamCamera._findCameraByName("ir camera") == 2
    assert WebcamCamera._findCameraByName("5986:213a") == 0  # first match wins


def test_find_by_name_raises_with_device_list(monkeypatch):
    _patch_devices(monkeypatch, [(0, "FHD Camera")])
    with pytest.raises(ValueError) as exc:
        WebcamCamera._findCameraByName("nonexistent")
    assert "FHD Camera" in str(exc.value)


# --- hardware integration (skipped when no camera attached) -----------------


def test_real_enumeration_reports_identifiable_names():
    pytest.importorskip("cv2")
    devices = WebcamCamera._enumerate_devices()
    if not devices:
        pytest.skip("no camera attached")
    # every entry is (int index, non-empty descriptive string)
    for idx, desc in devices:
        assert isinstance(idx, int)
        assert isinstance(desc, str) and desc.strip()
    # descriptions must be unique after de-duplication
    descs = [d for _, d in devices]
    assert len(descs) == len(set(descs))
