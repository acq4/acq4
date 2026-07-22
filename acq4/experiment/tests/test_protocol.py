"""Tests for the Protocol graph model (routing and handler lookup)."""
from acq4.experiment.protocol import Protocol


def test_next_node_follows_edge(recording_cls):
    a, b = recording_cls(name="a"), recording_cls(name="b")
    p = Protocol(nodes={"a": a, "b": b},
                 edges={("a", "done"): "b"},
                 entry="a")
    assert p.next_node("a", "done") == "b"


def test_next_node_missing_edge_returns_none(recording_cls):
    p = Protocol(nodes={"a": recording_cls(name="a")}, edges={}, entry="a")
    assert p.next_node("a", "done") is None


def test_edges_can_merge(recording_cls):
    # two outcomes route to the same downstream node
    p = Protocol(
        nodes={"a": recording_cls(name="a"), "c": recording_cls(name="c")},
        edges={("a", "left"): "c", ("a", "right"): "c"},
        entry="a",
    )
    assert p.next_node("a", "left") == "c"
    assert p.next_node("a", "right") == "c"


def test_handler_for_exact_and_fallback():
    catch_all = Protocol(entry="h")
    specific = Protocol(entry="hb")
    p = Protocol(exceptionHandlers={"Exception": catch_all,
                                    "BrokenPipette": specific})
    assert p.handler_for("BrokenPipette") is specific
    assert p.handler_for("Fouled") is catch_all  # falls back to catch-all


def test_handler_for_none_when_no_handlers():
    assert Protocol().handler_for("Exception") is None
