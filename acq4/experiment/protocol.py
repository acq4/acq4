"""Protocol: an outcome-routed directed graph of Actions, with exception-handler
sub-protocols. Serialization is added alongside JSON I/O."""
from __future__ import annotations

from .action import Action
import json

from .registry import get_action_class, action_type_name


class Protocol:
    """A directed graph of Actions.

    nodes:  {node_id: Action}
    edges:  {(node_id, outcome): target_node_id}   -- merges (many->one) allowed
    entry:  node_id of the first action, or None
    publicParams: [{"node": id, "param": name, "public": public_name}, ...]
    exceptionHandlers: {typeName: Protocol}         -- each handler is a sub-Protocol
    """

    version = 1

    def __init__(self, nodes=None, edges=None, entry=None,
                 publicParams=None, exceptionHandlers=None):
        self.nodes: dict[str, Action] = dict(nodes or {})
        self.edges: dict[tuple[str, str], str] = dict(edges or {})
        self.entry: str | None = entry
        self.publicParams: list[dict] = list(publicParams or [])
        self.exceptionHandlers: dict[str, "Protocol"] = dict(exceptionHandlers or {})

    def next_node(self, node_id: str, outcome: str) -> str | None:
        """The node reached by `outcome` from `node_id`, or None if the branch ends."""
        return self.edges.get((node_id, outcome))

    def handler_for(self, exc_type_name: str) -> "Protocol | None":
        """Handler protocol for an exception type, falling back to the catch-all."""
        return self.exceptionHandlers.get(exc_type_name) or self.exceptionHandlers.get(
            "Exception"
        )

    # ---- serialization ----
    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "entry": self.entry,
            "nodes": {
                nid: {"type": action_type_name(a), "params": _param_values(a)}
                for nid, a in self.nodes.items()
            },
            "edges": [
                {"from": f, "outcome": o, "to": t}
                for (f, o), t in self.edges.items()
            ],
            "publicParams": self.publicParams,
            "exceptionHandlers": {
                k: p.to_dict() for k, p in self.exceptionHandlers.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Protocol":
        nodes = {}
        for nid, ndata in data.get("nodes", {}).items():
            action_cls = get_action_class(ndata["type"])
            nodes[nid] = action_cls(name=nid, params=ndata.get("params", {}))
        edges = {(e["from"], e["outcome"]): e["to"] for e in data.get("edges", [])}
        handlers = {
            k: cls.from_dict(v) for k, v in data.get("exceptionHandlers", {}).items()
        }
        return cls(
            nodes=nodes,
            edges=edges,
            entry=data.get("entry"),
            publicParams=data.get("publicParams", []),
            exceptionHandlers=handlers,
        )

    def save_json(self, path: str) -> None:
        with open(path, "w") as fh:
            json.dump(self.to_dict(), fh, indent=2)

    @classmethod
    def load_json(cls, path: str) -> "Protocol":
        with open(path) as fh:
            return cls.from_dict(json.load(fh))


def _param_values(action: Action) -> dict:
    return {
        spec["name"]: action.paramValue(spec["name"])
        for spec in type(action).paramSpec
    }
