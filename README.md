# 🏀 Basketball Stats Analyzer

A web application for tracking and analyzing basketball game statistics with advanced metrics.
Docs:https://giuliomastromartino.github.io/Basketball-stats/


## What It Does

- **Import Game Data**: Upload CSV files with player statistics from basketball games
- **Track Performance**: Monitor individual player stats (points, rebounds, assists, shooting percentages)
- **Advanced Analytics**: Automatically calculates True Shooting %, Effective FG%, and Game Score
- **Game History**: View all games with win/loss records and scores
- **Player Comparison**: Compare players across multiple games and metrics
- **Web Interface**: User-friendly dashboard to view and analyze all data

## How It Works

1. **Data Import**: Place CSV files in the `Games/` folder with game statistics
2. **Automatic Processing**: The app parses filenames to extract game info (opponent, score, date)
3. **Database Storage**: All stats are stored in a SQLite database
4. **Analytics Engine**: Calculates advanced basketball metrics automatically
5. **Web Display**: View everything through a clean web interface at http://localhost:8080

## Quick Start (Local)

```bash
# 1. Clone and enter directory
git clone https://github.com/GiulioMastromartino/Basketball-stats.git
cd Basketball-stats

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements-local.txt

# 4. Run the application
python quick_start.py

# 5. Open browser to http://localhost:8080
# Login: admin / admin123
```

## Docker Deployment (TrueNAS Scale / General)

This project includes Docker support for easy deployment on TrueNAS Scale or any Docker environment.

### 1. Build the Image

Since you cannot pull this directly from Docker Hub yet, you need to build the image and push it to your own registry (Docker Hub, GHCR, etc.).

```bash
# 1. Login to your registry
docker login

# 2. Build the image
docker build -t your_username/basketball-stats:latest .

# 3. Push to registry
docker push your_username/basketball-stats:latest
```

### 2. Run with Docker Compose

For a quick test or simple deployment using Docker Compose:

```bash
docker-compose up -d
```
Access the app at `http://localhost:8080`.

### 3. Deploy on TrueNAS Scale (Custom App)

1.  **Log in to TrueNAS Scale**.
2.  Go to **Apps** -> **Discover Apps** -> **Custom App**.
3.  **Application Name**: `basketball-stats`
4.  **Image Configuration**:
    *   **Repository**: `your_username/basketball-stats`
    *   **Tag**: `latest`
    *   **Pull Policy**: `Always`
5.  **Environment Variables**:
    *   **DATABASE_URL**: `sqlite:////app/data/basketball_stats.db`
    *   **SECRET_KEY**: *(Generate a random string)*
6.  **Storage (Volumes)**:
    Map these Host Paths to your TrueNAS datasets to ensure data persists:
    *   **Host Path**: `/mnt/pool/path/to/data` -> **Mount Path**: `/app/data`
    *   **Host Path**: `/mnt/pool/path/to/Games` -> **Mount Path**: `/app/Games`
    *   **Host Path**: `/mnt/pool/path/to/Output` -> **Mount Path**: `/app/Output`
7.  **Networking**:
    *   **Container Port**: `8080`
    *   **Node Port**: `9080` (or any available port)
8.  **Deploy**: Click Save/Install.

## CSV File Format

**Filename Pattern:**
```
Opponent_YourScore-TheirScore_DD-MM-YYYY_Type.csv

Examples:
Lakers_105-98_15-03-2024_S.csv     (Season game)
Warriors_88-92_20-03-2024_P.csv    (Playoff)
Celtics_95-90_25-03-2024_F.csv     (Friendly)
```

**Required Columns in CSV:**
```
Name, MIN, PTS, FGM, FGA, FG%, 3PM, 3PA, 3P%, 
FTM, FTA, FT%, OREB, DREB, REB, AST, TOV, STL, BLK, PF
```

**Import Your Data:**
```bash
# Place CSV files in Games/ folder, then run:
python cli_import.py
```

## Key Features

- 📊 Advanced basketball analytics (TS%, eFG%, Game Score)
- 🏆 Win/loss tracking with opponent records
- 👥 Player performance history and trends
- 🔐 Secure login system
- 📈 Career statistics and averages
- 🌐 REST API with Swagger documentation

## Tech Stack

- **Backend**: Flask 3.0, SQLAlchemy, SQLite
- **Analytics**: Pandas, NumPy
- **Security**: Flask-Login, Bcrypt encryption
- **API**: Flask-RESTx with Swagger UI

## Requirements

- Python 3.8+
- 16MB disk space
- Modern web browser

## Project Structure

```
Basketball-stats/
├── Games/              # Place CSV files here
├── core/               # Analytics and data processing
├── web/                # Web interface and routes
├── quick_start.py      # Setup and run script
├── cli_import.py       # CSV import tool
└── requirements-local.txt
```

## Troubleshooting

**Port already in use?**
```bash
python quick_start.py --port 8080
```

**Reset database?**
```bash
python reset_empty.py
```

**Run app from new database**
```bash
python reset_empty.py
python cli_import.py
python quick_start.py
```

**Import not working?**
- Check filename matches pattern exactly
- Verify all required CSV columns are present
- Ensure no duplicate game files

## License

Apache License 2.0

## Repository

https://github.com/GiulioMastromartino/Basketball-stats

---

**⭐ Star the repo if you find it useful!**

## 🚀 Deployment on TrueNAS Scale

This application can be deployed as a Custom App on TrueNAS Scale (Electric Eel or later).

### Method 1: Docker Compose (Recommended)
1. Navigate to **Apps** > **Discover Apps** > **Custom App** in the TrueNAS UI.
2. Application Name: `basketball-stats`
3. Select **Install via: Docker Compose**.
4. Copy and paste the contents of `docker-compose.yml` from this repository.
5. **Storage Configuration**:
   - The compose file maps `./instance` to `/app/instance`.
   - On TrueNAS, change `./instance` to a valid host path on your ZFS pool (e.g., `/mnt/tank/apps/basketball-stats`) to ensure your database persists across restarts.

### Method 2: Manual CLI
```bash
# Note: Map only the database directory, not the entire app
docker run -d \
  -p 8080:8080 \
  -v /mnt/your-pool/app-data:/app/instance \
  --name basketball-stats \
  giuliomastromartino/basketball-stats:latest
```
