# Verify the Alert System

This guide walks through verifying the new **risk & health-score alert system**,
end to end. It covers the database, the API endpoints, email notifications and
the automated background checks.

---

## 1. What was added (quick reference)

| Piece | Location |
|-------|----------|
| `alerts` table | `portfolio_db_setup/schema.py` (added to `TABLE_SQL` / `INDEX_SQL`) |
| Alert DB access | `backend/app/models/alerts.py` |
| Alert schemas | `backend/app/schemas/alerts.py` |
| Health score + evaluation + email | `backend/app/services/alerts.py` |
| Alert API routes | `backend/app/routers/alerts.py` |
| Router registration + background task | `backend/app/__init__.py` |
| Unit tests | `backend/tests/test_alerts.py` |

**Endpoints:**

- `GET  /api/v1/alerts?userId=1` → alerts list + `unread_count` + `health_scores`
- `POST /api/v1/alerts/check?userId=1&sendEmail=false` → run the check now
- `POST /api/v1/alerts/{alert_id}/read` → mark an alert as read (idempotent)

**Health score** = weighted composite (0–100) of Sharpe (25%), volatility (20%),
max drawdown (20%), VaR95 (20%), beta (15%). Bands: ≥ 80 **Healthy**, 60–79
**Fair**, < 60 **Abnormal**.

**Alert thresholds (hardcoded):**

| Metric | Warning | Critical |
|--------|---------|----------|
| Sharpe ratio | < 0 | – |
| Annualized volatility | > 40% | > 60% |
| Max drawdown | < −20% | < −35% |
| VaR 95% | > 3% | > 5% |
| Beta | > 1.5 | – |
| Health score | < 60 | < 40 |

---

## 2. Prerequisites

- MySQL running on `localhost:3306` with the `portfolio_db` database.
- Backend deps installed (`pip install -r portfolio_db_setup/requirements.txt`).

---

## 3. Apply the database change

Run the schema setup (idempotent — safe to re-run):

```powershell
cd portfolio_db_setup
python -c "from create_database import create_tables, create_indexes; create_tables(); create_indexes()"
```

Verify the table exists:

```powershell
mysql -u root -p portfolio_db -e "DESCRIBE alerts"
```

Expected columns: `alert_id, portfolio_id, user_id, category, severity, metric,
observed_value, threshold, message, is_read, created_at`.


---

## 4. (Optional) Enable email alerts

Email only sends when SMTP is configured. Set these environment variables
**before** starting the backend:

```powershell
$env:SMTP_HOST     = "smtp.gmail.com"
$env:SMTP_PORT     = "587"
$env:SMTP_USER     = "your_address@gmail.com"
$env:SMTP_PASSWORD = "your_app_password"
$env:SMTP_FROM     = "your_address@gmail.com"
```

Recipients come from the `email` column of the `users` table, so make sure the
user row has an email (check: `SELECT user_id, user_name, email FROM users;`).

To change how often the automatic background check runs (default 1 hour), set
`ALERT_CHECK_INTERVAL_SECONDS` in `backend/.env` (the config file already has it
at `3600`):

```powershell
# backend/.env
ALERT_CHECK_INTERVAL_SECONDS=600   # 600 = every 10 minutes
```

The env var works the same way (`$env:ALERT_CHECK_INTERVAL_SECONDS = "600"`),
with the real environment variable taking precedence over `.env`. The background
check emails alerts **just like the manual trigger**: newly created alerts are
emailed, and if a run creates none it falls back to emailing any still-pending
unread alerts.

---

## 5. Start the backend

```powershell
cd backend
uvicorn main:app --reload
```

Then open http://127.0.0.1:8000/docs — you should see an **Alerts** section
with the three endpoints above.

---

## 6. Verification steps

Run these in a second terminal (PowerShell examples).

### 6a. Empty state — no alerts yet

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/alerts?userId=1" | ConvertTo-Json -Depth 5
```

Expect:
- `alerts: []`
- `unread_count: 0`
- `health_scores`: one entry per portfolio with a `score` (0–100), `band`
  (`Healthy`/`Fair`/`Abnormal`), `components`, and `metrics`.

### 6b. Trigger alerts with a real "abnormal" check

A check only creates alerts when something actually crosses a threshold. To
verify alert *creation*, first confirm the check runs at all:

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/alerts/check?userId=1" | ConvertTo-Json -Depth 5
```

Expect `portfolios_checked: <N>` and `health_scores` populated. If your demo
portfolio is healthy, `alerts_created` will be `0` (that's correct).

To see alerts actually being generated, you can **insert a synthetic abnormal
alert** directly (this also exercises the DB):

```powershell
cd backend
python -c "from app.services import alerts as s; from app.models import alerts as m; m.insert_alert(s.evaluate_metrics({'annualized_volatility':0.7,'sharpe_ratio':-1.5,'max_drawdown':-0.6,'value_at_risk_95':0.08,'beta':2.0},2,1)[0]); print('inserted')"
```

Then re-query:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/alerts?userId=1" | ConvertTo-Json -Depth 5
```

Expect `alerts` to contain a row with `category: risk`, `severity: critical`,
`metric: annualized_volatility`, and `unread_count` ≥ 1.

### 6c. Mark an alert as read

Take an `alert_id` from the previous response and run:

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/alerts/1/read"
```

Expect `{"alert_id":1,"is_read":true}`. Repeating the same call returns `200`
again (idempotent). A missing id returns `404`.

`GET /api/v1/alerts?userId=1` should now show a lower `unread_count`.

### 6d. Deduplication (background spam protection)

Re-running the check within 24 hours must **not** duplicate alerts (dedupe is
window-based and ignores read state, so a condition that stays broken re-alerts
at most ~once per day). Run the check twice with an active alert present:

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/alerts/check?userId=1"
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/alerts/check?userId=1"
```

Expect `alerts_created: 0` on the second run.

### 6e. Email (only if you configured SMTP in step 4)

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/alerts/check?userId=1&sendEmail=true"
```

Expect `emailed: true`, `emails_sent: 1`, and the email arrives at the address
in the `users.email` column. If SMTP isn't configured, `emailed` stays `false`
and in-app alerts still work.

**Auto mark-as-read:** any alert that gets emailed is automatically marked as
read right after the send succeeds, so `GET /alerts?userId=1` then shows
`unread_count: 0`. If the send fails, the alerts stay unread (no data loss).

> **Note:** a synthetic alert inserted straight into the DB row (section 6b) is
> *displayed* by `GET /alerts` but does **not** fire an email on its own — the
> check only emails what it *creates* or what's pending unread. That is why the
> `sendEmail=true` fallback above exists: it emails the pending unread alerts
> and then marks them read.

### 6f. Automatic background check

With the backend running, the `_run_periodic_alert_check` task runs every
`ALERT_CHECK_INTERVAL_SECONDS` (default 3600s). To see it quickly, restart the
server with:

```powershell
$env:ALERT_CHECK_INTERVAL_SECONDS = "30"
cd backend
uvicorn main:app --reload
```

Wait ~30 seconds, then:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/alerts?userId=1" | ConvertTo-Json -Depth 3
```

New alerts (if any thresholds are crossed) appear without any manual action.
The background check emails just like the manual trigger: alerts created that
run are emailed, and if nothing was created it emails any still-pending unread
alerts, then marks the emailed ones read. Because of the 24h dedupe, a condition
that stays broken re-alerts at most ~once per day rather than every interval.

---

## 7. Run the unit tests

```powershell
cd backend
python -m pytest tests/test_alerts.py -q
```

Expect **40 passed** (36 score/threshold + message tests, plus 4 email +
auto-mark-as-read tests). The full suite (`python -m pytest tests -q`) should
show **49 passed**.

---

## 8. Clean up

Remove any synthetic alerts you inserted during testing:

```powershell
mysql -u root -p portfolio_db -e "DELETE FROM alerts;"
```

Or, if you'd rather keep the new table pristine while playing with the API,
delete only rows you created.
