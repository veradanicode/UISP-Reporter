# UISP Reporter

> **Source-of-truth network reporting for UISP-managed infrastructure.**

UISP Reporter is a full-stack network reporting application that connects directly to a **Ubiquiti UISP / Network Management System (NMS)** instance, retrieves live device telemetry, allows operators to select one or multiple devices, configures the information to include, and generates a structured **PDF network report** that can be previewed and downloaded directly from the application.

The core design principle is simple:

> **UISP is the source of truth.**

The application does not assume that every device is a switch, access point, router, GPON device, or wireless station. Instead, it inspects the data returned by UISP and renders reports based on the actual device information available.

---

## ✨ Features

### 📡 Live UISP Device Discovery

Devices are discovered dynamically from the configured UISP instance.

- No device UUID is required in `.env`
- Retrieves the current UISP device inventory
- Displays device name, model, type, role, IP address, MAC address, and status
- Search devices by:
  - Name
  - Model
  - Type
  - Role
  - IP address

### 📊 Device-Aware Reporting

The reporting engine works with the data actually returned by UISP rather than relying on a fixed device template.

Depending on the device and available UISP endpoints, reports can include:

- Device information
- Device details
- Performance statistics
- Interface information
- Wireless stations/subscribers
- Outage history
- Data-link relationships
- Device status
- Device configuration
- Device health
- MAC tables
- Wireless configuration
- Site survey information
- Frequency-band information

Unsupported or unavailable endpoint data is handled gracefully instead of being fabricated.

---

### 📈 Telemetry & Performance Charts

Reports can include charts generated from UISP time-series data.

Supported reporting windows include:

| Period | Duration |
| ------ | -------: |
| `1h`   |   1 hour |
| `6h`   |  6 hours |
| `24h`  | 24 hours |
| `7d`   |   7 days |

Charts may include metrics such as:

- CPU utilization
- RAM
- Ping/latency
- Interface RX/TX traffic
- Temperature
- Voltage
- Wireless/interface statistics
- Other telemetry returned by UISP

The reporting engine only visualizes telemetry that is actually available in the UISP response.

---

### 🧩 Configurable Report Sections

Operators can control which major sections appear in the generated report.

Available sections include:

- Device Information
- Performance / Statistics
- Interfaces / Ports
- Stations / Subscribers
- Outage History
- Telemetry Charts
- Complete UISP Appendix

The **Complete UISP Appendix** is designed to preserve successful UISP payloads that do not yet have a dedicated presentation component.

This helps prevent useful network information from being silently discarded.

---

### 🔎 UISP Inspector

The built-in inspector provides visibility into the collection process.

For a selected device, operators can see:

- UISP endpoints queried
- Successful requests
- Failed optional requests
- Endpoint errors
- Raw device response
- Raw device detail response

This is particularly useful for debugging differences between UISP device types and installations.

---

### 📄 PDF Preview & Download

After report generation, the application provides:

1. Report generation status
2. Number of successfully collected devices
3. Devices that failed collection
4. Embedded PDF preview
5. PDF download

Multiple devices can be included in a single report.

---

## 🏗️ Architecture

UISP Reporter follows a lightweight full-stack architecture:

```text
┌───────────────────────────────┐
│          React Frontend       │
│                               │
│  Dashboard                    │
│  Device Selection             │
│  Report Configuration         │
│  UISP Inspector               │
│  PDF Preview                  │
└───────────────┬───────────────┘
                │
                │ HTTP / JSON
                ▼
┌───────────────────────────────┐
│          Flask API            │
│                               │
│  /api/devices                 │
│  /api/devices/:id/inspect     │
│  /api/reports/generate        │
│  /api/reports/:id/preview     │
│  /api/reports/:id/download    │
└───────────────┬───────────────┘
                │
                │ HTTPS + x-auth-token
                ▼
┌───────────────────────────────┐
│          UISP / NMS           │
│                               │
│ Device Inventory              │
│ Device Details                │
│ Statistics                    │
│ Interfaces                    │
│ Outages                       │
│ Wireless Data                 │
│ Additional Telemetry          │
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────┐
│       Report Engine           │
│                               │
│ Data normalization             │
│ Metric formatting              │
│ Chart generation              │
│ PDF composition               │
└───────────────────────────────┘
```

---

## 🛠️ Tech Stack

### Frontend

| Technology       | Purpose                                 |
| ---------------- | --------------------------------------- |
| **React**        | UI architecture                         |
| **Vite**         | Frontend tooling and development server |
| **Lucide React** | Interface icons                         |
| **CSS**          | Custom responsive styling               |

### Backend

| Technology        | Purpose                    |
| ----------------- | -------------------------- |
| **Python**        | Backend/runtime            |
| **Flask**         | REST API                   |
| **Requests**      | UISP API communication     |
| **Flask-CORS**    | Cross-origin communication |
| **python-dotenv** | Environment configuration  |
| **ReportLab**     | PDF generation             |
| **Matplotlib**    | Telemetry chart generation |
| **pypdf**         | PDF processing             |
| **urllib3**       | HTTP/TLS support           |

---

## 📁 Project Structure

```text
UISP-Reporter/
│
├── backend/
│   ├── app.py
│   ├── uisp_client.py
│   ├── report_engine.py
│   ├── requirements.txt
│   ├── .env.example
│   │
│   ├── reports/
│   │   └── generated reports and charts
│   │
│   ├── setup_windows.bat
│   └── start_windows.bat
│
├── frontend/
│   ├── src/
│   │   ├── main.jsx
│   │   └── styles.css
│   │
│   ├── package.json
│   ├── package-lock.json
│   └── .env.example
│
├── .gitignore
└── README.md
```

---

# 🚀 Getting Started

## Prerequisites

Make sure the following are installed:

- **Python 3.10+**
- **Node.js 18+**
- **npm**
- Access to a UISP/NMS installation
- A valid UISP API token

You should also have network access from the backend machine to the configured UISP instance.

---

# ⚙️ Backend Setup

## 1. Navigate to the backend

```bash
cd backend
```

---

## 2. Create a Python virtual environment

### Windows

```powershell
python -m venv .venv
```

Activate it:

```powershell
.venv\Scripts\activate
```

---

## 3. Install dependencies

```powershell
pip install -r requirements.txt
```

The project pins its backend dependencies to known versions for reproducible local setup.

---

## 4. Configure environment variables

Create:

```text
backend/.env
```

using `.env.example` as a template.

```env
UISP_URL=https://your-uisp-instance.example.com
UISP_API_TOKEN=YOUR_API_TOKEN
UISP_VERIFY_SSL=false
PORT=5000
```

### Environment variables

| Variable          | Description                                 | Required |
| ----------------- | ------------------------------------------- | -------- |
| `UISP_URL`        | Base URL of the UISP/NMS instance           | Yes      |
| `UISP_API_TOKEN`  | UISP authentication token                   | Yes      |
| `UISP_VERIFY_SSL` | Enable/disable TLS certificate verification | No       |
| `PORT`            | Flask API port                              | No       |

> **Important:** A device ID is intentionally **not** stored in `.env`.

Devices are discovered dynamically from UISP.

---

## 5. Start the backend

You can use the included Windows startup script:

```bat
start_windows.bat
```

Or start Flask directly:

```powershell
python app.py
```

The backend will normally be available at:

```text
http://localhost:5000
```

---

# 🖥️ Frontend Setup

Open another terminal.

```bash
cd frontend
```

Install dependencies:

```bash
npm install
```

Start the Vite development server:

```bash
npm run dev
```

The frontend will normally be available at:

```text
http://localhost:5173
```

---

## Frontend Environment Configuration

The frontend uses:

```env
VITE_API_URL=http://localhost:5000
```

Create:

```text
frontend/.env
```

if you need to point the frontend to another backend.

Example:

```env
VITE_API_URL=http://localhost:5000
```

---

# 🔄 Application Workflow

The application follows a straightforward reporting pipeline:

```text
        ┌───────────────┐
        │ Open Dashboard│
        └───────┬───────┘
                │
                ▼
       ┌──────────────────┐
       │ Fetch UISP Device│
       │     Inventory    │
       └────────┬─────────┘
                │
                ▼
       ┌──────────────────┐
       │ Select Device(s) │
       └────────┬─────────┘
                │
                ▼
       ┌──────────────────┐
       │ Configure Report │
       │    Sections      │
       └────────┬─────────┘
                │
                ▼
       ┌──────────────────┐
       │ Choose Telemetry │
       │     Window       │
       └────────┬─────────┘
                │
                ▼
       ┌──────────────────┐
       │ Collect Live UISP│
       │       Data       │
       └────────┬─────────┘
                │
                ▼
       ┌──────────────────┐
       │ Normalize + Build│
       │      Report      │
       └────────┬─────────┘
                │
                ▼
       ┌──────────────────┐
       │ Generate PDF +   │
       │     Charts       │
       └────────┬─────────┘
                │
                ▼
       ┌──────────────────┐
       │ Preview / Download│
       └──────────────────┘
```

---

# 🔌 API Reference

The backend exposes the following REST endpoints.

## Health Check

### `GET /api/health`

Returns the backend configuration status.

Example response:

```json
{
  "ok": true,
  "configured": true,
  "uisp_url": "https://your-uisp-instance.example.com",
  "device_id_required_in_env": false
}
```

---

## List Devices

### `GET /api/devices`

Retrieves the device inventory from UISP.

Example response:

```json
[
  {
    "id": "device-id",
    "name": "Core Router",
    "model": "Device Model",
    "type": "Router",
    "role": "Gateway",
    "ip": "192.168.1.1",
    "mac": "00:00:00:00:00:00",
    "status": "Online"
  }
]
```

---

## Inspect Device

### `GET /api/devices/:id/inspect`

Retrieves detailed information about a specific device and exposes the endpoint collection results.

Optional query parameter:

```text
period=24h
```

Supported values:

```text
1h
6h
24h
7d
```

Example:

```text
GET /api/devices/device-id/inspect?period=24h
```

The response contains:

- Device data
- Device details
- Statistics
- Interfaces
- Outages
- Data links
- Optional endpoint results
- Endpoint success/failure information

---

# 📄 Generate Report

### `POST /api/reports/generate`

Generates a PDF report for one or more devices.

Example request:

```json
{
  "device_ids": ["device-id-1", "device-id-2"],
  "period": "24h",
  "sections": {
    "device_information": true,
    "performance": true,
    "interfaces": true,
    "subscribers": true,
    "outages": true,
    "charts": true,
    "additional": true
  }
}
```

Example response:

```json
{
  "report_id": "generated-report-id",
  "filename": "generated-report-id.pdf",
  "collected_devices": 2,
  "failed_devices": [],
  "preview_url": "/api/reports/generated-report-id/preview",
  "download_url": "/api/reports/generated-report-id/download"
}
```

If one selected device fails while others succeed, the successful devices can still be included and the failed device is reported separately.

---

# 👁️ Preview Report

### `GET /api/reports/:report_id/preview`

Streams the generated PDF for browser preview.

---

# ⬇️ Download Report

### `GET /api/reports/:report_id/download`

Downloads the generated PDF.

---

# 🔐 Security

UISP credentials are deliberately kept on the backend.

```text
Browser
   │
   │ device IDs + report configuration
   ▼
Flask Backend
   │
   │ UISP_URL + UISP_API_TOKEN
   ▼
UISP
```

The frontend does **not** receive the UISP API token.

### Credential storage

Keep secrets in:

```text
backend/.env
```

Never commit:

```text
backend/.env
```

The repository's `.gitignore` already excludes it.

### Token rotation

If an API token has previously been exposed through source code, logs, screenshots, commits, or other public locations:

1. Revoke/rotate the exposed token.
2. Generate a new token.
3. Store the new token in `backend/.env`.
4. Verify that the old token is no longer active.

---

# 🧠 Source-of-Truth Design

One of the key architectural decisions in UISP Reporter is avoiding assumptions about device capabilities.

Instead of doing this:

```python
if device_type == "switch":
    generate_switch_report()
```

the collector first retrieves the device and its available resources.

Required resources are collected directly:

```text
Device
Detail
Statistics
Interfaces
Outages
```

Additional resources are probed conditionally:

```text
Device Status
Device Config
Device Health
MAC Table
Wireless Stations
Wireless Config
Site Survey
Frequency Bands
Data Links
```

Successful responses are retained.

Failed optional requests are recorded rather than causing the entire report to fail.

This makes the reporting pipeline more tolerant of:

- Different device models
- Different UISP versions
- Different device capabilities
- Missing optional resources
- Wireless vs wired infrastructure
- Different telemetry structures

---

# 🧱 Backend Responsibilities

The backend is separated conceptually into two primary responsibilities.

### `uisp_client.py`

Responsible for communication with UISP.

Responsibilities include:

- Authentication
- HTTP requests
- Timeout handling
- JSON parsing
- Device discovery
- Device data collection
- Optional endpoint probing
- UISP-specific error handling

### `report_engine.py`

Responsible for transforming collected UISP data into human-readable reports.

Responsibilities include:

- Data normalization
- Value formatting
- Device-specific presentation
- Wireless/station diagnostics
- Telemetry extraction
- Chart generation
- PDF composition
- Additional/raw data preservation

### `app.py`

Acts as the API layer.

Responsibilities include:

- HTTP routing
- Request validation
- Calling the UISP client
- Calling the report engine
- Report file serving
- Error responses
- CORS configuration

---

# 🎨 Frontend Responsibilities

The React application provides the operator-facing workflow.

### Dashboard

Provides a high-level overview of:

- UISP device count
- Online device count
- Selected devices
- Reporting workflow status

### Devices

Provides:

- Device discovery
- Search
- Device selection
- Device status
- Device inspection

### Generate Report

Provides:

- Multi-device selection
- Report section configuration
- Telemetry period selection
- Report generation

### Inspector

Provides:

- Endpoint collection status
- UISP request diagnostics
- Raw response inspection

### Report Preview

Provides:

- Generated report information
- Failed-device information
- Embedded PDF preview
- Download action

---

# 🪟 Windows Development Helpers

The backend includes Windows helper scripts.

### Initial setup

```bat
setup_windows.bat
```

### Start application

```bat
start_windows.bat
```

These scripts are intended to simplify local development on Windows machines.

---

# 🛠️ Troubleshooting

## `UISP_API_TOKEN is not configured`

Check:

```text
backend/.env
```

and ensure:

```env
UISP_API_TOKEN=your-token
```

is present.

Restart the backend after changing environment variables.

---

## UISP connection failed

Verify:

- UISP URL
- Network connectivity
- Firewall rules
- API token
- UISP availability
- TLS configuration

If your UISP installation uses a certificate that cannot be validated locally, the development configuration may use:

```env
UISP_VERIFY_SSL=false
```

For production deployments, TLS certificate validation should generally be enabled where possible.

---

## `SyntaxError: source code string cannot contain null bytes`

This can occur when a package inside the Python virtual environment has become corrupted.

The project includes a Windows repair workflow.

Run:

```bat
repair_windows.bat
```

If the script is unavailable in your working copy, recreate the environment manually:

```powershell
rmdir /s /q .venv
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

---

## No devices appear

Check the backend health endpoint:

```text
http://localhost:5000/api/health
```

Then verify that:

```text
configured
```

is `true`.

Also verify that the backend can reach the UISP instance and that the API token has appropriate access.

---

## Report generation fails

Check:

1. At least one device is selected.
2. The selected device IDs still exist in UISP.
3. Required UISP endpoints are accessible.
4. The backend has permission to create files inside `backend/reports/`.
5. The selected telemetry period is one of:

```text
1h
6h
24h
7d
```

The UISP Inspector can be used to identify which endpoint is failing.

---

# 🧪 Development

Run the backend:

```powershell
cd backend
.venv\Scripts\activate
python app.py
```

Run the frontend:

```powershell
cd frontend
npm run dev
```

Build the frontend:

```powershell
npm run build
```

Preview the production frontend build:

```powershell
npm run preview
```

---

# 📦 Production Considerations

The current application is structured for local development and deployment, but production environments should additionally consider:

- Running Flask behind a production WSGI server
- HTTPS termination
- Restricting CORS origins
- Enabling SSL verification
- Secure secret management
- Authentication/authorization for application users
- Report retention and cleanup
- Rate limiting
- Request logging
- Structured application logging
- Background report generation for large device inventories
- Persistent report storage
- Monitoring and health checks

For large UISP installations, asynchronous report generation would also prevent long-running PDF generation requests from blocking the API request lifecycle.

---

# 🔮 Future Improvements

Potential improvements include:

- [ ] User authentication and role-based access
- [ ] Scheduled report generation
- [ ] Email delivery of reports
- [ ] Report history
- [ ] Report deletion/retention policies
- [ ] Persistent report metadata
- [ ] Advanced device filtering
- [ ] Date-range based reporting
- [ ] Custom report templates
- [ ] Organization/site-based reports
- [ ] Background job processing
- [ ] Redis/Celery-based report workers
- [ ] Automated API tests
- [ ] Frontend component tests
- [ ] CI/CD pipeline
- [ ] Docker deployment
- [ ] Production observability
- [ ] More UISP endpoint integrations

---

# 📌 Design Principles

### 1. UISP is the source of truth

The application reports what UISP returns rather than inventing missing information.

### 2. Device-agnostic collection

The collector should work across different UISP-managed device types without relying on a single hard-coded device schema.

### 3. Graceful degradation

Optional endpoint failures should not unnecessarily prevent the entire report from being generated.

### 4. Preserve raw data

Data that does not yet have a dedicated visual representation should remain accessible through the report appendix.

### 5. Keep credentials server-side

UISP authentication credentials should never be exposed to the React client.

### 6. Separate collection from presentation

UISP API communication and PDF rendering are handled by separate backend modules, making the system easier to extend and maintain.

---

# 🤝 Contributing

Contributions are welcome.

A typical workflow is:

```bash
git checkout -b feature/report-improvements
```

Make your changes, test locally, and commit:

```bash
git add .
git commit -m "feat: improve report generation"
```

Then push the branch:

```bash
git push origin feature/report-improvements
```

When contributing, keep the following in mind:

- Do not commit secrets.
- Do not commit generated reports.
- Keep UISP API logic inside the client layer.
- Keep report formatting inside the report engine.
- Avoid hard-coded device assumptions.
- Preserve graceful handling of optional UISP endpoints.

---

# 📄 License

Add the project's applicable license here.

If this is an internal/proprietary project, replace this section with the organization's approved licensing and usage terms.

---

<div align="center">

### UISP Reporter

**Live UISP data → intelligent collection → structured reporting → PDF**

Built with React, Flask, Python, and the UISP API.

</div>
