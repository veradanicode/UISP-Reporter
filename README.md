# UISP Report Generator — Source-of-Truth Edition

This build follows one rule: **UISP is the source of truth.** The application does not assume a device is a switch, AP, GPON, router, AirMAX, or any other type before reading what UISP actually returns.

## Device selection — no device ID in `.env`

The user does **not** enter a device UUID in configuration.

The workflow is:

1. Backend connects to UISP using `UISP_URL` + `UISP_API_TOKEN`.
2. `GET /nms/api/v2.1/devices` retrieves the live device inventory.
3. The React application displays that inventory.
4. The user selects one or more devices in the UI.
5. The selected IDs are sent in the report request.
6. The backend retrieves data for those selected devices only.


## What the collector retrieves

For each selected device it collects the actual UISP responses from:

- `/nms/api/v2.1/devices/{id}`
- `/nms/api/v2.1/devices/{id}/detail?withStations=true`
- `/nms/api/v2.1/devices/{id}/statistics`
- `/nms/api/v2.1/devices/{id}/interfaces`
- `/nms/api/v2.1/outages?deviceId={id}`
- additional endpoints are probed safely; only successful responses are included
- wireless/AirMAX resources are probed when the device's returned identity indicates they are relevant

The raw successful payloads are preserved in the PDF appendix so information is not silently discarded just because the renderer does not yet have a dedicated pretty table for that field.

## Windows setup

### First installation

Open PowerShell/cmd in `backend` and run:

```bat
setup_windows.bat
```

Then edit `backend/.env`:

```env
UISP_URL=https://vdtaccess.uisp.com
UISP_API_TOKEN=YOUR_NEW_API_TOKEN
UISP_VERIFY_SSL=false
PORT=5000
```

There is intentionally **no device ID variable**.

Start the backend:

```bat
start_windows.bat
```

Or manually:

```powershell
.venv\Scripts\activate
python app.py
```

## Fixing `SyntaxError: source code string cannot contain null bytes`

If you see an error like:

```text
File "...\\site-packages\\requests\\__init__.py"
import urllib3
SyntaxError: source code string cannot contain null bytes
```

that error occurs while Python is importing the installed `requests`/`urllib3` package, before the UISP application code runs. It indicates a damaged/corrupted package file in the virtual environment rather than a UISP device-ID problem.

Run:

```bat
repair_windows.bat
```

The repair script removes only this project's `.venv`, recreates it, and reinstalls the pinned dependencies. Python's Windows documentation also recommends using the environment's Python/pip explicitly when working with virtual environments. 

## Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open the Vite URL, normally `http://localhost:5173`.

## API

- `GET /api/health`
- `GET /api/devices`
- `GET /api/devices/{id}/inspect?period=24h`
- `POST /api/reports/generate`
- `GET /api/reports/{report_id}/preview`
- `GET /api/reports/{report_id}/download`

## Security

Do not commit the real UISP API token. If an old token was previously exposed in source code, rotate/revoke it and use the new token only in `backend/.env`.
