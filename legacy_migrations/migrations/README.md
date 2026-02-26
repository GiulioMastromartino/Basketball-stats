# Database Migrations

## Overview
This directory contains SQL migration files to evolve the Basketball Stats database schema.

---

## Migration Files

### `001_add_play_selector_feature.sql`
**Purpose:** Adds play tracking functionality to shots and turnovers.

**Changes:**
- Creates `plays` table with columns: `id`, `name`, `description`, `play_type`, `image_filename`, `created_at`, `updated_at`
- Adds `play_id` foreign key to `shot_events` table
- Adds `shot_attempt` and `play_id` columns to `game_events` table
- Creates performance indexes on play-related columns
- Seeds 20 sample plays (Offense, Defense, Special)

**Status:** ✅ Ready to apply

---

### `add_indexes.sql`
**Purpose:** Performance optimization indexes.

**Changes:**
- Indexes on `player_stats` (player_name, game_id, minutes)
- Indexes on `games` (sort_date, game_type, opponent, result)
- Composite indexes for common query patterns

**Status:** ✅ Already applied

---

## How to Apply Migrations

### SQLite (Development/Production)

#### Method 1: Using SQLite CLI
```bash
# Navigate to project root
cd /path/to/Basketball-stats

# Apply migration
sqlite3 instance/basketball.db < migrations/001_add_play_selector_feature.sql

# Verify
sqlite3 instance/basketball.db "SELECT COUNT(*) FROM plays;"
```

#### Method 2: Using Python
```python
import sqlite3

# Connect to database
conn = sqlite3.connect('instance/basketball.db')
cursor = conn.cursor()

# Read and execute migration
with open('migrations/001_add_play_selector_feature.sql', 'r') as f:
    migration_sql = f.read()
    cursor.executescript(migration_sql)

conn.commit()
conn.close()
print("Migration applied successfully!")
```

#### Method 3: Flask Shell
```python
flask shell

>>> from core.models import db
>>> with open('migrations/001_add_play_selector_feature.sql', 'r') as f:
...     db.session.execute(f.read())
>>> db.session.commit()
>>> print("Migration complete!")
```

---

## Verification Queries

After applying migration `001_add_play_selector_feature.sql`, run these checks:

```sql
-- Check if plays table exists and has data
SELECT COUNT(*) as total_plays FROM plays;
-- Expected: 20

-- Check play types distribution
SELECT play_type, COUNT(*) as count 
FROM plays 
GROUP BY play_type;
-- Expected: Offense (10), Defense (6), Special (4)

-- Verify shot_events has play_id column
SELECT sql FROM sqlite_master 
WHERE type='table' AND name='shot_events';
-- Should include: play_id INTEGER

-- Verify game_events has new columns
SELECT sql FROM sqlite_master 
WHERE type='table' AND name='game_events';
-- Should include: shot_attempt VARCHAR(10), play_id INTEGER

-- Check indexes were created
SELECT name FROM sqlite_master 
WHERE type='index' 
AND name LIKE '%play%';
-- Expected: idx_shot_events_play_id, idx_game_events_play_id, idx_plays_type
```

---

## Sample Plays Included

### Offense (10 plays)
- Pick & Roll (Offensive)
- Isolation
- Post-Up
- Fast Break
- Screen Away
- Hand-Off
- Backdoor Cut
- Drive & Kick
- High-Low
- Motion Offense

### Defense (6 plays)
- Zone Defense
- Man-to-Man Defense
- Press Defense
- Trap Defense
- Help Defense
- Transition Defense

### Special (4 plays)
- Inbound Play
- Last Shot
- Out of Timeout
- Free Play

---

## Adding Custom Plays

After migration, add your team's custom plays:

```sql
INSERT INTO plays (name, description, play_type) VALUES
('Horns Set', 'Two players at elbows, ball handler at top', 'Offense'),
('Box-1 Defense', 'Box zone with one chaser', 'Defense'),
('Sideline Out', 'Sideline inbound play', 'Special');
```

---

## Rollback (If Needed)

**⚠️ Warning:** Rolling back will delete all play data.

```sql
-- Drop added columns (SQLite requires table recreation)
-- Backup first!
.backup backup.db

-- Drop tables
DROP TABLE IF EXISTS plays;

-- Recreate shot_events and game_events without play columns
-- (Not recommended - better to keep schema and clear data)
```

---

## Troubleshooting

### "table plays already exists"
✅ **Solution:** Migration is idempotent. This is expected if already applied.

### "duplicate column name: play_id"
✅ **Solution:** Columns already exist. Migration is partially applied.

### "FOREIGN KEY constraint failed"
❌ **Solution:** Ensure `plays` table exists before inserting shot/game events with play_id.

### "no such table: plays"
❌ **Solution:** Run migration `001_add_play_selector_feature.sql` first.

---

## Migration Checklist

- [ ] Backup database before migration
- [ ] Apply `001_add_play_selector_feature.sql`
- [ ] Verify plays table has 20 records
- [ ] Verify indexes created successfully
- [ ] Test play selector in live game UI
- [ ] Record a test game with play tags
- [ ] Query `shot_events` and `game_events` to verify play_id storage

---

## Next Steps After Migration

1. **Start Application**
   ```bash
   flask run
   ```

2. **Test Play Selector**
   - Navigate to `/live-game`
   - Start a new game
   - Record 2PT, 3PT, or TOV
   - Verify play selector modal appears
   - Select a play and confirm it's saved

3. **Verify Data Persistence**
   ```sql
   SELECT se.player_name, se.shot_type, p.name as play_name
   FROM shot_events se
   LEFT JOIN plays p ON se.play_id = p.id
   WHERE se.play_id IS NOT NULL;
   ```

4. **Customize Plays**
   - Add your team's playbook to `plays` table
   - Optionally upload play diagrams to `uploads/plays/`
   - Set `image_filename` for visual references

---

## Support

For issues or questions:
- Check logs: `tail -f logs/app.log`
- Review commit history: `git log migrations/`
- Open GitHub issue with `[MIGRATION]` tag