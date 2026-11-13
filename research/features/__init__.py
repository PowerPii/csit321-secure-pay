"""Shared feature definitions. Only events strictly before the current attempt may be counted.

`gateway_schema` is the offline twin of the gateway's screening features (fs-0.2).
"""
from .gateway_schema import FEATURE_NAMES, FEATURE_SCHEMA_VERSION, Event, replay

__all__ = ["FEATURE_NAMES", "FEATURE_SCHEMA_VERSION", "Event", "replay"]
