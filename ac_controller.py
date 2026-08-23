"""Async communication controller for a Midea-compatible air conditioner.

Designed for Midea-compatible type-0xAC devices. The React/pywebview desktop
interface imports this module; it intentionally contains no presentation-layer
code or manufacturer-specific branding.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp
import keyring
from dotenv import dotenv_values, load_dotenv, set_key, unset_key
from keyring.errors import PasswordDeleteError
from midea_beautiful import (
    appliance_state as beautiful_appliance_state,
    connect_to_cloud as beautiful_connect_to_cloud,
)
from midealocal.cloud import (
    SUPPORTED_CLOUDS,
    get_default_cloud,
    get_midea_cloud,
    get_preset_account_cloud,
)
from msmart.device import AirConditioner
from msmart.device.AC.command import GetGroupDataCommand, Group4Response, StateResponse
from msmart.discover import Discover


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
APP_DATA_DIRECTORY = "AirConControl"
CREDENTIAL_SERVICE_PREFIX = "AirCon Control"


def _configuration_file() -> Path:
    """Return a writable config path without ever bundling user secrets."""

    override = os.getenv("AIRCON_CONTROL_CONFIG_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve() / ".env"
    base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
    if not base:
        base = str(Path.home() / "AppData" / "Local")
    return Path(base) / APP_DATA_DIRECTORY / ".env"


ENV_FILE = _configuration_file()
ENV_FILE.parent.mkdir(parents=True, exist_ok=True)


def _credential_service(account_cloud: str) -> str:
    return f"{CREDENTIAL_SERVICE_PREFIX} - {account_cloud}"


def _stored_cloud_password(account: str, account_cloud: str) -> str:
    """Read a cloud password from the current Windows user's credential vault."""

    if not account:
        return ""
    try:
        return keyring.get_password(_credential_service(account_cloud), account) or ""
    except Exception:
        # A legacy plaintext value or process environment variable may still
        # allow startup. New saves fail explicitly instead of weakening storage.
        return ""


def _store_cloud_password(account: str, account_cloud: str, password: str) -> None:
    try:
        keyring.set_password(_credential_service(account_cloud), account, password)
    except Exception as exc:
        raise RuntimeError(
            "Windows Credential Manager could not save the cloud password."
        ) from exc


def _delete_cloud_password(account: str, account_cloud: str) -> None:
    if not account:
        return
    try:
        keyring.delete_password(_credential_service(account_cloud), account)
    except PasswordDeleteError:
        pass
    except Exception as exc:
        raise RuntimeError(
            "Windows Credential Manager could not remove the cloud password."
        ) from exc


def _remove_plaintext_password() -> None:
    """Remove the retired plaintext setting after secure storage succeeds."""

    if ENV_FILE.exists() and "MSMART_PASSWORD" in dotenv_values(ENV_FILE):
        unset_key(ENV_FILE, "MSMART_PASSWORD")
    os.environ.pop("MSMART_PASSWORD", None)


def _load_cloud_password(
    account: str, account_cloud: str, file_values: dict[str, Any]
) -> tuple[str, str | None]:
    """Load from Credential Manager and migrate a legacy .env password once."""

    stored = _stored_cloud_password(account, account_cloud)
    legacy = str(file_values.get("MSMART_PASSWORD") or "")
    if stored:
        if legacy:
            _remove_plaintext_password()
        return stored, "Windows Credential Manager"
    if legacy and account:
        try:
            _store_cloud_password(account, account_cloud, legacy)
        except RuntimeError:
            return legacy, "Legacy local configuration"
        _remove_plaintext_password()
        return legacy, "Windows Credential Manager"
    environment_password = os.getenv("MSMART_PASSWORD", "")
    return environment_password, "Process environment" if environment_password else None


def reload_configuration() -> None:
    """Reload settings after the desktop setup screen writes them."""

    file_values = dict(dotenv_values(ENV_FILE))
    load_dotenv(ENV_FILE, override=True)
    global MSMART_ACCOUNT, MSMART_PASSWORD, PASSWORD_STORAGE
    global MSMART_REGION, MIDEA_ACCOUNT_CLOUD
    global DEVICE_IP, DEVICE_PORT, DEVICE_ID, DEVICE_TOKEN, DEVICE_KEY
    global DISCOVERY_TARGET
    global WEATHER_LOCATION_ENABLED, WEATHER_LATITUDE, WEATHER_LONGITUDE
    MSMART_ACCOUNT = os.getenv("MSMART_ACCOUNT", "").strip()
    MSMART_REGION = os.getenv("MSMART_REGION", "DE").strip().upper() or "DE"
    MIDEA_ACCOUNT_CLOUD = (
        os.getenv("MIDEA_ACCOUNT_CLOUD", "NetHome Plus").strip()
        or "NetHome Plus"
    )
    MSMART_PASSWORD, PASSWORD_STORAGE = _load_cloud_password(
        MSMART_ACCOUNT, MIDEA_ACCOUNT_CLOUD, file_values
    )
    DEVICE_IP = os.getenv("MIDEA_DEVICE_IP", "").strip()
    try:
        DEVICE_PORT = int(os.getenv("MIDEA_DEVICE_PORT", "6444"))
    except ValueError:
        DEVICE_PORT = 6444
    DEVICE_ID = os.getenv("MIDEA_DEVICE_ID", "").strip()
    DEVICE_TOKEN = os.getenv("MIDEA_DEVICE_TOKEN", "").strip()
    DEVICE_KEY = os.getenv("MIDEA_DEVICE_KEY", "").strip()
    # msmart-ng's portable default works across ordinary IPv4 subnets.
    DISCOVERY_TARGET = (
        os.getenv("MIDEA_DISCOVERY_TARGET", "255.255.255.255").strip()
        or "255.255.255.255"
    )
    WEATHER_LOCATION_ENABLED = os.getenv(
        "AIRCON_WEATHER_LOCATION_ENABLED", "true"
    ).strip().lower() not in {"0", "false", "no", "off"}
    try:
        latitude = float(os.getenv("AIRCON_WEATHER_LATITUDE", ""))
        longitude = float(os.getenv("AIRCON_WEATHER_LONGITUDE", ""))
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError
        WEATHER_LATITUDE = latitude
        WEATHER_LONGITUDE = longitude
    except (TypeError, ValueError):
        WEATHER_LATITUDE = None
        WEATHER_LONGITUDE = None


reload_configuration()

DISCOVERY_TIMEOUT_SECONDS = 7
ENERGY_REFRESH_SECONDS = 60


def weather_configuration() -> dict[str, Any]:
    """Return the non-secret weather-location preference for the local UI."""

    location = None
    if (
        WEATHER_LOCATION_ENABLED
        and WEATHER_LATITUDE is not None
        and WEATHER_LONGITUDE is not None
    ):
        location = {
            "latitude": WEATHER_LATITUDE,
            "longitude": WEATHER_LONGITUDE,
        }
    return {
        "weather_location_enabled": WEATHER_LOCATION_ENABLED,
        "weather_location": location,
    }


def configuration_summary() -> dict[str, Any]:
    """Return setup values without exposing saved passwords, tokens, or keys."""

    return {
        "account": MSMART_ACCOUNT,
        "has_password": bool(MSMART_PASSWORD),
        "signed_in": bool(MSMART_ACCOUNT and MSMART_PASSWORD),
        "password_storage": PASSWORD_STORAGE,
        "region": MSMART_REGION,
        "account_cloud": MIDEA_ACCOUNT_CLOUD,
        "account_clouds": list(SUPPORTED_CLOUDS),
        "device_ip": DEVICE_IP,
        "device_port": DEVICE_PORT,
        "device_id": DEVICE_ID,
        "has_local_credentials": bool(DEVICE_TOKEN and DEVICE_KEY),
        "discovery_target": DISCOVERY_TARGET,
        "configured": bool(
            (MSMART_ACCOUNT and MSMART_PASSWORD)
            or (DEVICE_ID and DEVICE_TOKEN and DEVICE_KEY)
        ),
        **weather_configuration(),
    }


def save_weather_configuration(values: dict[str, Any]) -> dict[str, Any]:
    """Persist the user's weather choice and an approximate device location."""

    enabled = bool(values.get("enabled", False))
    latitude = values.get("latitude")
    longitude = values.get("longitude")
    if enabled and latitude is not None and longitude is not None:
        try:
            latitude = round(float(latitude), 3)
            longitude = round(float(longitude), 3)
        except (TypeError, ValueError) as exc:
            raise ValueError("Weather coordinates must be numeric.") from exc
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError("Weather coordinates are outside the valid range.")
    else:
        latitude = None
        longitude = None

    settings = {
        "AIRCON_WEATHER_LOCATION_ENABLED": "true" if enabled else "false",
        "AIRCON_WEATHER_LATITUDE": "" if latitude is None else f"{latitude:.3f}",
        "AIRCON_WEATHER_LONGITUDE": "" if longitude is None else f"{longitude:.3f}",
    }
    ENV_FILE.touch(exist_ok=True)
    for name, value in settings.items():
        set_key(ENV_FILE, name, value, quote_mode="always")
    reload_configuration()
    return weather_configuration()


def save_user_configuration(values: dict[str, Any]) -> dict[str, Any]:
    """Validate and persist settings supplied by the desktop setup screen."""

    current = configuration_summary()
    previous_account = current["account"]
    previous_cloud = current["account_cloud"]
    account = str(values.get("account", current["account"])).strip()
    password = str(values.get("password", ""))
    if not password and account == previous_account:
        password = MSMART_PASSWORD
    if not account:
        password = ""
    elif not password:
        raise ValueError("Enter the password for the selected cloud account.")

    region = str(values.get("region", current["region"])).strip().upper()
    account_cloud = str(
        values.get("account_cloud", current["account_cloud"])
    ).strip()
    device_ip = str(values.get("device_ip", current["device_ip"])).strip()
    device_id = str(values.get("device_id", current["device_id"])).strip()
    discovery_target = str(
        values.get("discovery_target", current["discovery_target"])
    ).strip() or "255.255.255.255"
    try:
        device_port = int(values.get("device_port", current["device_port"]))
    except (TypeError, ValueError) as exc:
        raise ValueError("Device port must contain digits only.") from exc
    if not 1 <= device_port <= 65535:
        raise ValueError("Device port must be between 1 and 65535.")
    if device_id and not device_id.isdigit():
        raise ValueError("Device ID must contain digits only.")
    if region not in {"DE", "US", "KR"}:
        raise ValueError("Account region must be DE, US, or KR.")
    if account_cloud not in SUPPORTED_CLOUDS:
        raise ValueError("Select a supported Midea account app.")

    token = str(values.get("device_token", "")).strip()
    key = str(values.get("device_key", "")).strip()
    clear_local = bool(values.get("clear_local_credentials", False))
    id_changed = device_id != current["device_id"]
    if clear_local or (id_changed and not token and not key):
        token = ""
        key = ""
    elif not token and not key:
        token = DEVICE_TOKEN
        key = DEVICE_KEY
    if bool(token) != bool(key):
        raise ValueError("Provide both the local token and key, or neither.")

    weather_enabled = bool(
        values.get("weather_location_enabled", current["weather_location_enabled"])
    )
    clear_weather_location = bool(
        values.get("refresh_weather_location", False)
    ) or not weather_enabled
    saved_weather = current["weather_location"]
    weather_latitude = (
        ""
        if clear_weather_location or not saved_weather
        else f"{saved_weather['latitude']:.3f}"
    )
    weather_longitude = (
        ""
        if clear_weather_location or not saved_weather
        else f"{saved_weather['longitude']:.3f}"
    )

    settings = {
        "MSMART_ACCOUNT": account,
        "MSMART_REGION": region,
        "MIDEA_ACCOUNT_CLOUD": account_cloud,
        "MIDEA_DEVICE_IP": device_ip,
        "MIDEA_DEVICE_PORT": str(device_port),
        "MIDEA_DEVICE_ID": device_id,
        "MIDEA_DEVICE_TOKEN": token,
        "MIDEA_DEVICE_KEY": key,
        "MIDEA_DISCOVERY_TARGET": discovery_target,
        "AIRCON_WEATHER_LOCATION_ENABLED": "true" if weather_enabled else "false",
        "AIRCON_WEATHER_LATITUDE": weather_latitude,
        "AIRCON_WEATHER_LONGITUDE": weather_longitude,
    }
    if account:
        _store_cloud_password(account, account_cloud, password)
    ENV_FILE.touch(exist_ok=True)
    for name, value in settings.items():
        set_key(ENV_FILE, name, value, quote_mode="always")
    _remove_plaintext_password()
    if previous_account and (
        previous_account != account or previous_cloud != account_cloud
    ):
        _delete_cloud_password(previous_account, previous_cloud)
    reload_configuration()
    return configuration_summary()


def remove_account_from_this_pc() -> dict[str, Any]:
    """Forget the cloud login while preserving the paired AC configuration."""

    previous_account = MSMART_ACCOUNT
    previous_cloud = MIDEA_ACCOUNT_CLOUD
    _delete_cloud_password(previous_account, previous_cloud)

    # Device details and verified LAN credentials belong to the paired AC, not
    # to the cloud login. Keeping them lets locally authenticated units remain
    # controllable after cloud sign-out. A cloud-only unit must sign in again.
    settings = {"MSMART_ACCOUNT": ""}
    ENV_FILE.touch(exist_ok=True)
    for name, value in settings.items():
        set_key(ENV_FILE, name, value, quote_mode="always")
    _remove_plaintext_password()
    reload_configuration()
    return configuration_summary()


class _RawCloudCommand:
    """Adapt an msmart command frame to midea-beautiful's cloud wrapper."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def finalize(self) -> bytes:
        return self._data


@dataclass(frozen=True)
class ACState:
    """Thread-safe, GUI-friendly copy of the device state."""

    ip: str
    device_name: str
    model_number: str | None
    power: bool
    target_temperature: float
    indoor_temperature: float | None
    mode: str
    fan_speed: str
    minimum_temperature: float
    maximum_temperature: float
    supported_modes: frozenset[str]
    supported_fan_speeds: frozenset[str]
    transport: str
    outdoor_temperature: float | None
    error_code: int
    vertical_swing: bool
    horizontal_swing: bool
    eco: bool
    turbo: bool
    frost_protect: bool
    display_on: bool
    sleep: bool
    comfort: bool
    purifier: bool
    dryer: bool
    filter_alert: bool | None
    real_time_power: float | None
    current_energy: float | None
    total_energy: float | None
    supported_features: frozenset[str]


class ACController:
    """All communication with msmart-ng lives in this async controller."""

    MODES = {
        "Cool": AirConditioner.OperationalMode.COOL,
        "Heat": AirConditioner.OperationalMode.HEAT,
        "Fan Only": AirConditioner.OperationalMode.FAN_ONLY,
        "Dry": AirConditioner.OperationalMode.DRY,
    }
    FAN_SPEEDS = {
        "Auto": AirConditioner.FanSpeed.AUTO,
        "Low": AirConditioner.FanSpeed.LOW,
        "Medium": AirConditioner.FanSpeed.MEDIUM,
        "High": AirConditioner.FanSpeed.HIGH,
    }
    CLOUD_MODES = {"Cool": 2, "Heat": 4, "Fan Only": 5, "Dry": 3}
    CLOUD_FAN_SPEEDS = {"Auto": 102, "Low": 40, "Medium": 60, "High": 80}
    FEATURE_LABELS = {
        "vertical_swing": "Vertical Swing",
        "horizontal_swing": "Horizontal Swing",
        "eco": "Eco",
        "turbo": "Turbo",
        "frost_protect": "8°C Heat",
        "display_on": "Display Light",
        "sleep": "Sleep",
        "comfort": "Comfort",
        "purifier": "Purifier",
        "dryer": "Dryer",
    }

    def __init__(self) -> None:
        self.device: AirConditioner | None = None
        self.cloud: Any | None = None
        self.cloud_device: Any | None = None
        self._device_name = "Air Conditioner"
        self._model_number: str | None = None
        self._filter_alert: bool | None = None
        self._real_time_power: float | None = None
        self._current_energy: float | None = None
        self._total_energy: float | None = None
        self._last_energy_refresh = 0.0
        self._operation_lock: asyncio.Lock | None = None

    def _lock(self) -> asyncio.Lock:
        # Constructing the lock here binds its first use to the worker loop.
        if self._operation_lock is None:
            self._operation_lock = asyncio.Lock()
        return self._operation_lock

    @staticmethod
    def _validate_configuration() -> None:
        if bool(MSMART_ACCOUNT) != bool(MSMART_PASSWORD):
            raise ValueError(
                "Set both MSMART_ACCOUNT and MSMART_PASSWORD, or leave both empty."
            )
        if bool(DEVICE_TOKEN) != bool(DEVICE_KEY):
            raise ValueError(
                "Set both MIDEA_DEVICE_TOKEN and MIDEA_DEVICE_KEY, or leave both empty."
            )
        if DEVICE_ID:
            try:
                int(DEVICE_ID)
            except ValueError as exc:
                raise ValueError("MIDEA_DEVICE_ID must contain digits only.") from exc
        if MSMART_REGION.upper() not in {"DE", "US", "KR"}:
            raise ValueError("MSMART_REGION must be DE, US, or KR.")
        if MIDEA_ACCOUNT_CLOUD not in SUPPORTED_CLOUDS:
            choices = ", ".join(SUPPORTED_CLOUDS)
            raise ValueError(f"MIDEA_ACCOUNT_CLOUD must be one of: {choices}.")

    async def connect(self) -> ACState:
        """Find, authenticate, query capabilities, and refresh the AC."""

        async with self._lock():
            self._validate_configuration()
            self.device = None
            self.cloud = None
            self.cloud_device = None

            manual_auth = bool(DEVICE_TOKEN and DEVICE_KEY)

            # NetHome's token endpoint returned no per-device credentials for
            # this account. With an explicitly selected NetHome account and no
            # saved LAN pair, go straight to its working transparent-send API.
            if (
                not manual_auth
                and MIDEA_ACCOUNT_CLOUD == "NetHome Plus"
                and MSMART_ACCOUNT
                and MSMART_PASSWORD
            ):
                return await asyncio.to_thread(
                    self._connect_cloud_sync,
                    ConnectionError("No saved LAN token/key"),
                )

            # If every local credential is known, discovery is unnecessary.
            if DEVICE_IP and DEVICE_ID and manual_auth:
                device = AirConditioner(
                    ip=DEVICE_IP,
                    port=DEVICE_PORT,
                    device_id=int(DEVICE_ID),
                )
                await device.authenticate(DEVICE_TOKEN, DEVICE_KEY)
            else:
                discovery_options: dict[str, Any] = {
                    "timeout": DISCOVERY_TIMEOUT_SECONDS,
                    "region": MSMART_REGION.upper(),
                    # Token retrieval is handled below with midea-local's newer
                    # appliance-code request. Discovery itself needs no login.
                    "account": None,
                    "password": None,
                    # Select the desired unit before making any cloud connection.
                    "auto_connect": False,
                }

                if DEVICE_IP:
                    found = await Discover.discover_single(
                        DEVICE_IP, **discovery_options
                    )
                    devices = [found] if found is not None else []
                else:
                    devices = await Discover.discover(
                        target=DISCOVERY_TARGET, **discovery_options
                    )

                air_conditioners = [
                    item for item in devices if isinstance(item, AirConditioner)
                ]
                if DEVICE_ID:
                    requested_id = int(DEVICE_ID)
                    air_conditioners = [
                        item for item in air_conditioners if item.id == requested_id
                    ]

                if not air_conditioners:
                    if (
                        MIDEA_ACCOUNT_CLOUD == "NetHome Plus"
                        and MSMART_ACCOUNT
                        and MSMART_PASSWORD
                    ):
                        return await asyncio.to_thread(
                            self._connect_cloud_sync,
                            ConnectionError("No AC found by local discovery"),
                        )
                    target = f" at {DEVICE_IP}" if DEVICE_IP else ""
                    raise ConnectionError(
                        "No supported Midea air conditioner was discovered"
                        f"{target}. Confirm that the PC and AC are on the same "
                        "non-guest Wi-Fi network and allow Python through Windows Firewall."
                    )

                device = air_conditioners[0]
                if manual_auth:
                    await device.authenticate(DEVICE_TOKEN, DEVICE_KEY)
                elif device.version == 3:
                    # The current cloud request includes both the UDP ID and
                    # appliance code. Each returned pair is verified locally;
                    # only the working one is saved for future cloud-free use.
                    try:
                        await self._authenticate_v3_and_save(device)
                    except Exception as local_error:
                        if (
                            MIDEA_ACCOUNT_CLOUD == "NetHome Plus"
                            and MSMART_ACCOUNT
                            and MSMART_PASSWORD
                        ):
                            return await asyncio.to_thread(
                                self._connect_cloud_sync, local_error
                            )
                        raise
                else:
                    # A V2 unit needs no token/key and refreshes entirely locally.
                    connected = await Discover.connect(device)
                    if not connected:
                        raise ConnectionError(
                            "The AC was found but authentication or its first status "
                            "request failed. Add compatible Midea-app credentials "
                            "or a token/key."
                        )

            # Capabilities provide the unit's actual temperature limits and
            # supported modes. Some devices tolerate this query but return less
            # data, so refresh once more to obtain the authoritative live state.
            await device.get_capabilities()
            await device.refresh()
            self._ensure_online(device)
            self.device = device
            return self._snapshot(device)

    def _connect_cloud_sync(self, local_error: Exception) -> ACState:
        """Connect through NetHome's transparent-send API as a LAN fallback."""

        try:
            cloud = beautiful_connect_to_cloud(
                MSMART_ACCOUNT,
                MSMART_PASSWORD,
                appname="NetHome Plus",
            )
            appliances = [
                appliance
                for appliance in cloud.list_appliances()
                if str(appliance.get("type", "")).lower()
                in {"ac", "0xac", "172", "-84"}
            ]
            device_id = DEVICE_ID
            selected_appliance = next(
                (
                    appliance
                    for appliance in appliances
                    if str(appliance.get("id", "")) == device_id
                ),
                None,
            )
            if not device_id:
                if not appliances:
                    raise ConnectionError(
                        "No compatible air conditioner is linked to this "
                        "NetHome Plus account."
                    )
                if len(appliances) > 1:
                    raise ConnectionError(
                        "This NetHome Plus account has multiple air conditioners. "
                        "Open Settings and enter the Device ID to choose one."
                    )
                selected_appliance = appliances[0]
                device_id = str(selected_appliance["id"])
                save_user_configuration({"device_id": device_id})
            if selected_appliance:
                self._device_name = (
                    str(selected_appliance.get("name") or "").strip()
                    or "Air Conditioner"
                )
                self._model_number = (
                    str(selected_appliance.get("modelNumber") or "").strip()
                    or None
                )
            device = beautiful_appliance_state(
                address=DEVICE_IP or None,
                appliance_id=device_id,
                appliance_type="0xac",
                cloud=cloud,
                use_cloud=True,
                cloud_timeout=10,
            )
        except Exception as cloud_error:
            raise ConnectionError(
                f"Local authentication failed ({local_error}); NetHome cloud "
                f"control also failed ({cloud_error})."
            ) from cloud_error
        self.cloud = cloud
        self.cloud_device = device
        if self._device_name == "Air Conditioner":
            self._device_name = str(getattr(device, "name", "") or "").strip() or self._device_name
        self._refresh_cloud_telemetry_sync(force=True)
        return self._cloud_snapshot()

    async def _authenticate_v3_and_save(self, device: AirConditioner) -> None:
        """Retrieve candidate V3 credentials, verify locally, and persist."""

        preset = get_preset_account_cloud()
        cloud_attempts: list[tuple[str, str, str]] = []
        if MSMART_ACCOUNT and MSMART_PASSWORD:
            cloud_attempts.append(
                (MIDEA_ACCOUNT_CLOUD, MSMART_ACCOUNT, MSMART_PASSWORD)
            )
        cloud_attempts.append(
            (get_default_cloud(), preset["username"], preset["password"])
        )

        candidates: list[dict[str, str]] = []
        cloud_errors: list[str] = []
        async with aiohttp.ClientSession() as session:
            # A known default key is harmless to try and is verified locally.
            default_cloud = get_midea_cloud(
                cloud_name=get_default_cloud(),
                session=session,
                account=preset["username"],
                password=preset["password"],
            )
            candidates.extend((await default_cloud.get_default_keys()).values())

            for cloud_name, account, password in cloud_attempts:
                cloud = get_midea_cloud(
                    cloud_name=cloud_name,
                    session=session,
                    account=account,
                    password=password,
                )
                try:
                    if not await cloud.login():
                        cloud_errors.append(f"{cloud_name} login failed")
                        continue
                    cloud_candidates = await cloud.get_cloud_keys(device.id)
                    if not cloud_candidates:
                        cloud_errors.append(
                            f"{cloud_name} returned no credentials for device {device.id}"
                        )
                    candidates.extend(cloud_candidates.values())
                except Exception as exc:
                    cloud_errors.append(f"{cloud_name}: {exc}")

        if not candidates:
            detail = "; ".join(cloud_errors)
            raise ConnectionError(
                "Midea did not return a V3 token/key for this appliance code. "
                + detail
            )

        last_error: Exception | None = None
        for candidate in candidates:
            token = candidate.get("token")
            key = candidate.get("key")
            if not token or not key:
                continue
            try:
                await device.authenticate(token, key)
                await device.refresh()
                if device.online:
                    self._save_local_credentials(device, token, key)
                    return
            except Exception as exc:  # try the alternative UDP-ID byte order
                last_error = exc

        details = []
        if last_error:
            details.append(str(last_error))
        details.extend(cloud_errors)
        detail = f" ({'; '.join(details)})" if details else ""
        raise ConnectionError(
            "Midea returned token/key candidates, but the AC rejected them" + detail
        )

    @staticmethod
    def _save_local_credentials(
        device: AirConditioner, token: str, key: str
    ) -> None:
        """Save verified local credentials; never save helper-cloud login data."""

        values = {
            "MIDEA_DEVICE_IP": device.ip,
            "MIDEA_DEVICE_PORT": str(device.port),
            "MIDEA_DEVICE_ID": str(device.id),
            "MIDEA_DEVICE_TOKEN": token,
            "MIDEA_DEVICE_KEY": key,
        }
        for name, value in values.items():
            set_key(ENV_FILE, name, value, quote_mode="always")
        reload_configuration()

    async def refresh(self) -> ACState:
        """Read current state without blocking Tkinter."""

        async with self._lock():
            if self.cloud_device is not None:
                return await asyncio.to_thread(self._cloud_refresh_sync)
            device = self._require_device()
            await device.refresh()
            self._ensure_online(device)
            return self._snapshot(device)

    async def apply(self, **changes: Any) -> ACState:
        """Apply one or more settings and read back the resulting state."""

        async with self._lock():
            if self.cloud_device is not None:
                return await asyncio.to_thread(self._cloud_apply_sync, changes)
            device = self._require_device()

            if "power" in changes:
                device.power_state = bool(changes["power"])
            if "temperature" in changes:
                requested = float(int(float(changes["temperature"]) + 0.5))
                requested = max(
                    device.min_target_temperature,
                    min(device.max_target_temperature, requested),
                )
                device.target_temperature = requested
            if "mode" in changes:
                # This board reports a Dry-only automatic fan code (101).  If
                # that value is copied into the next full control packet, the
                # AC ignores attempts to leave Dry mode.  Restore the normal
                # Auto code when the caller did not also choose a fan speed.
                if (
                    device.operational_mode == AirConditioner.OperationalMode.DRY
                    and changes["mode"] != "Dry"
                    and "fan_speed" not in changes
                ):
                    device.fan_speed = AirConditioner.FanSpeed.AUTO
                device.operational_mode = self.MODES[changes["mode"]]
            if "fan_speed" in changes:
                device.fan_speed = self.FAN_SPEEDS[changes["fan_speed"]]
            if "eco" in changes:
                device.eco = bool(changes["eco"])
            if "turbo" in changes:
                device.turbo = bool(changes["turbo"])
            if "frost_protect" in changes:
                device.freeze_protection = bool(changes["frost_protect"])
            if "sleep" in changes:
                device.sleep = bool(changes["sleep"])
            if "purifier" in changes:
                device.purifier = bool(changes["purifier"])
            if "vertical_swing" in changes or "horizontal_swing" in changes:
                vertical = device.swing_mode in {
                    AirConditioner.SwingMode.VERTICAL,
                    AirConditioner.SwingMode.BOTH,
                }
                horizontal = device.swing_mode in {
                    AirConditioner.SwingMode.HORIZONTAL,
                    AirConditioner.SwingMode.BOTH,
                }
                vertical = bool(changes.get("vertical_swing", vertical))
                horizontal = bool(changes.get("horizontal_swing", horizontal))
                device.swing_mode = (
                    AirConditioner.SwingMode.BOTH
                    if vertical and horizontal
                    else AirConditioner.SwingMode.VERTICAL
                    if vertical
                    else AirConditioner.SwingMode.HORIZONTAL
                    if horizontal
                    else AirConditioner.SwingMode.OFF
                )
            if (
                "display_on" in changes
                and bool(changes["display_on"]) != bool(device.display_on)
            ):
                await device.toggle_display()

            await device.apply()
            # Read back instead of assuming the AC accepted the requested state.
            await device.refresh()
            self._ensure_online(device)
            return self._snapshot(device)

    def _cloud_refresh_sync(self) -> ACState:
        if self.cloud_device is None or self.cloud is None:
            raise ConnectionError("NetHome cloud control is not connected.")
        self.cloud_device.refresh(self.cloud)
        self._refresh_cloud_telemetry_sync()
        return self._cloud_snapshot()

    def _cloud_apply_sync(self, changes: dict[str, Any]) -> ACState:
        if self.cloud_device is None or self.cloud is None:
            raise ConnectionError("NetHome cloud control is not connected.")
        values: dict[str, Any] = {"cloud": self.cloud}
        if "power" in changes:
            values["running"] = bool(changes["power"])
        if "temperature" in changes:
            requested = float(int(float(changes["temperature"]) + 0.5))
            values["target_temperature"] = max(
                16.0, min(31.0, requested)
            )
        if "mode" in changes:
            requested_mode = self.CLOUD_MODES[changes["mode"]]
            values["mode"] = requested_mode
            # Some Midea boards report fan code 101 while in Dry mode.
            # midea-beautiful builds a full state packet, so carrying 101 into
            # another mode makes this firmware reject/ignore the transition.
            if (
                int(self.cloud_device.state.mode) == self.CLOUD_MODES["Dry"]
                and requested_mode != self.CLOUD_MODES["Dry"]
                and "fan_speed" not in changes
            ):
                values["fan_speed"] = self.CLOUD_FAN_SPEEDS["Auto"]
        if "fan_speed" in changes:
            values["fan_speed"] = self.CLOUD_FAN_SPEEDS[changes["fan_speed"]]
        cloud_fields = {
            "vertical_swing": "vertical_swing",
            "horizontal_swing": "horizontal_swing",
            "eco": "eco_mode",
            "turbo": "turbo",
            "frost_protect": "frost_protect",
            "display_on": "show_screen",
            "sleep": "comfort_sleep",
            "comfort": "comfort_mode",
            "purifier": "purifier",
            "dryer": "dryer",
        }
        for change_name, cloud_name in cloud_fields.items():
            if change_name in changes:
                values[cloud_name] = bool(changes[change_name])
        self.cloud_device.set_state(**values)
        # AirConditionerAppliance.set_state() calls apply(), and this appliance
        # type already performs its own status refresh inside apply().  A
        # second refresh here added another full cloud round trip after the AC
        # had accepted the command.  Energy telemetry can wait for the normal
        # background refresh cycle.
        return self._cloud_snapshot()

    def _cloud_query_sync(self, command: Any, response_type: type) -> Any:
        if self.cloud_device is None or self.cloud is None:
            raise ConnectionError("NetHome cloud control is not connected.")
        packet = self.cloud_device._lan_packet(
            _RawCloudCommand(command.tobytes()), local_packet=False
        )
        replies = self.cloud.appliance_transparent_send(
            self.cloud_device.appliance_id, packet
        )
        if not replies:
            raise ConnectionError("The AC returned no telemetry response.")
        reply = replies[-1]
        if len(reply) < 14 or reply[0] != 0xAA or reply[2] != 0xAC:
            raise ConnectionError("The AC returned an invalid telemetry frame.")
        # Some Midea boards use a nonstandard inner CRC. The outer cloud frame
        # has already been authenticated; decode the payload without rejecting
        # this known firmware variant.
        return response_type(memoryview(reply)[10:-2])

    def _refresh_cloud_telemetry_sync(self, *, force: bool = False) -> None:
        if self.cloud_device is None:
            return

        latest = getattr(self.cloud_device.state, "latest_data", b"")
        if isinstance(latest, (bytes, bytearray)) and len(latest) > 16:
            try:
                basic = StateResponse(memoryview(latest)[:-2])
                self._filter_alert = basic.filter_alert
            except Exception:
                pass

        now = time.monotonic()
        if not force and now - self._last_energy_refresh < ENERGY_REFRESH_SECONDS:
            return
        capabilities = getattr(self.cloud_device.state, "capabilities", {})
        if not capabilities.get("electricity"):
            return
        try:
            energy = self._cloud_query_sync(GetGroupDataCommand(4), Group4Response)
        except Exception:
            return
        self._last_energy_refresh = now
        self._real_time_power = energy.real_time_power
        self._current_energy = energy.current_energy
        self._total_energy = energy.total_energy

    def _require_device(self) -> AirConditioner:
        if self.device is None:
            raise ConnectionError("No air conditioner is connected.")
        return self.device

    @staticmethod
    def _ensure_online(device: AirConditioner) -> None:
        if not device.online:
            raise ConnectionError(f"The air conditioner at {device.ip} did not respond.")
        if not device.supported:
            raise ConnectionError(
                "The discovered device responded, but msmart-ng marked it unsupported."
            )

    @staticmethod
    def _enum_name(value: Any) -> str:
        return getattr(value, "name", str(value))

    def _snapshot(self, device: AirConditioner) -> ACState:
        target = device.target_temperature
        if target is None:
            target = 24.0

        supported_features: set[str] = set()
        supported_swings = set(device.supported_swing_modes)
        if AirConditioner.SwingMode.VERTICAL in supported_swings or AirConditioner.SwingMode.BOTH in supported_swings:
            supported_features.add("vertical_swing")
        if AirConditioner.SwingMode.HORIZONTAL in supported_swings or AirConditioner.SwingMode.BOTH in supported_swings:
            supported_features.add("horizontal_swing")
        for feature, supported in {
            "eco": getattr(device, "supports_eco", False),
            "turbo": getattr(device, "supports_turbo", False),
            "frost_protect": getattr(device, "supports_freeze_protection", False),
            "display_on": getattr(device, "supports_display_control", False),
            "purifier": getattr(device, "supports_purifier", False),
        }.items():
            if supported:
                supported_features.add(feature)

        swing = device.swing_mode
        outdoor = getattr(device, "outdoor_temperature", None)
        total_energy = device.get_total_energy_usage()
        current_energy = device.get_current_energy_usage()
        real_time_power = device.get_real_time_power_usage()
        return ACState(
            ip=device.ip,
            device_name=str(device.name or "").strip() or "Air Conditioner",
            model_number=None,
            power=bool(device.power_state),
            target_temperature=float(target),
            indoor_temperature=(
                float(device.indoor_temperature)
                if device.indoor_temperature is not None
                else None
            ),
            mode=self._enum_name(device.operational_mode),
            fan_speed=self._enum_name(device.fan_speed),
            minimum_temperature=float(device.min_target_temperature),
            maximum_temperature=float(device.max_target_temperature),
            supported_modes=frozenset(
                self._enum_name(item) for item in device.supported_operation_modes
            ),
            supported_fan_speeds=frozenset(
                self._enum_name(item) for item in device.supported_fan_speeds
            ),
            transport="Local",
            outdoor_temperature=float(outdoor) if outdoor is not None else None,
            error_code=int(device.error_code or 0),
            vertical_swing=swing in {
                AirConditioner.SwingMode.VERTICAL,
                AirConditioner.SwingMode.BOTH,
            },
            horizontal_swing=swing in {
                AirConditioner.SwingMode.HORIZONTAL,
                AirConditioner.SwingMode.BOTH,
            },
            eco=bool(device.eco),
            turbo=bool(device.turbo),
            frost_protect=bool(device.freeze_protection),
            display_on=bool(device.display_on),
            sleep=bool(device.sleep),
            comfort=False,
            purifier=bool(device.purifier),
            dryer=False,
            filter_alert=device.filter_alert,
            real_time_power=real_time_power,
            current_energy=current_energy,
            total_energy=total_energy,
            supported_features=frozenset(supported_features),
        )

    def _cloud_snapshot(self) -> ACState:
        if self.cloud_device is None:
            raise ConnectionError("NetHome cloud control is not connected.")
        state = self.cloud_device.state
        mode_names = {2: "COOL", 3: "DRY", 4: "HEAT", 5: "FAN_ONLY"}
        fan_names = {40: "LOW", 60: "MEDIUM", 80: "HIGH", 102: "AUTO"}
        indoor = float(state.indoor_temperature)
        if indoor < -100 or indoor > 100:
            indoor = None
        outdoor = float(state.outdoor_temperature)
        if outdoor < -100 or outdoor > 100:
            outdoor = None
        capabilities = getattr(state, "capabilities", {})
        supported_features: set[str] = set()
        swing_capability = capabilities.get("fan_swing")
        if swing_capability in (0, 1):
            supported_features.add("vertical_swing")
        if swing_capability in (1, 3):
            supported_features.add("horizontal_swing")
        if capabilities.get("eco") in (1, 2):
            supported_features.add("eco")
        if capabilities.get("strong_fan"):
            supported_features.add("turbo")
        if capabilities.get("heat_8"):
            supported_features.add("frost_protect")
        # The status packet explicitly reports display state even though this
        # firmware omits the separate display capability record.
        supported_features.add("display_on")
        if capabilities.get("anion"):
            supported_features.add("purifier")
        return ACState(
            ip=DEVICE_IP or "NetHome Plus",
            device_name=self._device_name,
            model_number=self._model_number,
            power=bool(state.running),
            target_temperature=float(state.target_temperature or 24.0),
            indoor_temperature=indoor,
            mode=mode_names.get(int(state.mode), "AUTO"),
            fan_speed=fan_names.get(int(state.fan_speed), "AUTO"),
            minimum_temperature=16.0,
            maximum_temperature=31.0,
            supported_modes=frozenset(mode_names.values()),
            supported_fan_speeds=frozenset(fan_names.values()),
            transport="Cloud",
            outdoor_temperature=outdoor,
            error_code=int(state.error_code or 0),
            vertical_swing=bool(state.vertical_swing),
            horizontal_swing=bool(state.horizontal_swing),
            eco=bool(state.eco_mode),
            turbo=bool(state.turbo or state.turbo_fan),
            frost_protect=bool(state.frost_protect),
            display_on=bool(state.show_screen),
            sleep=bool(state.comfort_sleep),
            comfort=bool(state.comfort_mode),
            purifier=bool(state.purifier),
            dryer=bool(state.dryer),
            filter_alert=self._filter_alert,
            real_time_power=self._real_time_power,
            current_energy=self._current_energy,
            total_energy=self._total_energy,
            supported_features=frozenset(supported_features),
        )
