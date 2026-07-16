from __future__ import annotations
"""Source profile persistence system.

Provides SourceProfile dataclass and ProfileRepository for saving/loading
source configurations to TOML files.
"""

from multiwebcam.profiles.profile import ControlValue, SourceProfile
from multiwebcam.profiles.repository import ProfileError, ProfileNotFoundError, ProfileParseError, ProfileRepository
from multiwebcam.profiles.settings import AppSettings, InferenceSettings, RecordingSettings

__all__ = [
    "SourceProfile",
    "ControlValue",
    "AppSettings",
    "InferenceSettings",
    "ProfileRepository",
    "ProfileError",
    "ProfileParseError",
    "ProfileNotFoundError",
    "RecordingSettings",
]
