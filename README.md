# RideOps Support Intelligence — v0

A working Flask + SQLite support-operations prototype built on the supplied RideOps ticket dataset.

The ticket dataset is not included in this repository because it contains client-identifying fields. To run the app, place an authorized dataset at `data/rideops_support_tickets.csv`; the local database is created automatically.

## Run locally

### macOS / Linux
1. Install Python 3.10+.
2. Open a terminal in this folder.
3. Run:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   python app.py
   ```
4. Open http://127.0.0.1:5000.

### Windows
1. Install Python 3.10+.
2. Double-click `run_windows.bat`, or run it from Command Prompt.
3. Open http://127.0.0.1:5000.

The Mac/Linux launcher also creates a virtual environment and installs requirements.

## What works
- Dashboard KPIs and trends are computed from the supplied 1,444-ticket CSV.
- Smart Queue searches and filters tickets by status, priority, category, owner and text; it sorts open work using a transparent Gate Score.
- Ticket Assistant displays category-specific L1 checklists. Checklist state, ticket status, owner and notes are saved in SQLite, with an audit entry for each action.
- Support Insights shows category volumes, escalation outcomes, escalation/return rates, reopens, resolution time and CSAT.
- Knowledge Base searches a small starter set of category playbooks and troubleshooting notes.
- Settings lets the support lead change the engineering-age threshold.
- CSV export downloads the original ticket dataset.

## Data handling and assumptions
- Historical source of truth: `data/rideops_support_tickets.csv` (1,444 tickets created 2 July–30 September 2026).
- The source data is not overwritten. Local workflow changes are stored separately in `rideops.sqlite3`.
- The source snapshot has 48 open tickets: 29 Open - with L1 and 19 Open - with Engineering.
- Open-ticket age is calculated against the supplied 30 September 2026 snapshot, not the computer's current clock.
- Engineering return rate is defined as (Insufficient info - returned to L1 + Config issue - returned to L1) / all tickets escalated to engineering. This is 173 / 486 = 35.6%.
- The dashboard's historical escalation and CSAT metrics remain tied to the CSV; newly logged actions are an operational overlay and do not rewrite historical outcomes.
- Knowledge Base content and team directory are starter/demo content. Team management, real notifications, client messaging and live engineering-system integrations are not implemented.
- "Chase engineering" and "client update" actions are logged in the audit trail; they do not send external messages.

## Reset local state
Stop the server and delete `rideops.sqlite3`. It will be recreated on the next run. The CSV remains unchanged.

## Stack
Python, Flask, SQLite, vanilla JavaScript, HTML and CSS. No external API key or paid service is required.
