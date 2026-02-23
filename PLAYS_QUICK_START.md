# Plays Module - Quick Start Guide

## TL;DR - 2 Commands to Get Started

```bash
# 1. Initialize database
flask init-db

# 2. Create uploads directory
mkdir -p web/static/uploads/plays
```

**Then restart Flask and navigate to:** `http://localhost:5000/plays`

**Note:** Plays are created automatically when games are imported. There are no pre-loaded plays.

---

## What Was Created

| File | Purpose |
|------|----------|
| `web/routes/plays.py` | Routes for CRUD operations |
| `web/templates/plays/index.html` | Play gallery (grid view) |
| `web/templates/plays/view.html` | Play detail page |
| `cli.py` | CLI commands (init-db, reset-db) |
| `PLAYS_SETUP.md` | Full documentation |
| Sidebar | Added "Plays" link to navigation |

---

## Features at a Glance

✓ **Dynamic Plays** - Created from imported game data  
✓ **Filter by Type** - Offense, Defense, Special  
✓ **Grid Gallery** - Beautiful card layout  
✓ **Add/Edit/Delete** - Full CRUD operations  
✓ **Image Upload** - Diagrams and photos (PNG, JPG, GIF, WEBP)  
✓ **Search API** - JSON endpoints for integration  
✓ **Responsive** - Works on mobile and desktop  
✓ **Modals** - Inline workflows for add/edit/delete  

---

## Common Tasks

### Add a New Play
1. Navigate to `/plays`
2. Click "Add New Play" button
3. Fill in name, type, description
4. Optionally upload diagram
5. Click "Add Play"

### View Play Details
1. Navigate to `/plays`
2. Click "View" on any play card
3. See full description and image
4. Options to Edit or Delete

### Filter Plays
1. Navigate to `/plays`
2. Click filter buttons: All, Offense, Defense, Special
3. View filtered results

### Upload Diagram
1. When adding or editing a play
2. Click file input
3. Select PNG, JPG, GIF, or WEBP
4. File auto-displays on play card

### Search Plays (API)
```
GET /plays/api/search?q=pick
→ Returns plays matching "pick"

GET /plays/api/types
→ Returns available play types
```

---

## Database Schema

```sql
TABLE plays (
  id INTEGER PRIMARY KEY,
  name VARCHAR(100) NOT NULL UNIQUE,
  description TEXT,
  play_type VARCHAR(50) DEFAULT 'Offense',
  image_filename VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

---

## Directory Structure

```
web/
├── static/uploads/plays/     ← Play diagram uploads
├── routes/plays.py           ← Routes and logic
└── templates/plays/
    ├── index.html            ← Gallery view
    └── view.html             ← Detail view
```

---

## Troubleshooting

**Plays not showing?**
- Import a game to create plays from game data
- Restart Flask

**Can't upload images?**
- Run: `mkdir -p web/static/uploads/plays`
- Check write permissions

**Sidebar link missing?**
- Restart Flask application
- Clear browser cache

**Database error?**
- Run: `flask init-db`
- Check database is accessible

---

## API Endpoints Reference

| Method | Endpoint | Purpose |
|--------|----------|----------|
| GET | `/plays/` | List all plays |
| GET | `/plays/<id>` | View play details |
| POST | `/plays/add` | Create new play |
| POST | `/plays/<id>/edit` | Update play |
| POST | `/plays/<id>/delete` | Delete play |
| GET | `/plays/api/types` | Get play types |
| GET | `/plays/api/search?q=...` | Search plays |

---

## Sidebar Navigation

The plays module is now integrated into the main sidebar. You'll see:
- **Plays** link with clipboard icon
- Active state when on plays page
- Positioned between Analytics and Glossary

---

## Next Steps

1. **Run setup commands** (see top of this guide)
2. **Visit `/plays`** to see gallery
3. **Try filtering** by play type
4. **Add your own plays** using the modal
5. **Upload diagrams** for each play

---

## Support & Questions

Refer to **PLAYS_SETUP.md** for:
- Detailed setup instructions
- Complete play list reference
- Troubleshooting guide
- Future enhancement ideas
- Integration notes

---

**Status:** Production Ready  
**Last Updated:** January 12, 2026  
**Version:** 1.0
