# React + pywebview AirCon Control

This is the project's desktop interface. It imports the shared `ACController`
from the parent project. Private settings live outside the repository in
`%LOCALAPPDATA%\AirConControl\.env`; the cloud password is protected separately
by Windows Credential Manager.

The gear button provides first-run account/device setup. Source and frozen
Windows builds use the same private LocalAppData settings location.

## Run

Double-click `run_react_app.bat`, or run:

```powershell
npm --prefix .\react-webview-app run build
.\.venv\Scripts\python.exe .\react-webview-app\backend.py
```

## Reinstall

```powershell
npm install
..\.venv\Scripts\python.exe -m pip install -r ..\requirements.txt
npm run build
```

The UI is a fixed non-scrolling window. Drag the white handle on the
temperature arc and release it to send a whole-degree setpoint. The white
bottom sheet opens and closes without moving or scrolling the main screen.
Interface symbols use `lucide-react` components with short text labels retained
where an icon alone would be ambiguous.

On first launch, Windows may ask for location permission. If granted, the app
stores only three-decimal approximate coordinates in LocalAppData and reuses
them on later launches, so it does not request location again each time. The
preference can be disabled or the saved location refreshed from the gear menu.
Open-Meteo is refreshed every 30 minutes and drives the outdoor weather icon.
