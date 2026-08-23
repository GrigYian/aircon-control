"""Network-free smoke tests for the controller's state/command mapping."""

import unittest
from unittest.mock import patch

from msmart.device import AirConditioner

from ac_controller import ACController, configuration_summary


class FakeAirConditioner:
    ip = "192.0.2.10"
    name = "Bedroom AC"
    online = True
    supported = True
    power_state = False
    target_temperature = 24.0
    indoor_temperature = 25.5
    operational_mode = AirConditioner.OperationalMode.COOL
    fan_speed = AirConditioner.FanSpeed.AUTO
    min_target_temperature = 16.0
    max_target_temperature = 30.0
    supported_operation_modes = list(AirConditioner.OperationalMode)
    supported_fan_speeds = list(AirConditioner.FanSpeed)
    supported_swing_modes = list(AirConditioner.SwingMode)
    swing_mode = AirConditioner.SwingMode.OFF
    supports_eco = True
    supports_turbo = True
    supports_freeze_protection = True
    supports_display_control = True
    supports_purifier = False
    outdoor_temperature = 20.0
    error_code = 0
    eco = False
    turbo = False
    freeze_protection = False
    display_on = True
    sleep = False
    purifier = False
    filter_alert = False

    async def apply(self) -> None:
        pass

    async def refresh(self) -> None:
        pass

    async def toggle_display(self) -> None:
        self.display_on = not self.display_on

    def get_total_energy_usage(self) -> float:
        return 123.4

    def get_current_energy_usage(self) -> float:
        return 0.5

    def get_real_time_power_usage(self) -> float:
        return 450.0


class FakeCloudState:
    running = True
    target_temperature = 26.0
    indoor_temperature = 28.0
    mode = 2
    fan_speed = 60
    outdoor_temperature = 20.5
    error_code = 0
    vertical_swing = False
    horizontal_swing = False
    eco_mode = False
    turbo = False
    turbo_fan = False
    frost_protect = False
    show_screen = True
    comfort_sleep = False
    comfort_mode = False
    purifier = False
    dryer = False
    capabilities = {
        "eco": 1,
        "fan_swing": 1,
        "heat_8": 1,
        "strong_fan": 1,
    }
    latest_data = b""


class FakeCloudDevice:
    def __init__(self) -> None:
        self.state = FakeCloudState()
        self.refresh_calls = 0

    def refresh(self, _cloud: object) -> None:
        self.refresh_calls += 1

    def set_state(self, **changes: object) -> None:
        for name, value in changes.items():
            if name != "cloud":
                setattr(self.state, name, value)


class ControllerTests(unittest.IsolatedAsyncioTestCase):
    def test_configuration_summary_never_exposes_secret_values(self) -> None:
        summary = configuration_summary()

        self.assertNotIn("password", summary)
        self.assertNotIn("device_token", summary)
        self.assertNotIn("device_key", summary)
        self.assertIn("has_password", summary)
        self.assertIn("has_local_credentials", summary)

    async def test_apply_maps_all_requested_controls(self) -> None:
        controller = ACController()
        controller.device = FakeAirConditioner()  # type: ignore[assignment]

        state = await controller.apply(
            power=True,
            temperature=25.0,
            mode="Heat",
            fan_speed="High",
        )

        self.assertTrue(state.power)
        self.assertEqual(state.target_temperature, 25.0)
        self.assertEqual(state.mode, "HEAT")
        self.assertEqual(state.fan_speed, "HIGH")
        self.assertEqual(state.device_name, "Bedroom AC")

    async def test_temperature_is_clamped_to_device_limits(self) -> None:
        controller = ACController()
        controller.device = FakeAirConditioner()  # type: ignore[assignment]

        state = await controller.apply(temperature=99)

        self.assertEqual(state.target_temperature, 30.0)

    async def test_temperature_is_snapped_to_whole_degree(self) -> None:
        controller = ACController()
        controller.device = FakeAirConditioner()  # type: ignore[assignment]

        state = await controller.apply(temperature=24.26)

        self.assertEqual(state.target_temperature, 24.0)

    async def test_cloud_fallback_maps_and_applies_controls(self) -> None:
        controller = ACController()
        controller.cloud = object()
        controller.cloud_device = FakeCloudDevice()

        state = await controller.apply(
            power=False,
            temperature=26.0,
            mode="Heat",
            fan_speed="High",
        )

        self.assertEqual(state.transport, "Cloud")
        self.assertFalse(state.power)
        self.assertEqual(state.target_temperature, 26.0)
        self.assertEqual(state.mode, "HEAT")
        self.assertEqual(state.fan_speed, "HIGH")
        self.assertEqual(controller.cloud_device.refresh_calls, 0)

    async def test_cloud_fallback_maps_extra_features(self) -> None:
        controller = ACController()
        controller.cloud = object()
        controller.cloud_device = FakeCloudDevice()

        state = await controller.apply(
            vertical_swing=True,
            eco=True,
            turbo=True,
            frost_protect=True,
            display_on=False,
        )

        self.assertTrue(state.vertical_swing)
        self.assertTrue(state.eco)
        self.assertTrue(state.turbo)
        self.assertTrue(state.frost_protect)
        self.assertFalse(state.display_on)
        self.assertIn("vertical_swing", state.supported_features)

    async def test_leaving_cloud_dry_mode_normalizes_dry_only_fan_code(self) -> None:
        controller = ACController()
        controller.cloud = object()
        controller.cloud_device = FakeCloudDevice()
        controller.cloud_device.state.mode = 3
        controller.cloud_device.state.fan_speed = 101

        state = await controller.apply(mode="Cool")

        self.assertEqual(state.mode, "COOL")
        self.assertEqual(controller.cloud_device.state.fan_speed, 102)
        self.assertEqual(state.fan_speed, "AUTO")

    async def test_explicit_fan_speed_wins_when_leaving_cloud_dry_mode(self) -> None:
        controller = ACController()
        controller.cloud = object()
        controller.cloud_device = FakeCloudDevice()
        controller.cloud_device.state.mode = 3
        controller.cloud_device.state.fan_speed = 101

        state = await controller.apply(mode="Cool", fan_speed="Low")

        self.assertEqual(state.mode, "COOL")
        self.assertEqual(controller.cloud_device.state.fan_speed, 40)
        self.assertEqual(state.fan_speed, "LOW")

    @patch("ac_controller.save_user_configuration")
    @patch("ac_controller.beautiful_appliance_state")
    @patch("ac_controller.beautiful_connect_to_cloud")
    async def test_nethome_auto_selects_a_single_linked_ac(
        self,
        connect_cloud,
        appliance_state,
        save_configuration,
    ) -> None:
        class FakeCloud:
            @staticmethod
            def list_appliances() -> list[dict[str, str]]:
                return [{
                    "id": "123456789",
                    "name": "Living room",
                    "type": "0xac",
                    "modelNumber": "Example AC 12K",
                }]

        connect_cloud.return_value = FakeCloud()
        appliance_state.return_value = FakeCloudDevice()
        controller = ACController()

        with patch("ac_controller.DEVICE_ID", ""):
            state = controller._connect_cloud_sync(ConnectionError("local unavailable"))

        self.assertEqual(state.transport, "Cloud")
        self.assertEqual(state.device_name, "Living room")
        self.assertEqual(state.model_number, "Example AC 12K")
        save_configuration.assert_called_once_with({"device_id": "123456789"})
        self.assertEqual(appliance_state.call_args.kwargs["appliance_id"], "123456789")


if __name__ == "__main__":
    unittest.main()
