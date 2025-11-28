# Basketball Stats Analyzer

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements-local.txt

# 2. Setup and run
python quick_start.py --run

# 3. Open browser
# http://localhost:5000
# Login: admin/admin123
```

## Import CSV Files

Place CSV files in `Games/` folder with format:
```
Opponent_TeamScore-OpponentScore_DD-MM-YYYY_Type.csv
Example: Lakers_105-98_15-03-2024_S.csv
```

Then run:
```bash
python cli_import.py
```

## Features

- User authentication & authorization
- Advanced basketball analytics (TS%, eFG%, PER, Game Score)
- Win/Loss tracking with score analysis
- REST API with Swagger docs
- Player comparison tools
- Team performance analytics

## Tech Stack

- Flask 3.0
- SQLAlchemy ORM
- SQLite (local) / PostgreSQL (production)
- Pandas for analytics
- Flask-Login for auth
- Flask-RESTx for API
