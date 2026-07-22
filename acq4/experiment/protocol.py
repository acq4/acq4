"""Protocol: an outcome-routed directed graph of Actions, with exception-handler
sub-protocols. Serialization is added alongside JSON I/O."""
from __future__ import annotations

from .action import Action


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
