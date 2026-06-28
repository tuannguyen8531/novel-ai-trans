"""Application-layer entry points.

Workflows in this package are pure Python functions that accept typed
request objects, return typed results, and never print, call :func:`sys.exit`,
or install signal handlers. CLI and API adapters delegate to these
workflows so behavior is identical across interfaces.

Each long-running workflow accepts:

- ``progress_callback``: optional callable receiving :class:`ProgressEvent`
- ``cancel_event``: optional :class:`threading.Event` for cooperative cancel
"""

from __future__ import annotations
