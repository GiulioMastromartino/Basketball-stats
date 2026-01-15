# Getting Started

This guide covers how to install and run the Basketball Stats Tracker locally or using Docker.

## Prerequisites

*   **Python**: 3.8 or higher
*   **Git**: For cloning the repository
*   **Docker** (Optional): For containerized deployment

## Local Installation

The fastest way to get started for development or personal use.

### 1. Clone the Repository

```bash
git clone https://github.com/GiulioMastromartino/Basketball-stats.git
cd Basketball-stats
```

### 2. Set Up Virtual Environment

It is recommended to use a virtual environment to manage dependencies.

```bash
# Create venv
python -m venv venv

# Activate venv
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements-local.txt
```

### 4. Initialize Database

The application comes with scripts to set up the database and seed initial data.

```bash
# Initialize and seed plays
python cli.py init-db
python cli.py seed
```

### 5. Run the Application

```bash
python quick_start.py
```

Open your browser to `http://localhost:8080`.
**Default Login**: `admin` / `admin123`

---

## Docker Deployment

For servers, NAS (like TrueNAS Scale), or cleaner isolation.

### using Docker Compose

1.  Ensure you have Docker and Docker Compose installed.
2.  Run the stack:

```bash
docker-compose up -d
```

The app will be available at `http://localhost:8080`.

### Building the Image

If you need to build the image yourself (e.g., for a custom registry):

```bash
docker build -t your_username/basketball-stats:latest .
docker push your_username/basketball-stats:latest
```

### TrueNAS Scale Deployment

1.  **Log in to TrueNAS Scale**.
2.  Go to **Apps** -> **Discover Apps** -> **Custom App**.
3.  **Application Name**: `basketball-stats`
4.  **Image Configuration**:
    *   **Repository**: `your_username/basketball-stats` (or the one you built)
    *   **Tag**: `latest`
5.  **Environment Variables**:
    *   `DATABASE_URL`: `sqlite:////app/data/basketball_stats.db`
    *   `SECRET_KEY`: (Generate a random string)
6.  **Storage**:
    *   Map a Host Path to `/app/data` to persist your database.
    *   Map a Host Path to `/app/Games` for CSV import.

## Importing Data

To import historical game data from CSV files:

1.  Place your CSV files in the `Games/` directory.
2.  Ensure filenames follow the pattern: `Opponent_YourScore-TheirScore_DD-MM-YYYY_Type.csv`
    *   Example: `Lakers_105-98_15-03-2024_S.csv`
3.  Run the import tool:

```bash
python cli_import.py
```
