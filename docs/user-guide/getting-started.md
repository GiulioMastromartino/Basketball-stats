# Getting Started

<div class="hoops-hero">
  <p class="lead">Track the full game live. Print the halftime report in seconds. Get up and running in under 2 minutes.</p>
</div>

---

## What You'll Get

HoopsLab turns live game tracking into instant intelligence and print-ready coaching documents. After setup you'll have:

- **Live Command Center** — Real-time event logging, possession context, play tagging
- **Automatic Intelligence** — TS%, eFG%, Net Rating, lineup impact, duo/trio combinations
- **Print & Share** — Server-side PDFs (halftime, game, player, lineup, season, clutch)
- **Digital Playbook** — 65+ pre-loaded plays with visual diagram builder

---

## Prerequisites

<div class="step-card">
  <div class="step-number">1</div>
  <div class="step-content">
    <h4>Python 3.11+</h4>
    <p>Check your version: <code>python --version</code>. If you don't have it, download from <a href="https://python.org">python.org</a>.</p>
  </div>
</div>

<div class="step-card">
  <div class="step-number">2</div>
  <div class="step-content">
    <h4>Git</h4>
    <p>Check: <code>git --version</code>. Download from <a href="https://git-scm.com">git-scm.com</a>.</p>
  </div>
</div>

<div class="step-card">
  <div class="step-number">3</div>
  <div class="step-content">
    <h4>Docker (optional)</h4>
    <p>Only needed for containerized deployment. Get <a href="https://docker.com">Docker Desktop</a>.</p>
  </div>
</div>

---

## Quick Start (Under 2 Minutes)

The fastest path to a running app with sample data:

<div class="step-card">
  <div class="step-number">1</div>
  <div class="step-content">
    <h4>Clone the repo</h4>
    <pre><code>git clone https://github.com/GiulioMastromartino/Basketball-stats.git
cd Basketball-stats</code></pre>
  </div>
</div>

<div class="step-card">
  <div class="step-number">2</div>
  <div class="step-content">
    <h4>Create & activate a virtual environment</h4>
    <pre><code>python -m venv venv
source venv/bin/activate   # macOS/Linux
venv\Scripts\activate      # Windows</code></pre>
  </div>
</div>

<div class="step-card">
  <div class="step-number">3</div>
  <div class="step-content">
    <h4>Install dependencies</h4>
    <pre><code>pip install -r requirements-local.txt</code></pre>
    <p>This installs Flask, SQLAlchemy, Pandas, WeasyPrint, and all other dependencies.</p>
  </div>
</div>

<div class="step-card">
  <div class="step-number">4</div>
  <div class="step-content">
    <h4>Run the app</h4>
    <pre><code>python quick_start.py</code></pre>
    <p>This single command:</p>
    <ul>
      <li>Creates the SQLite database</li>
      <li>Creates an admin user & default team</li>
      <li>Seeds 3 sample games with player stats</li>
      <li>Starts the dev server on <strong>http://localhost:8080</strong></li>
    </ul>
  </div>
</div>

<div class="step-card">
  <div class="step-number">5</div>
  <div class="step-content">
    <h4>Log in</h4>
    <p>Open <a href="http://localhost:8080">http://localhost:8080</a> and log in with:</p>
    <table>
      <tr><td><strong>Username</strong></td><td><code>admin</code></td></tr>
      <tr><td><strong>Password</strong></td><td><code>admin123</code></td></tr>
    </table>
  </div>
</div>

!!! tip "What you'll see"
    After logging in you'll see the **Dashboard** with 3 sample games (Lakers win, Warriors loss, Celtics win) and summary metrics. Click any game to explore the full detail page with box scores, shot charts, and advanced stats.

---

## Local Setup (Step by Step)

Use this when you want full control over the setup process.

### 1. Clone & Enter

```bash
git clone https://github.com/GiulioMastromartino/Basketball-stats.git
cd Basketball-stats
```

### 2. Virtual Environment

```bash
python -m venv venv

# Activate:
# macOS/Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

You should see `(venv)` in your terminal prompt.

### 3. Install Dependencies

```bash
pip install -r requirements-local.txt
```

This installs ~20 packages including Flask 3.0, SQLAlchemy 2.0, Pandas, WeasyPrint, and testing tools.

For production deployments use `requirements.txt` instead (adds gunicorn, psycopg2, WorkOS SSO, Prometheus metrics).

### 4. Database Setup

Create all tables and seed initial data:

```bash
# Option A: Quick start (creates DB + sample data + starts server)
python quick_start.py --no-run

# Option B: Manual with Flask CLI
export FLASK_APP=manage.py
flask shell -c "from web import create_app; app=create_app(); app.app_context().push(); from core.models import db; db.create_all()"
```

### 5. Import Your Data

Place CSV files in the `Games/` directory, then:

```bash
python -c "from cli_import import main; main()"
```

Or use the web UI: navigate to **Upload Game** in the sidebar.

### 6. Run the Server

```bash
python quick_start.py
```

Or for more control:

```bash
python run.py --host 0.0.0.0 --port 8080 --env development
```

---

## Docker Setup

For server deployments, NAS (TrueNAS Scale), or cleaner isolation.

### Using Docker Compose (Recommended)

```bash
docker-compose up -d
```

This starts three services:

| Service | Purpose |
|---------|---------|
| `db` | PostgreSQL 16 (persistent storage) |
| `web` | Flask app with Gunicorn on port 8080 |
| `cloudflared` | Optional Cloudflare Tunnel for public access |

The app will be available at `http://localhost:8080`.

### Building the Image Manually

```bash
# Build
docker build -t your-username/basketball-stats:latest .

# Push to registry
docker push your-username/basketball-stats:latest

# Run
docker run -d \
  -p 8080:8080 \
  -e SECRET_KEY="your-secret-key" \
  -v ./instance:/app/instance \
  your-username/basketball-stats:latest
```

### TrueNAS Scale Deployment

1. Go to **Apps** → **Discover Apps** → **Custom App**
2. **Application Name**: `basketball-stats`
3. **Image**: `your-username/basketball-stats:latest`
4. **Environment Variables**:
    - `DATABASE_URL`: `sqlite:////app/data/basketball_stats.db`
    - `SECRET_KEY`: (generate a random string)
5. **Storage**: Map host paths to `/app/data`, `/app/Games`, `/app/Output`
6. **Networking**: Container port `8080` → Node port `9080`

---

## First Steps After Login

Once you're logged in, here's what to do first:

<div class="step-card">
  <div class="step-number">1</div>
  <div class="step-content">
    <h4>Explore the Dashboard</h4>
    <p>Your dashboard shows recent games with win/loss highlighting, summary metrics (Total Games, Active Players, Record, Win Rate), and a list of all games. Click any game card to dive into details.</p>
  </div>
</div>

<div class="step-card">
  <div class="step-number">2</div>
  <div class="step-content">
    <h4>Check the Players Page</h4>
    <p>Browse player cards showing PPG, RPG, APG, EFF, ORtg, PPP, TS%, and USG%. Switch to Table View for all 28+ advanced metrics with color-coded performance indicators.</p>
  </div>
</div>

<div class="step-card">
  <div class="step-number">3</div>
  <div class="step-content">
    <h4>View a Game Detail</h4>
    <p>Click any game to see the full breakdown: Box Score, Advanced Stats, Shot Chart, Plays Analysis, and Lineup Combinations. Download PDF reports from the action bar.</p>
  </div>
</div>

<div class="step-card">
  <div class="step-number">4</div>
  <div class="step-content">
    <h4>Try Live Game Tracking</h4>
    <p>Click <strong>Live Game</strong> in the sidebar to start tracking a game in real-time — shot locations, quarter timer, player substitutions, play tagging, and +/- tracking.</p>
  </div>
</div>

<div class="step-card">
  <div class="step-number">5</div>
  <div class="step-content">
    <h4>Generate PDF Reports</h4>
    <p>Every game, player, and team page has an <strong>Export PDF</strong> button. Try the Visual Game Report, Player Scouting Card, or Clutch Time Report.</p>
  </div>
</div>

---

## Importing Game Data

### CSV Format

**Filename pattern:**
```
Opponent_YourScore-TheirScore_DD-MM-YYYY_Type.csv
```

Examples:

| File | Game Type |
|------|-----------|
| `Lakers_105-98_15-03-2024_S.csv` | Season |
| `Warriors_88-92_20-03-2024_P.csv` | Playoff |
| `Celtics_95-90_25-03-2024_F.csv` | Friendly |

**Required columns:**
```
Name, MIN, PTS, FGM, FGA, FG%, 3PM, 3PA, 3P%,
FTM, FTA, FT%, OREB, DREB, REB, AST, TOV, STL, BLK, PF
```

**Import:**
```bash
# Place your CSV files in the Games/ folder, then:
python -c "from cli_import import main; main()"
```

### PDF & JSON Import

You can also upload PDF game reports (parsed automatically) or JSON exports directly through the web UI at **Upload Game** in the sidebar.

---

## Configuration

Key environment variables you can set in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | auto-generated | Flask session signing key |
| `DATABASE_URL` | `sqlite:///basketball_stats.db` | Database connection string |
| `FLASK_ENV` | `development` | `development`, `testing`, or `production` |
| `DISABLE_AUTH` | `false` | Set to `true` for single-user setups |
| `GAMES_DIR` | `./Games` | Directory for CSV import files |
| `OUTPUT_DIR` | `./Output` | Directory for generated outputs |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `MAIL_SERVER` | `smtp.gmail.com` | SMTP server for email reports |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **Port 8080 already in use** | `python quick_start.py --port 8081` or `python run.py --port 8081` |
| **Database errors** | `python quick_start.py --reset` to reset and recreate |
| **Module not found** | Make sure your virtual environment is activated and `pip install -r requirements-local.txt` completed |
| **CSV import fails** | Check filename matches pattern exactly, verify all required columns are present |
| **PDF generation fails** | Ensure WeasyPrint is installed correctly — on macOS: `brew install pango` |
| **Docker build fails** | Ensure Docker has enough memory allocated (minimum 4GB recommended) |

---

## Next Steps

- [Live Game Tracking](live-game.md) — Set up and run a live game session
- [Plays Management](plays.md) — Build your digital playbook
- [Analytics & Reports](advanced-analytics.md) — Understand advanced metrics
- [PDF Exports](pdf-exports.md) — Generate professional reports
- [Deployment Guide](../technical/deployment.md) — Production deployment options
