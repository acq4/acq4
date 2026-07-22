"""Tests for Protocol JSON (de)serialization round-trips."""
from acq4.experiment.protocol import Protocol


def _sample_protocol(recording_cls):
    a = recording_cls(name="a", params={"next": "left"})
    b = recording_cls(name="b")
    handler = Protocol(
        nodes={"h": recording_cls(name="h")}, edges={}, entry="h"
    )
    return Protocol(
        nodes={"a": a, "b": b},
        edges={("a", "left"): "b"},
        entry="a",
        publicParams=[{"node": "a", "param": "next", "public": "First branch"}],
        exceptionHandlers={"Exception": handler},
    )


def test_to_dict_shape(recording_cls):
    d = _sample_protocol(recording_cls).to_dict()
    assert d["version"] == 1
    assert d["entry"] == "a"
    assert d["nodes"]["a"] == {"type": "Recording", "params": {"next": "left"}}
    assert {"from": "a", "outcome": "left", "to": "b"} in d["edges"]
    assert d["publicParams"][0]["public"] == "First branch"
    assert d["exceptionHandlers"]["Exception"]["entry"] == "h"


def test_round_trip_in_memory(recording_cls):
    p = _sample_protocol(recording_cls)
    p2 = Protocol.from_dict(p.to_dict())
    assert p2.entry == "a"
    assert p2.next_node("a", "left") == "b"
    assert p2.nodes["a"].paramValue("next") == "left"
    assert p2.publicParams == p.publicParams
    assert p2.handler_for("Exception").entry == "h"


def test_round_trip_json_file(tmp_path, recording_cls):
    p = _sample_protocol(recording_cls)
    path = tmp_path / "proto.json"
    p.save_json(str(path))
    loaded = Protocol.load_json(str(path))
    assert loaded.next_node("a", "left") == "b"
    assert loaded.nodes["b"].name == "b"
