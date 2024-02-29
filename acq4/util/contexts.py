from contextlib import ExitStack


def maybe(possible_context) -> ExitStack:
    """Convenience function to allow for optional context managers to be non-evaluated. Usage::

    with maybe(some_test() and some_context_manager()):
        # do something that only wants the context manager if some_test() is True
    """
    context = ExitStack()
    if possible_context:
        context.enter_context(possible_context)
    return context


if __name__ == "__main__":
    from contextlib import suppress
    with maybe(True and suppress(Exception)):
        raise RuntimeError("This should not be raised")
    with maybe(False and suppress(Exception)):
        raise RuntimeError("This should be raised")
