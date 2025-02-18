"""Support for Synology DSM cameras."""
from __future__ import annotations

from dataclasses import dataclass
import logging

from synology_dsm.api.surveillance_station import SynoCamera, SynoSurveillanceStation
from synology_dsm.exceptions import (
    SynologyDSMAPIErrorException,
    SynologyDSMRequestException,
)

from homeassistant.components.camera import (
    Camera,
    CameraEntityDescription,
    CameraEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import SynoApi
from .const import (
    CONF_SNAPSHOT_QUALITY,
    COORDINATOR_CAMERAS,
    DEFAULT_SNAPSHOT_QUALITY,
    DOMAIN,
    SIGNAL_CAMERA_SOURCE_CHANGED,
    SYNO_API,
)
from .entity import SynologyDSMBaseEntity, SynologyDSMEntityDescription

_LOGGER = logging.getLogger(__name__)


@dataclass
class SynologyDSMCameraEntityDescription(
    CameraEntityDescription, SynologyDSMEntityDescription
):
    """Describes Synology DSM camera entity."""


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Synology NAS cameras."""

    data = hass.data[DOMAIN][entry.unique_id]
    api: SynoApi = data[SYNO_API]

    if SynoSurveillanceStation.CAMERA_API_KEY not in api.dsm.apis:
        return

    # initial data fetch
    coordinator: DataUpdateCoordinator[dict[str, dict[str, SynoCamera]]] = data[
        COORDINATOR_CAMERAS
    ]
    await coordinator.async_config_entry_first_refresh()

    async_add_entities(
        SynoDSMCamera(api, coordinator, camera_id)
        for camera_id in coordinator.data["cameras"]
    )


class SynoDSMCamera(SynologyDSMBaseEntity, Camera):
    """Representation a Synology camera."""

    _attr_supported_features = CameraEntityFeature.STREAM
    coordinator: DataUpdateCoordinator[dict[str, dict[str, SynoCamera]]]
    entity_description: SynologyDSMCameraEntityDescription

    def __init__(
        self,
        api: SynoApi,
        coordinator: DataUpdateCoordinator[dict[str, dict[str, SynoCamera]]],
        camera_id: str,
    ) -> None:
        """Initialize a Synology camera."""
        description = SynologyDSMCameraEntityDescription(
            api_key=SynoSurveillanceStation.CAMERA_API_KEY,
            key=camera_id,
            name=coordinator.data["cameras"][camera_id].name,
            entity_registry_enabled_default=coordinator.data["cameras"][
                camera_id
            ].is_enabled,
        )
        self.snapshot_quality = api._entry.options.get(
            CONF_SNAPSHOT_QUALITY, DEFAULT_SNAPSHOT_QUALITY
        )
        super().__init__(api, coordinator, description)
        Camera.__init__(self)

    @property
    def camera_data(self) -> SynoCamera:
        """Camera data."""
        return self.coordinator.data["cameras"][self.entity_description.key]

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information."""
        return DeviceInfo(
            identifiers={
                (
                    DOMAIN,
                    f"{self._api.information.serial}_{self.camera_data.id}",
                )
            },
            name=self.camera_data.name,
            model=self.camera_data.model,
            via_device=(
                DOMAIN,
                f"{self._api.information.serial}_{SynoSurveillanceStation.INFO_API_KEY}",
            ),
        )

    @property
    def available(self) -> bool:
        """Return the availability of the camera."""
        return self.camera_data.is_enabled and self.coordinator.last_update_success

    @property
    def is_recording(self) -> bool:
        """Return true if the device is recording."""
        return self.camera_data.is_recording  # type: ignore[no-any-return]

    @property
    def motion_detection_enabled(self) -> bool:
        """Return the camera motion detection status."""
        return self.camera_data.is_motion_detection_enabled  # type: ignore[no-any-return]

    def _listen_source_updates(self) -> None:
        """Listen for camera source changed events."""

        @callback
        def _handle_signal(url: str) -> None:
            if self.stream:
                _LOGGER.debug("Update stream URL for camera %s", self.camera_data.name)
                self.stream.update_source(url)

        assert self.platform
        assert self.platform.config_entry
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_CAMERA_SOURCE_CHANGED}_{self.platform.config_entry.entry_id}_{self.camera_data.id}",
                _handle_signal,
            )
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to signal."""
        self._listen_source_updates()

    def camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return bytes of camera image."""
        _LOGGER.debug(
            "SynoDSMCamera.camera_image(%s)",
            self.camera_data.name,
        )
        if not self.available:
            return None
        try:
            return self._api.surveillance_station.get_camera_image(self.entity_description.key, self.snapshot_quality)  # type: ignore[no-any-return]
        except (
            SynologyDSMAPIErrorException,
            SynologyDSMRequestException,
            ConnectionRefusedError,
        ) as err:
            _LOGGER.debug(
                "SynoDSMCamera.camera_image(%s) - Exception:%s",
                self.camera_data.name,
                err,
            )
            return None

    async def stream_source(self) -> str | None:
        """Return the source of the stream."""
        _LOGGER.debug(
            "SynoDSMCamera.stream_source(%s)",
            self.camera_data.name,
        )
        if not self.available:
            return None

        return self.camera_data.live_view.rtsp  # type: ignore[no-any-return]

    def enable_motion_detection(self) -> None:
        """Enable motion detection in the camera."""
        _LOGGER.debug(
            "SynoDSMCamera.enable_motion_detection(%s)",
            self.camera_data.name,
        )
        self._api.surveillance_station.enable_motion_detection(
            self.entity_description.key
        )

    def disable_motion_detection(self) -> None:
        """Disable motion detection in camera."""
        _LOGGER.debug(
            "SynoDSMCamera.disable_motion_detection(%s)",
            self.camera_data.name,
        )
        self._api.surveillance_station.disable_motion_detection(
            self.entity_description.key
        )
