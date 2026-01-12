# 🏀 Plays-Based Statistics Implementation Summary

**Branch:** `feature/live-game`  
**Date:** January 13, 2026  
**Status:** 📋 Planning Complete - Ready for Implementation  
**Estimated Duration:** 4-6 hours  

---

## Executive Summary

This document outlines the complete implementation of **plays-based shot tracking** for the basketball stats application. Currently, the app tracks aggregate player statistics but lacks individual shot-level data organized by offensive plays.

### What We're Building

```
✅ BEFORE (Current State):
Game Entry → PlayerStat (points, rebounds, assists, etc.) → Box Score PDFs

✅ AFTER (Target State):
Game Entry → PlayerStat + ShotEvent (individual shots) → Box Score PDFs + Plays-Based Analytics
                ↓
            Play Tagging (Pick & Roll, Isolation, etc.)
                ↓
            Play Efficiency Analysis & Player Rankings
```

---

## Key Features

### 1. **Offensive Play Catalog**
- Pick & Roll
- Isolation  
- Spot Up
- Fast Break
- Off-Ball Screen
- High Post
- Drive & Kick
- Transition Three
- Post Up
- Handoff

### 2. **Shot-Level Data Tracking**
Each shot records:
- Player name
- Play type (Pick & Roll, Isolation, etc.)
- Shot type (2PT, 3PT, FT)
- Result (Made/Missed)
- Points scored
- Shot distance
- Shot location
- Shooter position
- Assist player
- Defender
- Quarter & time
- Game margin

### 3. **Analytics Output**
- **Game Report:** All plays used, shot attempts, FG%, PPA (points per attempt)
- **Player Report:** Performance breakdown by play type
- **Team Report:** Player rankings for each play (who scores most from Pick & Roll?)
- **JSON Previews:** For dashboards and real-time data

---

## Implementation Roadmap

### Phase 1: Database Layer (30-45 min)

**Deliverables:**
- `Play` table (offensive play catalog)
- `ShotEvent` table (individual shot attempts)
- Database migration with indexes
- Updated models in `core/models.py`
- Initial play data seed script

**Key Tables:**
```sql
Play(id, name, category, description, is_active, created_at)
ShotEvent(
  id, game_id, player_name, play_id,
  shot_type, result, points, shot_distance,
  shot_location, shooter_position, assist_player, defender,
  quarter, time_in_quarter, game_score_margin,
  created_at, updated_at
)
```

---

### Phase 2: Data Access Layer (1-1.5 hours)

**Deliverable:** `core/plays_stats.py`

**Key Methods:**
```python
PlaysStatsAggregator.get_game_plays_stats(game_id)
→ Returns: plays_used, plays_coverage%, shots_by_play

PlaysStatsAggregator.get_player_plays_stats(player_name, game_id=None)
→ Returns: performance breakdown by play, PPA metrics

PlaysStatsAggregator.get_team_plays_rankings(game_id)
→ Returns: player rankings for each play type
```

**Features:**
- Efficient SQL queries with joins and aggregation
- Handles NULL play_id values gracefully
- Calculates FG%, PPA for each play
- Ranks players by points per play type

---

### Phase 3: PDF Export Layer (1.5-2 hours)

**Deliverable:** `web/routes/pdf_export.py`

**API Endpoints:**
```
GET /api/pdf/game/<game_id>
→ game_plays_{date}_{opponent}.pdf
→ Summary, plays used, shot statistics by play

GET /api/pdf/player/<player_name>?game_id=<id>
→ player_{name}_plays.pdf
→ Performance breakdown by play type with metrics

GET /api/pdf/team/<game_id>
→ team_plays_{date}_{opponent}.pdf (LANDSCAPE)
→ Each play with player rankings

GET /api/pdf/game/<game_id>/preview
→ JSON with plays_used, plays_coverage%, shot details

GET /api/pdf/team/<game_id>/preview
→ JSON with play rankings and player stats
```

**Features:**
- Professional PDF formatting with ReportLab
- Color-coded tables
- Landscape orientation for team report
- Error handling (404, 500)
- Proper file naming

---

### Phase 4: UI Integration (45-60 min)

**Updates Required:**

1. **Game Detail Page** (`web/templates/game_detail.html`)
   - Add shot entry form with play dropdown
   - Display plays used in this game
   - Add "Export Game Plays" button

2. **Player Detail Page** (`web/templates/player_detail.html`)
   - Show player's breakdown by play type
   - Add "Export Player Plays" button

3. **Team Analytics** (new or existing)
   - Show team's plays performance
   - Add "Export Team Plays" button

---

## Database Schema Details

### Play Table
```sql
CREATE TABLE plays (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    category VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Seed data
INSERT INTO plays (name, category, description) VALUES
('Pick & Roll', 'Offensive Set', 'Screen at top of key'),
('Isolation', 'Offensive Set', 'One-on-one post up'),
('Spot Up', 'Offensive Set', 'Catch and shoot three'),
('Fast Break', 'Transition', '3v2 or 2v1 outlet'),
('Off-Ball Screen', 'Offensive Set', 'Screen away from ball'),
('High Post', 'Offensive Set', 'Mid-range from elbow'),
('Drive & Kick', 'Offensive Set', 'Drive dish to shooter'),
('Transition Three', 'Transition', 'Early offensive three'),
('Post Up', 'Offensive Set', 'Low post scoring'),
('Handoff', 'Offensive Set', 'Guard to guard/wing handoff');
```

### ShotEvent Table
```sql
CREATE TABLE shot_events (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    game_id INTEGER NOT NULL,
    player_name VARCHAR(100) NOT NULL,
    play_id INTEGER,
    shot_type VARCHAR(20) NOT NULL,
    result VARCHAR(10) NOT NULL,
    points INTEGER NOT NULL,
    shot_distance DECIMAL(5,2),
    shot_location VARCHAR(50),
    shooter_position VARCHAR(30),
    assist_player VARCHAR(100),
    defender VARCHAR(100),
    quarter INTEGER,
    time_in_quarter VARCHAR(8),
    game_score_margin INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (game_id) REFERENCES games(id),
    FOREIGN KEY (play_id) REFERENCES plays(id)
);

-- Indexes for performance
CREATE INDEX idx_shot_events_game ON shot_events(game_id);
CREATE INDEX idx_shot_events_play ON shot_events(play_id);
CREATE INDEX idx_shot_events_player ON shot_events(player_name);
CREATE INDEX idx_shot_events_result ON shot_events(result);
```

---

## Sample Queries

### Get plays used in a game
```python
plays_stats = db.session.query(
    Play.id, Play.name,
    func.count(ShotEvent.id).label('attempts'),
    func.sum(func.cast(ShotEvent.result == 'Made', db.Integer)).label('made')
).join(
    ShotEvent, Play.id == ShotEvent.play_id
).filter(
    ShotEvent.game_id == 42
).group_by(
    Play.id, Play.name
).all()
```

### Get player performance by play
```python
player_plays = db.session.query(
    Play.name,
    func.count(ShotEvent.id).label('attempts'),
    func.sum(func.cast(ShotEvent.result == 'Made', db.Integer)).label('made')
).join(
    ShotEvent, Play.id == ShotEvent.play_id
).filter(
    ShotEvent.player_name == 'John Smith',
    ShotEvent.game_id == 42
).group_by(
    Play.name
).all()
```

### Get player rankings per play
```python
rankings = db.session.query(
    ShotEvent.player_name,
    func.sum(ShotEvent.points).label('points')
).filter(
    ShotEvent.game_id == 42,
    ShotEvent.play_id == 1  # Pick & Roll
).group_by(
    ShotEvent.player_name
).order_by(
    desc('points')
).all()
```

---

## File Structure

```
basketball-stats/
├── core/
│   ├── models.py                    # UPDATED (add Play, ShotEvent)
│   ├── plays_stats.py               # NEW
│   └── utils.py
│
├── web/
│   ├── routes/
│   │   ├── main.py
│   │   ├── analytics.py
│   │   └── pdf_export.py            # NEW
│   │
│   ├── templates/
│   │   ├── game_detail.html         # UPDATED
│   │   ├── player_detail.html       # UPDATED
│   │   └── ...
│   │
│   └── static/
│       └── ...
│
├── migrations/
│   └── versions/
│       └── add_plays_and_shot_events.py  # NEW
│
├── scripts/
│   └── seed_plays.py                # NEW
│
├── tests/
│   ├── test_plays_stats.py          # NEW
│   └── test_pdf_export.py           # NEW
│
├── app.py                           # UPDATED (register blueprint)
├── requirements.txt                 # UPDATED (add reportlab)
├── IMPLEMENTATION_SUMMARY.md        # THIS FILE
└── ...
```

---

## Deployment Checklist

### Pre-Deployment
- [ ] All code written and reviewed
- [ ] All tests passing (unit + integration)
- [ ] Database migration tested on local DB
- [ ] Plays seeded correctly
- [ ] PDF generation tested with sample data
- [ ] Templates updated and tested
- [ ] No hardcoded paths or credentials
- [ ] Error messages user-friendly
- [ ] Documentation complete

### Deployment Steps
1. Create PR on `feature/live-game` branch
2. Code review and approval
3. Run `flask db upgrade` on staging
4. Run `python scripts/seed_plays.py` on staging
5. Test all endpoints on staging
6. Deploy to production
7. Run migrations on production
8. Monitor error logs

---

## Key Decisions Made

### 1. Why separate ShotEvent table?
- Allows granular shot-level analytics
- Maintains backward compatibility with existing PlayerStat aggregates
- Enables play-based analysis without disrupting current flows

### 2. Why Play table vs strings?
- Consistency (no typos)
- Queryable (GROUP BY efficient)
- Extensible (add categories, descriptions)
- Maintainable (central location)

### 3. Why nullable play_id?
- Some shots may be untagged initially
- Allows gradual migration
- Handles edge cases
- Calculation explicitly handles NULLs

### 4. Why ReportLab?
- Simpler to install (no external deps)
- Reliable table rendering
- Better performance
- Professional output

---

## Next Steps

1. ✅ **Review this plan** - You approved it!
2. 📋 **Implement Phase 1** - Database schema and models
3. 📋 **Implement Phase 2** - PlaysStatsAggregator
4. 📋 **Implement Phase 3** - PDF export routes
5. 📋 **Implement Phase 4** - UI integration
6. 🧪 **Test thoroughly** - Unit, integration, manual
7. 📝 **Document** - Update README, API docs
8. 🚀 **Deploy** - Merge to main and deploy

---

**Status:** 📋 Ready for Phase 1 Implementation  
**Branch:** `feature/live-game`  
**Ready to proceed!** 🎉
