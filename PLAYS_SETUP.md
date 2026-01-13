# Plays Module Setup Guide

This guide explains how to set up and use the new Plays feature in HoopsStats.

## Overview

The Plays module provides a complete playbook management system based on the DR 4 Playbook 2025-2026. It includes:

- **65+ Pre-loaded Plays**: Offensive, Defensive, and Special plays from the DR 4 playbook
- **Play Gallery**: Grid view with filtering by play type
- **Detailed Views**: Full play information with descriptions and diagrams
- **CRUD Operations**: Add, edit, view, and delete plays
- **Image Support**: Upload play diagrams and photos
- **Search API**: Quick play search functionality

## File Structure

```
core/
├── models.py                 # Play model definition
└── seed_plays.py             # Pre-loaded plays data (65 plays)

web/
├── routes/
│   └── plays.py              # Play routes and business logic
└── templates/
    └── plays/
        ├── index.html        # Play gallery/list view
        └── view.html         # Detailed play view with edit/delete

web/static/uploads/
└── plays/                    # Directory for play diagram uploads

cli.py                        # CLI utility for database operations
PLAYS_SETUP.md                # This file
```

## Installation & Setup

### Step 1: Create Database Tables

Run the Flask CLI command to initialize the database:

```bash
flask init-db
```

This creates the `plays` table in your database.

### Step 2: Seed Pre-loaded Plays

Populate the database with 65 plays from the DR 4 playbook:

```bash
flask seed
```

This command:
- Adds 20 offensive plays (PNR, Isolation, Screens, etc.)
- Adds 20 defensive plays (Man-to-Man, Zones, Press, etc.)
- Adds 25 special plays (Out of bounds, ATO, Quick clock, etc.)

### Step 3: Create Uploads Directory

Make sure the uploads directory exists:

```bash
mkdir -p web/static/uploads/plays
```

This directory stores uploaded play diagrams.

### Step 4: Register Blueprint (if not already done)

Ensure the plays blueprint is registered in `web/__init__.py`:

```python
from web.routes.plays import plays_bp
app.register_blueprint(plays_bp)
```

## Usage

### Accessing the Plays Module

1. **Sidebar**: Click "Plays" in the left sidebar
2. **URL**: Navigate to `http://localhost:5000/plays`

### Features

#### List View
- **Filter by Type**: Buttons to show All, Offense, Defense, or Special plays
- **Play Cards**: Grid layout showing play name, type badge, and description preview
- **Quick Actions**: View, Edit, or Delete buttons on each card
- **Add New Play**: Button to open modal for creating plays

#### Detail View
- **Full Description**: Complete play explanation
- **Play Diagram**: Image/diagram of the play
- **Metadata**: Type and created date
- **Edit/Delete**: Manage play information

#### Add/Edit Play Modal
- **Name**: Required field for play name (must be unique)
- **Type**: Select Offense, Defense, or Special
- **Description**: Detailed play explanation
- **Diagram**: Upload PNG, JPG, GIF, or WEBP image

### Pre-loaded Plays Reference

#### Offensive Plays (20)
- Horns Twist, Spain PNR, Dribble Handoff
- Pick and Pop, Pick and Roll, High Post Entry
- Wing Isolation, Weak Side Cut, Ball Screen
- Flare Screen, Staggered Screen, Cross Screen
- UCLA Cut, Zipper Cut, Back Screen
- Down Screen, Transition Offense, Triangle Offense
- Motion Offense, Spread P&R

#### Defensive Plays (20)
- Man-to-Man Defense, Zone Defense
- 2-3 Zone, 3-2 Zone, 1-3-1 Zone
- Box-and-One, Triangle-and-Two
- Full Court Press, Half Court Press
- Trap and Recover, Screen Coverage
- Switch Defense, Drop Coverage, High Coverage
- Hedging, Help and Recover, Deny Ball Handler
- Weak Side Rotation, Transition Defense, Rebounding Position

#### Special Plays (25)
- Inbound from Sideline, Inbound from Baseline
- Against Full Court Press, Against Half Court Press
- Baseline Out of Bounds, Sideline Out of Bounds
- Backdoor Cut, Lob Play, Curl to Three
- Punch Through, Elevator Door, Pick Pocket
- Crash Boards, Short Clock, Game Winner
- And more...

## Database Reset

If you need to reset everything and start fresh:

```bash
flask reset-db
```

⚠️ **Warning**: This will delete all plays and require confirmation. Use carefully!

## API Endpoints

The plays module includes REST API endpoints:

### Get Play Types
```
GET /plays/api/types
```

Response:
```json
["Offense", "Defense", "Special"]
```

### Search Plays
```
GET /plays/api/search?q=pick
```

Response:
```json
[
  {"id": 1, "name": "Pick and Roll", "type": "Offense"},
  {"id": 2, "name": "Pick and Pop", "type": "Offense"}
]
```

## File Upload Configuration

**Allowed Extensions**: png, jpg, jpeg, gif, webp
**Max File Size**: No built-in limit (configure in Flask if needed)
**Upload Directory**: `web/static/uploads/plays/`

## Troubleshooting

### Plays Not Showing After Seed
1. Restart Flask application
2. Verify database was initialized: `flask init-db`
3. Check plays were seeded: Query database directly

### Upload Fails
1. Ensure `web/static/uploads/plays/` directory exists and is writable
2. Verify file extension is in allowed list (png, jpg, jpeg, gif, webp)
3. Check file permissions on the uploads directory

### Play Type Filter Not Working
1. Clear browser cache
2. Verify play_type values match in database ("Offense", "Defense", "Special")
3. Check database query in `web/routes/plays.py`

### Delete Operation Fails
1. Check if associated image file exists
2. Verify write permissions to uploads directory
3. Ensure play ID exists in database

## Future Enhancements

- [ ] PDF upload with automatic OCR extraction
- [ ] Play video demonstrations
- [ ] Playbook versioning and comparison
- [ ] Play statistics and usage tracking
- [ ] Team-specific play customization
- [ ] Play drill sequences
- [ ] Player assignment to plays
- [ ] Play variant management
- [ ] Advanced filtering and search
- [ ] Bulk import from external playbooks

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review the code comments in `core/seed_plays.py`
3. Verify all files were created correctly
4. Check Flask logs for error messages

## Integration with Other Modules

The Plays module is designed to integrate with:
- **Games Module**: Associate plays with games
- **Players Module**: Track which players execute plays
- **Analytics Module**: Analyze play effectiveness
- **Video Module** (future): Link plays to game footage

---

**Last Updated**: January 12, 2026  
**Version**: 1.0  
**Status**: Production Ready
