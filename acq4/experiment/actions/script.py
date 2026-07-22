"""Script action: loads a .py file fresh on every run and delegates to the single
Action subclass it defines. Import/exec failures surface as ScriptError."""
from __future__ import annotations

import importlib.util
import os
import sys
import uuid

from ..action import Action
from ..registry import register_action
from ..exceptions import ScriptError


@register_action(name="Script")
class ScriptAction(Action):
    # Placeholder until a script is loaded; run() replaces this with the loaded
    # action's own outcomes (they aren't known until load time, by design).
    outcomes = ("done",)
    paramSpec = ({"name": "path", "type": "str", "default": ""},)

    _inner: Action | None = None

    def run(self, ctx):
        action = self._loadAction()
        self._inner = action
        # Expose the loaded script's outcomes so the orchestrator validates and
        # routes on what the inner action actually returns, not the placeholder.
        self.outcomes = tuple(action.outcomes)
        return action.run(ctx)

    def safeAbort(self, ctx) -> None:
        # Delegate unwinding to the inner action loaded by the most recent run().
        if self._inner is not None:
            self._inner.safeAbort(ctx)

    def _loadAction(self) -> Action:
        path = self.paramValue("path")
        # Unique module name each load so edits are always picked up fresh.
        mod_name = f"_acq4_experiment_script_{uuid.uuid4().hex}"
        try:
            # Delete any cached bytecode so file edits are always picked up
            cache_file = importlib.util.cache_from_source(path)
            if os.path.exists(cache_file):
                os.remove(cache_file)

            spec = importlib.util.spec_from_file_location(mod_name, path)
            if spec is None or spec.loader is None:
                raise ScriptError(f"Cannot load script at {path!r}")
            module = importlib.util.module_from_spec(spec)
            # Register the module before execution so the module's own
            # __module__ / introspection (e.g. matching Action subclasses to
            # this module by name) resolves correctly during exec.
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)
        except ScriptError:
            raise
        except Exception as e:  # import/exec errors -> exception state
            raise ScriptError(f"Error loading script {path!r}: {e}") from e
        finally:
            # Clean up the module from sys.modules so it doesn't interfere with future loads
            sys.modules.pop(mod_name, None)

        candidates = [
            obj
            for obj in vars(module).values()
            if isinstance(obj, type)
            and issubclass(obj, Action)
            and obj is not Action
            and obj.__module__ == module.__name__
        ]
        if len(candidates) != 1:
            raise ScriptError(
                f"Script {path!r} must define exactly one Action subclass; "
                f"found {len(candidates)}"
            )
        return candidates[0]()
