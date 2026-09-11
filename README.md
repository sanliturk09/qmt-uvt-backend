# QMT Shop Floor & Production Execution System (UVT)

A high-performance, real-time Manufacturing Execution System (MES) and production tracking engine integrated with **SAP Business One**. 
Designed for high-mix, discrete manufacturing environments to digitize shop-floor operations, track operator labor telemetry, 
balance welding workstation workloads, and provide production planners with an interactive scheduling cockpit.

Architecture Overview

[ SAP Business One (MSSQL) ]
            │
            ▼ (Sync Pipeline / Direct Queries)
[ UVT Production Database (UVT_DB) ]
            │
            ▼ (pyodbc Connection Pooling)
[ FastAPI Async Telemetry Core (main.py) ]
      │                                │
      ▼ (REST / JSON / Polling)        ▼ (REST / JSON / Polling)
[ Planner Cockpit Interface ]    [ Shop Floor Workstation Terminals ]
(cockpit.html)                   (station.html)

Technology Stack
     Layer                                              Technology
Backend Framework                         Python 3.12, FastAPI, Uvicorn (ASGI)
Database & Engine                     Microsoft SQL Server (MSSQL), T-SQL CTEs, pyodbc
Security                              JWT (JSON Web Tokens), Passlib, Bcrypt hashing
Frontend                      Vanilla JavaScript (ES6+ Fetch API), Semantic HTML5, Custom Dark-Themed CSS3
Process Management                     Windows Server NSSM (Non-Sucking Service Manager)

| Method | Endpoint | Role | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/auth/login` | Public | Authenticates credentials and returns JWT bearer token. |
| `GET` | `/api/jobs/queue` | Operator, Planner | Fetches unlocked, actionable operations for a target workstation. |
| `POST` | `/api/jobs/start` | Operator | Initializes a work session and creates a `START` telemetry log. |
| `POST` | `/api/jobs/pause` | Operator | Freezes duration counter, writes stoppage reason to `PAUSE` log. |
| `POST` | `/api/jobs/complete` | Operator | Finalizes stage, logs good/scrap quantities, triggers downstream routing. |
| `GET` | `/api/jobs/{operation_id}/lzr-batches` | LZR operator | Reads the exact component's live, positive-quantity SAP B1 batch lots. |
| `GET` | `/api/cockpit/operations` | Planner, Admin | Returns unified live scheduling board with progress calculations. |
| `POST` | `/api/cockpit/schedule` | Planner, Admin | Updates operation assigned dates and workstations via drag-and-drop. |
| `GET` | `/api/cockpit/workstations` | Public | Returns active workstations associated with a specific category. |
| `GET` | `/api/cockpit/station-status` | Planner, Admin | Live floor telemetry monitor showing active, paused, or idle stations. |
| `GET` | `/api/cockpit/shipping-orders` | Planner, Admin | Retrieves fully completed orders ready for final quality dispatch. |
| `POST` | `/api/cockpit/close-orders` | Planner, Admin | Permanently archives and closes finished production orders. |
| `POST` | `/api/jobs/sync-from-sap` | Planner, Admin | Pulls and syncs open production orders directly from SAP Business One. |

Installation & Local Setup: (Only 4 Steps...)

1. Clone Repository
git clone [https://github.com/sanliturk09/qmt-uvt-backend.git](https://github.com/sanliturk09/qmt-uvt-backend.git)
cd qmt-uvt-backend

2. Environment Configuration
Create a .env file in the root directory following .env.example:

3. Install Dependencies
python -m venv .venv
# Windows
.\.venv\Scripts\Activate.ps1
# Linux
source .venv/bin/activate

pip install -r requirements.txt

4. Run Development Server
uvicorn main:app --reload --host 0.0.0.0 --port 8000

LZR Batch Traceability

Before deploying the LZR batch-selection feature, execute
`migrations/20260911_lzr_batch_selections.sql` once against `UVT_DB`. This
creates an UVT-only audit table; it does not alter SAP Business One data.

The SAP B1 company database is read through `SAP_TR_DB_NAME` (default:
`QMT_TR_TEST`) or `SAP_DE_DB_NAME`. The LZR screen only lists `OIBT` batches
with `Quantity > 0`, and every selected batch remains
visible on downstream job cards and in the shipping list.



Author
Developed by Burak Şanlıtürk
System Administrator & Software Developer

