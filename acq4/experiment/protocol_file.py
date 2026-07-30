"""ProtocolFile: wraps a single .py protocol file, importing it fresh on each
load() to extract its run() function, PARAMS spec, and module docstring."""
from __future__ import annotations

import importlib.util
import os
import sys
import uuid
from pathlib import Path
from typing import Callable

from pyqtgraph.parametertree import Parameter


class ProtocolLoadError(Exception):
    """Raised when a protocol .py file fails to import or does not define run()."""


class ProtocolFile:
    """A single .py protocol file: a module-level `run(ctx, **params)` and an
    optional `PARAMS` list (a pyqtgraph Parameter children spec).

    `load()` (re-)imports the file fresh each time, so an operator's edit is
    always picked up. `name` is the filename stem and is available before the
    first load, so the UI can list a protocol even if it fails to import.
    """

    def __init__(self, path: str):
        self.path = path
        self.name = Path(path).stem
        self.description = ""
        self.params: list[dict] = []
        self.run: Callable | None = None
        self.param_tree: Parameter | None = None
        self.is_loaded = False
        self.load_error: str | None = None

    def load(self) -> None:
        # Unique module name each load so edits are always picked up fresh; the
        # module is never cached in sys.modules across loads.
        mod_name = f"_acq4_protocol_{uuid.uuid4().hex}"
        try:
            # Delete any cached bytecode so file edits are always picked up.
            cache_file = importlib.util.cache_from_source(self.path)
            if os.path.exists(cache_file):
                os.remove(cache_file)

            spec = importlib.util.spec_from_file_location(mod_name, self.path)
            if spec is None or spec.loader is None:
                raise ProtocolLoadError(f"Cannot load protocol at {self.path!r}")
            module = importlib.util.module_from_spec(spec)
            # Register the module before execution so the module's own
            # __module__ introspection (e.g. dataclass's ClassVar/InitVar
            # detection under `from __future__ import annotations`, or pickle)
            # resolves correctly during exec.
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)

            run = getattr(module, "run", None)
            if not callable(run):
                raise ProtocolLoadError(f"Protocol {self.path!r} has no run() function")

            params = list(getattr(module, "PARAMS", []))
            description = (module.__doc__ or "").strip()
            # Build the tree before touching instance state, so a rejected
            # PARAMS spec leaves the previously-loaded run/params/description/
            # param_tree fully intact rather than mixed with the new run().
            param_tree = self._build_tree(params)

            self.run = run
            self.params = params
            self.description = description
            self.param_tree = param_tree
            self.is_loaded = True
            self.load_error = None
        except ProtocolLoadError as e:
            self.is_loaded = False
            self.load_error = str(e)
            raise
        except Exception as e:  # import/exec errors -> ProtocolLoadError
            self.is_loaded = False
            self.load_error = str(e)
            raise ProtocolLoadError(f"Error loading protocol {self.path!r}: {e}") from e
        finally:
            # Clean up the module from sys.modules so it doesn't interfere with
            # future loads.
            sys.modules.pop(mod_name, None)

    @staticmethod
    def _build_tree(params: list[dict]) -> Parameter:
        children = []
        for p in params:
            child = dict(p)
            # pyqtgraph reads these from two different opts keys: 'tip' sets
            # the tooltip on the value widget (basetypes.py's
            # WidgetParameterItem.updateWidget), while 'tooltip' sets it on
            # the name column (ParameterItem.__init__). A protocol author
            # only writes 'tip', so mirror it onto 'tooltip' here unless the
            # author set 'tooltip' explicitly.
            if "tip" in child and "tooltip" not in child:
                child["tooltip"] = child["tip"]
            children.append(child)
        return Parameter.create(name="params", type="group", children=children)

    def param_values(self) -> dict:
        if self.param_tree is None:
            return {}
        return {child.name(): child.value() for child in self.param_tree.children()}
