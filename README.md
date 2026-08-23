# AirCon Control

A Windows React/pywebview app for Midea-compatible air conditioners.
Communication is local after a V3 token/key has been obtained.
If NetHome Plus no longer provides that token/key, the app automatically falls
back to its transparent cloud-control endpoint for an AC paired in NetHome Plus.
Temperature steps and available controls are taken from the connected unit.

The interface follows a fixed, non-scrolling phone-style AirCon layout: a blue
control surface with mode shortcuts, a draggable whole-degree temperature arc,
and a prominent round power button. A real bottom sheet opens from the
**Controls** handle and holds fan speed plus one-tap vertical/horizontal swing,
Eco, Turbo, 8 °C frost protection, and indoor-unit display controls. Less common
features and live energy/system readings are tucked under **Show details and
more controls**. Unsupported controls are automatically dimmed. Energy data is
refreshed once per minute to avoid excessive cloud requests.

## Install and run (PowerShell)

Python 3.10 or newer and Node.js 20 or newer are required.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
npm --prefix .\react-webview-app install
npm --prefix .\react-webview-app run build
.\react-webview-app\run_react_app.bat
```

The gear button opens first-run connection settings. Both source and packaged
builds store private configuration in `%LOCALAPPDATA%\AirConControl\.env`, outside
the repository. Cloud passwords are protected by Windows Credential Manager;
local tokens and keys remain in the private LocalAppData file. Secrets are never
returned to the React interface or included in a release package.

## Build a Windows release

Install the pinned build tools once, then run the release script:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements-build.txt
.\build_release.ps1
```

The script builds React, generates the Windows icon, creates a versioned
PyInstaller one-folder application, and packages it as
`release\AirConControl-Windows-x64-1.0.0.zip`. Distribute that ZIP as a unit; it
does not contain `.env` or credentials. Building on 64-bit Windows produces a
64-bit Windows release.

The generated community build is not code-signed, so Windows SmartScreen may
show an Unknown publisher warning. A public release should be Authenticode-
signed with the distributor's certificate.

If PowerShell blocks virtual-environment activation, activation is optional:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm --prefix .\react-webview-app install
npm --prefix .\react-webview-app run build
.\react-webview-app\run_react_app.bat
```

## Configuration and authentication

First try the app unchanged. It broadcasts on the LAN and `msmart-ng` can use
its cloud authentication flow for many V3 units. The PC and AC must be on the
same subnet; guest Wi-Fi/client isolation must be disabled.

Settings are loaded from `%LOCALAPPDATA%\AirConControl\.env` and may also be
supplied as environment variables. `.env.example` documents the available keys:

- `MSMART_ACCOUNT`: login name for the mobile app selected by
  `MIDEA_ACCOUNT_CLOUD`. Enter the password in the gear menu; it is saved in
  Windows Credential Manager. Existing `.env` passwords are migrated and removed.
- `MSMART_REGION`: `DE` for Europe, or `US`/`KR` as appropriate.
- `MIDEA_ACCOUNT_CLOUD`: `NetHome Plus` by default. Select `SmartHome` when
  the AC has been paired to an account created in the NetHome Plus app.
- `MIDEA_DEVICE_IP`: optional fixed AC address.
- `MIDEA_DEVICE_ID`, `MIDEA_DEVICE_TOKEN`, `MIDEA_DEVICE_KEY`: saved local V3
  credentials. The app fills these automatically only after verifying them
  against the physical AC. Supplying these plus the IP avoids cloud use entirely.
- `MIDEA_DISCOVERY_TARGET`: optional broadcast address. It defaults to the
  portable IPv4 broadcast `255.255.255.255`; a subnet-specific target can help
  when a VPN captures discovery traffic.
- `AIRCON_WEATHER_LOCATION_ENABLED`: remembers whether location-based weather
  is enabled. After the first successful permission grant, the app stores only
  three-decimal approximate coordinates in LocalAppData and reuses them on
  later launches. Disable or refresh the saved location from the gear menu.

Keep `.env` and its local token/key private. Use **Sign out of cloud account**
in the gear menu to delete the Windows credential while preserving device
details and any verified local token/key. Cloud-only units disconnect until you
sign in again. You may
need to allow Python through Windows Defender Firewall the first time discovery
broadcasts are sent.

## License

AirCon Control is available under the [MIT License](LICENSE).
