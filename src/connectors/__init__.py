"""Data source connectors.

Every connector exposes a single ``fetch`` function that returns a
dictionary of pandas DataFrames. When credentials or configuration are
missing the connector returns an empty dict so the rest of the pipeline can
still run.
"""

from __future__ import annotations
