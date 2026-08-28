"""Allow ``python -m agent_trust`` as well as the ``agent-trust`` console script.

The console script depends on a generated ``.exe`` shim being on PATH, which is
not always true on a fresh shell -- and on Windows machines with Application
Control it may be blocked outright. ``python -m`` needs neither.
"""

from __future__ import annotations

from agent_trust.cli import app

if __name__ == "__main__":
    app()
