from __future__ import annotations
"""Profile repository for loading and saving source profiles to TOML."""


import logging
from pathlib import Path

import rtoml

from multiwebcam.profiles.profile import ControlValue, SourceProfile
from multiwebcam.profiles.settings import AppSettings, InferenceSettings, RecordingSettings

logger = logging.getLogger(__name__)


class ProfileError(Exception):
    """Base exception for profile operations."""


class ProfileParseError(ProfileError):
    """TOML file exists but is malformed."""


class ProfileNotFoundError(ProfileError):
    """Requested profile doesn't exist."""


class ProfileRepository:
    """Load and save source profiles to TOML.

    Operates on a single file: <project_path>/multiwebcam.toml
    Uses rtoml for fast, correct TOML serialization.

    Not thread-safe by design - expected to be used from main thread only.
    """

    def __init__(self, project_path: Path) -> None:
        """Initialize repository.

        Args:
            project_path: Directory containing multiwebcam.toml
        """
        self._project_path = project_path
        self._toml_path = project_path / "multiwebcam.toml"

    def load_all(self) -> list[SourceProfile]:
        """Load all profiles from TOML.

        Returns empty list if file doesn't exist (fresh project).

        Raises:
            ProfileParseError: If file exists but is malformed or missing required fields.
        """
        if not self._toml_path.exists():
            logger.debug(f"No TOML file at {self._toml_path}, returning empty list")
            return []

        try:
            data = rtoml.load(self._toml_path)
        except Exception as e:
            raise ProfileParseError(f"Failed to parse TOML file: {e}") from e

        # Extract sources array
        sources_list = data.get("sources", [])
        if not isinstance(sources_list, list):
            raise ProfileParseError("'sources' must be an array of tables")

        profiles = []
        for i, source_dict in enumerate(sources_list):
            try:
                profile = self._dict_to_profile(source_dict)
                profiles.append(profile)
            except (TypeError, KeyError) as e:
                raise ProfileParseError(f"Invalid source entry at index {i}: {e}") from e

        logger.info(f"Loaded {len(profiles)} profile(s) from {self._toml_path}")
        return profiles

    def save(self, profile: SourceProfile) -> None:
        """Save or update a profile.

        If a profile with the same source_id exists, it's replaced.
        If not, the profile is appended.
        Creates the TOML file if it doesn't exist.

        Args:
            profile: Profile to save
        """
        # Load existing profiles
        profiles = self.load_all()

        # Replace or append
        found = False
        for i, existing in enumerate(profiles):
            if existing.source_id == profile.source_id:
                profiles[i] = profile
                found = True
                break

        if not found:
            profiles.append(profile)

        # Write back
        self._write_all(profiles)
        logger.debug(f"Saved profile source_id={profile.source_id} to {self._toml_path}")

    def load_settings(self) -> AppSettings:
        """Load project-level runtime settings from TOML."""
        data = self._load_raw_data()
        recording_dict = data.get("recording", {})
        inference_dict = data.get("inference", {})

        recording = RecordingSettings(
            backend=recording_dict.get("backend", "pyav"),
            codec=recording_dict.get("codec", "h264"),
            fps=recording_dict.get("fps", 30),
            jetson_encoder=recording_dict.get("jetson_encoder", "nvv4l2h264enc"),
            bitrate=recording_dict.get("bitrate", 8_000_000),
            preset_level=recording_dict.get("preset_level", 1),
            insert_sps_pps=recording_dict.get("insert_sps_pps", True),
            maxperf_enable=recording_dict.get("maxperf_enable", True),
        )

        target_class_ids = inference_dict.get("target_class_ids")
        if target_class_ids is not None:
            target_class_ids = tuple(int(v) for v in target_class_ids)

        inference = InferenceSettings(
            backend=inference_dict.get("backend", "heuristic"),
            engine_path=inference_dict.get("engine_path"),
            device=inference_dict.get("device", 0),
            input_size=tuple(inference_dict.get("input_size", [640, 640])),
            confidence_threshold=float(inference_dict.get("confidence_threshold", 0.25)),
            interval_ms=int(inference_dict.get("interval_ms", 100)),
            target_class_ids=target_class_ids,
            service_conda_env=inference_dict.get("service_conda_env"),
            service_python=inference_dict.get("service_python"),
            service_backend=inference_dict.get("service_backend"),
            service_script=inference_dict.get("service_script"),
        )
        return AppSettings(recording=recording, inference=inference)

    def save_settings(self, settings: AppSettings) -> None:
        """Save project-level runtime settings while preserving sources."""
        data = self._load_raw_data()
        data["recording"] = {
            "backend": settings.recording.backend,
            "codec": settings.recording.codec,
            "fps": settings.recording.fps,
            "jetson_encoder": settings.recording.jetson_encoder,
            "bitrate": settings.recording.bitrate,
            "preset_level": settings.recording.preset_level,
            "insert_sps_pps": settings.recording.insert_sps_pps,
            "maxperf_enable": settings.recording.maxperf_enable,
        }
        inference = {
            "backend": settings.inference.backend,
            "input_size": list(settings.inference.input_size),
            "confidence_threshold": settings.inference.confidence_threshold,
            "interval_ms": settings.inference.interval_ms,
        }
        if settings.inference.engine_path is not None:
            inference["engine_path"] = settings.inference.engine_path
        if settings.inference.device != 0:
            inference["device"] = settings.inference.device
        if settings.inference.target_class_ids is not None:
            inference["target_class_ids"] = list(settings.inference.target_class_ids)
        if settings.inference.service_conda_env is not None:
            inference["service_conda_env"] = settings.inference.service_conda_env
        if settings.inference.service_python is not None:
            inference["service_python"] = settings.inference.service_python
        if settings.inference.service_backend is not None:
            inference["service_backend"] = settings.inference.service_backend
        if settings.inference.service_script is not None:
            inference["service_script"] = settings.inference.service_script
        data["inference"] = inference
        data["sources"] = [self._profile_to_dict(p) for p in self.load_all()]
        self._project_path.mkdir(parents=True, exist_ok=True)
        rtoml.dump(data, self._toml_path)

    def delete(self, source_id: int) -> bool:
        """Delete a profile by source_id.

        Args:
            source_id: Source ID to delete

        Returns:
            True if deleted, False if not found.
        """
        profiles = self.load_all()
        original_count = len(profiles)
        profiles = [p for p in profiles if p.source_id != source_id]

        if len(profiles) < original_count:
            self._write_all(profiles)
            logger.debug(f"Deleted profile source_id={source_id}")
            return True

        return False

    def get_by_bus_info(self, bus_info: str) -> SourceProfile | None:
        """Find profile matching the given bus_info.

        Args:
            bus_info: USB topology identifier

        Returns:
            Matching profile or None if not found.
        """
        profiles = self.load_all()
        for profile in profiles:
            if profile.bus_info == bus_info:
                return profile
        return None

    def get_by_source_id(self, source_id: int) -> SourceProfile | None:
        """Find profile by source_id.

        Args:
            source_id: Source ID

        Returns:
            Matching profile or None if not found.
        """
        profiles = self.load_all()
        for profile in profiles:
            if profile.source_id == source_id:
                return profile
        return None

    def next_source_id(self) -> int:
        """Return next available source_id.

        Returns:
            max(existing_source_ids) + 1, or 0 if no profiles exist.
        """
        profiles = self.load_all()
        if not profiles:
            return 0
        return max(p.source_id for p in profiles) + 1

    def _write_all(self, profiles: list[SourceProfile]) -> None:
        """Write all profiles to TOML file.

        Args:
            profiles: List of profiles to write
        """
        # Build TOML structure
        data = self._load_raw_data()
        data["sources"] = [self._profile_to_dict(p) for p in profiles]

        # Ensure directory exists
        self._project_path.mkdir(parents=True, exist_ok=True)

        # Write to file
        rtoml.dump(data, self._toml_path)

    def _load_raw_data(self) -> dict:
        if not self._toml_path.exists():
            return {}
        try:
            data = rtoml.load(self._toml_path)
        except Exception as e:
            raise ProfileParseError(f"Failed to parse TOML file: {e}") from e
        if not isinstance(data, dict):
            raise ProfileParseError("TOML root must be a table")
        return data

    def _profile_to_dict(self, profile: SourceProfile) -> dict:
        """Convert profile to dict for TOML serialization.

        Omits empty controls dict.
        """
        d = {
            "source_id": profile.source_id,
            "label": profile.label,
            "bus_info": profile.bus_info,
            "ignore": profile.ignore,
            "resolution": list(profile.resolution),  # TOML wants list, not tuple
            "pixel_format": profile.pixel_format,
            "capture_fps": profile.capture_fps,
            "capture_backend": profile.capture_backend,
        }

        if profile.gstreamer_pipeline is not None:
            d["gstreamer_pipeline"] = profile.gstreamer_pipeline

        # Add V4L2 controls as nested dict if any exist
        if profile.controls:
            d["controls"] = {
                name: {"value": cv.value, "min": cv.min, "max": cv.max}
                for name, cv in profile.controls.items()
            }

        return d

    def _dict_to_profile(self, d: dict) -> SourceProfile:
        """Convert dict from TOML to SourceProfile.

        Unknown fields are ignored for forward compatibility.

        Raises:
            KeyError: If required field is missing
            TypeError: If field has wrong type
        """
        # Required fields
        source_id = d["source_id"]
        label = d["label"]
        bus_info = d["bus_info"]

        # Fields with defaults
        ignore = d.get("ignore", False)
        resolution_list = d.get("resolution", [1280, 720])
        resolution = tuple(resolution_list)  # Convert list back to tuple
        pixel_format = d.get("pixel_format", "mjpeg")
        capture_fps = d.get("capture_fps", 30)
        capture_backend = d.get("capture_backend", "opencv_v4l2")
        gstreamer_pipeline = d.get("gstreamer_pipeline")

        # V4L2 controls as dict[str, ControlValue]
        controls = {}
        controls_dict = d.get("controls", {})
        for name, cv_dict in controls_dict.items():
            controls[name] = ControlValue(
                value=cv_dict["value"],
                min=cv_dict["min"],
                max=cv_dict["max"],
            )

        return SourceProfile(
            source_id=source_id,
            label=label,
            bus_info=bus_info,
            ignore=ignore,
            resolution=resolution,
            pixel_format=pixel_format,
            capture_fps=capture_fps,
            capture_backend=capture_backend,
            gstreamer_pipeline=gstreamer_pipeline,
            controls=controls,
        )
