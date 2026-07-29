"""Ask the operator to confirm they're ready.
Hardware-free demo protocol."""
from acq4.experiment.actions import prompt

PARAMS = [{"name": "message", "type": "str", "default": "Ready to patch this cell?"}]


def run(ctx, message="Ready to patch this cell?"):
    prompt(ctx, message=message)
