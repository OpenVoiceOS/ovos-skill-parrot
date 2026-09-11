"""Pytest collection config for the test suite.

The ``test/end2end/`` suite is an ovoscope-driven end-to-end suite that requires
the heavy e2e stack (``ovoscope`` + ``ovos-core[plugins,lgpl]``, which needs
swig/libfann system headers). It is exercised by the dedicated ``ovoscope`` CI
job (``install_extras: 'end2end'`` + ``require_padatious: true``).

The lightweight ``build_tests``/``coverage`` jobs install only the ``test``
extra and scan the whole ``test/`` tree, so without ovoscope present pytest
would error out trying to import the end2end modules. When ovoscope is not
installed we skip collecting that directory entirely so those jobs stay green.
When ovoscope IS installed (the ovoscope job) the directory is collected and the
e2e tests actually run.
"""
from importlib.util import find_spec

collect_ignore_glob = []

if find_spec("ovoscope") is None:
    collect_ignore_glob.append("end2end/*")
