# Basketball Stats Tracker

![Status](https://img.shields.io/badge/status-active-success.svg)
![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)
![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)

A professional web application for tracking, analyzing, and visualizing basketball game statistics with advanced metrics and PDF reporting.

## Overview

Basketball Stats Tracker is designed for coaches, analysts, and enthusiasts who need deep insights into game performance. It goes beyond basic box scores to provide:

*   **Live Game Tracking**: Record shots, fouls, and plays in real-time.
*   **Advanced Analytics**: True Shooting % (TS%), Effective Field Goal % (eFG%), and Game Score.
*   **Playbook Management**: Manage offensive and defensive plays and track their effectiveness.
*   **Professional Reporting**: Generate PDF reports for games, players, and teams.

## Key Features

### 📊 Advanced Analytics
Automatically calculates advanced metrics that matter:
*   **True Shooting % (TS%)**: Measures shooting efficiency taking into account field goals, 3-pointers, and free throws.
*   **Effective FG% (eFG%)**: Adjusts for the fact that a 3-point field goal is worth more than a 2-point field goal.
*   **Game Score**: A holistic measure of a player's productivity for a single game.

### 🎥 Live Game Tracking
*   **Real-time Entry**: Optimized interface for mobile and tablet use.
*   **Shot Charting**: Track shot locations and types.
*   **Play Tagging**: Associate shots with specific plays from your playbook.

### 📋 Playbook Management
*   **Digital Playbook**: Store and organize 65+ pre-loaded plays.
*   **Visual Diagrams**: Upload and view play diagrams.
*   **Effectiveness Tracking**: Analyze which plays yield the highest points per possession.

### 📄 Professional Exports
*   **PDF Reports**: Download comprehensive game, player, and team reports.
*   **Team Analysis**: Season-long performance tracking.
*   **Shareable**: Ready-to-print formats for coaching staff and players.

## Getting Started

To get up and running quickly, check out the [Installation Guide](user-guide/getting-started.md).

For detailed usage instructions:

*   [Live Game Tracking](user-guide/live-game.md)
*   [Plays Management](user-guide/plays.md)
*   [PDF Exports](user-guide/pdf-exports.md)

## Technology Stack

*   **Backend**: Python 3.8+, Flask 3.0, SQLAlchemy
*   **Database**: SQLite (easy setup, reliable)
*   **Frontend**: HTML5, Bootstrap 5, JavaScript
*   **Analysis**: Pandas, NumPy
*   **Reporting**: ReportLab (PDF generation)

## License

This project is licensed under the Apache License 2.0.
