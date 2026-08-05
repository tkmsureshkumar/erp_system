# Imported automatically by Python's site module at process startup.
# Patches GZipResponder.__init__ so Streamlit's gzip middleware works
# with Starlette >=0.41 which added thread_minimum_size as a required kwarg.
try:
    import inspect as _inspect
    import starlette.middleware.gzip as _sgzip

    _p = _inspect.signature(_sgzip.GZipResponder.__init__).parameters
    if (
        "thread_minimum_size" in _p
        and _p["thread_minimum_size"].default is _inspect.Parameter.empty
    ):
        _orig = _sgzip.GZipResponder.__init__

        def _patched(self, app, minimum_size, *, compresslevel=9, thread_minimum_size=None, **kw):
            _orig(
                self, app, minimum_size,
                compresslevel=compresslevel,
                thread_minimum_size=minimum_size if thread_minimum_size is None else thread_minimum_size,
                **kw,
            )

        _sgzip.GZipResponder.__init__ = _patched

    del _inspect, _sgzip, _p
except Exception:
    pass
