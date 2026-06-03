# HoopsLab

<div class="hoops-hero">
  <p class="lead">Track the full game live. Print the halftime report in seconds.<br>
  One tool for coaches who need instant intelligence — not post-game spreadsheets.</p>
</div>

<div class="hoops-metrics">
  <div class="hoops-metric">
    <div class="value">&lt;1s</div>
    <div class="label">PDF render</div>
  </div>
  <div class="hoops-metric">
    <div class="value">100%</div>
    <div class="label">Game-day flow</div>
  </div>
  <div class="hoops-metric">
    <div class="value">1 tool</div>
    <div class="label">Track → Share</div>
  </div>
</div>

<div class="feature-grid">
  <div class="feature-card">
    <div class="icon">🎥</div>
    <h3>Live Command Center</h3>
    <p>Real-time event logging with shot clock, quarter timer, player subs, and play tagging. Halftime-ready summaries in seconds.</p>
  </div>
  <div class="feature-card">
    <div class="icon">📊</div>
    <h3>Automatic Intelligence</h3>
    <p>TS%, eFG%, Net Rating, lineup impact, duo/trio matrices, and shot quality models — calculated instantly from your tracking data.</p>
  </div>
  <div class="feature-card">
    <div class="icon">📄</div>
    <h3>Print & Share</h3>
    <p>Server-side PDF reports for games, players, lineups, seasons, and clutch situations. Export as ZIP bundles or email to players.</p>
  </div>
  <div class="feature-card">
    <div class="icon">🎯</div>
    <h3>Shot Charts & Heatmaps</h3>
    <p>Court-mapped shot locations with hexbin heatmaps and zone efficiency analysis. See hot and cold areas at a glance.</p>
  </div>
  <div class="feature-card">
    <div class="icon">👥</div>
    <h3>Lineup Analytics</h3>
    <p>On/off court splits, duo/trio compatibility, 5-man unit rankings, and rotation analysis. Know who works with whom.</p>
  </div>
  <div class="feature-card">
    <div class="icon">📋</div>
    <h3>Digital Playbook</h3>
    <p>65+ pre-loaded plays with a visual diagram builder. Track play effectiveness with points-per-possession analysis.</p>
  </div>
</div>

---

## Quick Start

<div class="step-card">
  <div class="step-number">1</div>
  <div class="step-content">
    <pre><code>git clone https://github.com/GiulioMastromartino/Basketball-stats.git
cd Basketball-stats</code></pre>
  </div>
</div>

<div class="step-card">
  <div class="step-number">2</div>
  <div class="step-content">
    <pre><code>python -m venv venv && source venv/bin/activate
pip install -r requirements-local.txt</code></pre>
  </div>
</div>

<div class="step-card">
  <div class="step-number">3</div>
  <div class="step-content">
    <pre><code>python quick_start.py</code></pre>
    <p>Open <a href="http://localhost:8080">http://localhost:8080</a> — login: <code>admin</code> / <code>admin123</code></p>
  </div>
</div>

<p style="text-align:center;margin-top:1.5rem">
  <a href="user-guide/getting-started.md" class="md-button md-button--hoops">Full Getting Started Guide</a>
  <a href="user-guide/live-game.md" class="md-button md-button--cool">Live Game Tracking</a>
</p>

---

## What's Inside

### 🎥 Live Game Tracking
- Real-time entry optimized for mobile and tablet
- Shot charting with court location tracking
- Play tagging — associate shots with specific plays
- Halftime and final PDF summaries

### 📊 Analytics Engine
- True Shooting % (TS%), Effective FG% (eFG%), Game Score
- True Usage Rate (USG%), Points Per Shot (PPS)
- Shot Quality Model with expected values by zone
- Clutch performance analysis (score within 5, under 5 minutes)
- Four Factors analysis (Dean Oliver)

### 👥 Lineup Intelligence
- On/off court splits with Net Rating differential
- Duo compatibility with Synergy Factor
- 5-man lineup efficiency rankings
- Rotation analysis with substitution patterns

### 📋 Playbook Management
- 65+ pre-loaded offensive, defensive, and special plays
- Visual diagram builder with Fabric.js canvas
- Effectiveness tracking (PPP, FG% by play)
- Animation sequences for player movement

### 📄 PDF Reports
- Game Summary with shot charts
- Player Scouting Cards with hot zones
- Visual Game Report (Score Worm, Four Factors)
- Season Trend Report with rolling averages
- Clutch Time Report
- Lineup Analysis Report
- ZIP bundle export for entire team

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| **Backend** | Python 3.11+, Flask 3.1, SQLAlchemy 2.0 |
| **Database** | SQLite (dev), PostgreSQL 16 (production) |
| **Frontend** | Bootstrap 5.3, Jinja2, Fabric.js |
| **Charts** | Matplotlib, Chart.js |
| **PDF** | WeasyPrint, ReportLab |
| **Performance** | Rust via PyO3 (shot quality, zone analysis) |
| **Auth** | Flask-Login, WorkOS SSO |
| **Container** | Docker, docker-compose |
| **Mobile** | iOS native app (Swift/SwiftUI) |

---

## License

Apache License 2.0
