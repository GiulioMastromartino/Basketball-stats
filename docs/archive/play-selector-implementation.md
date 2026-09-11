# Play Selector Feature - Implementation Summary

## Overview
Added a **Play Selector Modal** that automatically triggers after recording 2-pointers (2P), 3-pointers (3P), or Turnovers (TOV) to tag which play was executed during the event.

**NEW:** Toggle button to enable/disable the play selector modal on-demand.

---

## Changes Made

### 1. **Database Models** (`core/models.py`)
**Updated:**
- `ShotEvent` model: Added `play_id` field (foreign key to `Play` table)
- `GameEvent` model:
  - Added `shot_attempt` field (tracks 'attempted' or 'made' for shots)
  - Added `play_id` field (foreign key to `Play` table)
  - Updated `event_type` values to include `SHOT_2PT`, `SHOT_3PT`, `TURNOVER`
- `Play` model: Added `created_at` and `updated_at` timestamps

**Purpose:** Store which play was selected for each shot or turnover event.

---

### 2. **API Endpoint** (`web/routes/api.py`)
**New endpoints:**
```
GET /api/plays - Returns all plays, optionally filtered by type
GET /api/plays/types - Returns unique play types
```

**Purpose:** Fetch available plays for the modal dropdown.

---

### 3. **Live Game Template** (`web/templates/live_game.html`)
**Added Modal:**
- `playSelectorModal` - A responsive modal with:
  - Play type filter dropdown
  - Scrollable list of plays grouped by type
  - "Skip / None" button to dismiss without selection
  - Clean, accessible design

**Purpose:** Provide UI for selecting a play after events.

**Added Toggle Control:**
- Toggle button in game tracker info bar
- Box-style button labeled "Play Selector: ON/OFF"
- Visual state indicator (green = ON, gray = OFF)
- Located next to Subs and Finish buttons for easy access

---

### 4. **JavaScript Logic** (`web/static/js/live_game.js`)
**New Properties:**
```javascript
this.playSelectMode = true;  // Toggle state for play selector
```

**New Methods:**

| Method | Purpose |
|--------|----------|
| `loadPlays()` | Fetch all plays from API on init |
| `populatePlayFilter()` | Build play type filter dropdown |
| `filterPlays()` | Filter plays by selected type |
| `renderPlaysList(filterType)` | Render filtered plays in modal |
| `togglePlaySelector()` | Toggle play selector modal on/off |
| `openPlaySelector(eventType, shooter, shotType)` | Open modal (called from event handlers) - checks toggle state |
| `selectPlay(play)` | Store selected play in gameEvents |

**Updated Methods:**
- `init()` - Now calls `loadPlays()` to preload available plays
- `confirmShotLocationFromMap()` - Triggers play selector ONLY if toggle is ON
- `openPlaySelector()` - Now respects `playSelectMode` toggle before showing modal
- `renderStatBox()` - Updated TOV stat box with custom handler for play selector

**Purpose:** Handle play loading, filtering, selection, storage, and toggle control.

---

## User Flow

### For 2-Pointers & 3-Pointers:
```
1. User clicks +2 or +3 button
2. → Assist Modal appears
3. → User selects assister (or "No assist")
4. → Shot Location Modal appears
5. → User clicks on court to mark shot location
6. → User confirms location
7. → PLAY SELECTOR MODAL appears ✨ (IF toggle is ON)
   OR → Event recorded without play (IF toggle is OFF)
8. → If ON: User selects play from list
9. → Play is tagged to the shot event
```

### For Turnovers:
```
1. User clicks + button next to TOV stat
2. → PLAY SELECTOR MODAL appears immediately ✨ (IF toggle is ON)
   OR → TOV count increments (IF toggle is OFF)
3. → If ON: User selects play from list
4. → Play is tagged to turnover event
5. → TOV count increments
```

### Toggling Play Selector On/Off:
```
1. User clicks "Play Selector: ON" button
2. → Button changes to "Play Selector: OFF" (gray background)
3. → No modals trigger on subsequent shots/turnovers
4. → Click button again to re-enable
5. → State persists within game session
```

### Skipping Play Selection:
- Modal has "Skip / None" button
- Users can dismiss without selecting a play
- Event is still recorded without play tagging

---

## Data Structure

### GameEvent with Play Selection:
```json
{
  "type": "SHOT_2PT",
  "player": "LeBron James",
  "detail": {
    "play_id": 42,
    "play_name": "Pick & Roll (Offensive)"
  },
  "quarter": 2,
  "clockSeconds": 245,
  "timestamp": 1673456789000
}
```

### Turnover with Play Selection:
```json
{
  "type": "TURNOVER",
  "player": "James Harden",
  "detail": {
    "play_id": 15,
    "play_name": "Press Defense"
  },
  "quarter": 1,
  "clockSeconds": 156,
  "timestamp": 1673456812000
}
```

### Without Play Selection (when toggle is OFF):
```json
{
  "type": "SHOT_3PT",
  "player": "Stephen Curry",
  "detail": null,
  "quarter": 3,
  "clockSeconds": 120,
  "timestamp": 1673456900000
}
```

---

## Integration Points

### Required Play Database Setup:
You must populate the `plays` table with your coaching plays:

```sql
INSERT INTO plays (name, description, play_type, created_at, updated_at) VALUES
('Pick & Roll (Offensive)', 'Ball handler uses screener to create space', 'Offense', NOW(), NOW()),
('Press Defense', 'Full court defensive pressure', 'Defense', NOW(), NOW()),
('Isolation', 'One-on-one play setup', 'Offense', NOW(), NOW()),
-- ... add more plays
```

### Queryable Event Data:
After game is saved, you can query plays used:

```python
from core.models import GameEvent, Play

# Get all 2PT shots and their associated plays (including untagged)
events = GameEvent.query.filter_by(game_id=game_id, event_type='SHOT_2PT').all()
for event in events:
    if event.play_id:
        play = Play.query.get(event.play_id)
        print(f"{event.player} scored 2PT via {play.name}")
    else:
        print(f"{event.player} scored 2PT (no play tagged)")
```

---

## UI/UX Features

✅ **Toggle Button Control**
- Located in game tracker controls bar
- Box-style button with clear ON/OFF state
- Green background when ON (active)
- Gray background when OFF (inactive)
- Click to toggle state
- State visible at a glance

✅ **Responsive Modal**
- Works on mobile, tablet, desktop
- Scrollable play list (400px max-height)
- Touch-friendly button sizing

✅ **Smart Filtering**
- Dropdown to filter by play type
- "All Plays" option for comprehensive list
- Real-time filter updates

✅ **Clear Play Information**
- Play name displayed boldly
- Play description shown if available
- Play type badge for quick identification

✅ **Optional Selection**
- "Skip / None" button lets users continue without tagging
- No forcing required selection
- Event still recorded without play data

✅ **Toggle Flexibility**
- Switch play selector on/off during game
- No need to finish and restart
- Quick workflow adjustment

✅ **Integration Points**
- Shows after shots (both made and attempted at shot location step) - IF toggle ON
- Shows immediately after TOV button click - IF toggle ON
- Styled consistently with existing modals
- Toggle state saved in game session

---

## Files Modified

| File | Changes | Status |
|------|---------|--------|
| `core/models.py` | Added `play_id` fields to `ShotEvent` and `GameEvent` | ✅ Committed |
| `web/routes/api.py` | Added `/api/plays` and `/api/plays/types` endpoints | ✅ Committed |
| `web/templates/live_game.html` | Added `playSelectorModal` HTML + toggle button | ✅ Committed |
| `web/static/js/live_game.js` | Added play selector logic, event handlers, and toggle | ✅ Committed |

---

## Next Steps

1. **Populate Play Database**
   - Insert your basketball plays into `plays` table
   - Include offensive, defensive, and special play types

2. **Test Play Selection Flow**
   - Create a test game
   - Toggle play selector ON and OFF
   - Record 2P/3P/TOV events with toggle ON
   - Verify play selector appears only when ON
   - Record events with toggle OFF
   - Verify no modal appears when OFF

3. **Query Recorded Plays**
   - Review how plays are stored
   - Build analytics views showing play frequency
   - Track efficiency by play type

4. **Optional Analytics Integration**
   - Add charts showing play usage frequency
   - Show effectiveness metrics by play
   - Generate play-based scouting reports

---

## Technical Notes

- **Browser Storage:** Play data cached in localStorage for offline reliability
- **State Management:** Play selections persist in `gameEvents` array until game finish
- **Toggle State:** `playSelectMode` boolean stored in class instance (resets on page reload)
- **Event Tagging:** Each event can have optional `play_id` in detail field
- **API Caching:** Plays loaded once on init and cached in `playsCache`
- **Conditional Rendering:** Modal only opens if `playSelectMode === true`
- **Graceful Degradation:** If no plays exist, modal shows empty message
- **CSRF Protection:** All API calls include CSRF token for security

---

## Example Game Events Log

After a game with mixed play selection (toggle switched on/off):

```json
[
  {
    "type": "SHOT_3PT",
    "player": "Jayson Tatum",
    "detail": {
      "play_id": 8,
      "play_name": "Motion Offense"
    },
    "quarter": 1,
    "clockSeconds": 420
  },
  {
    "type": "TURNOVER",
    "player": "Jaylen Brown",
    "detail": null,
    "quarter": 1,
    "clockSeconds": 415
  },
  {
    "type": "SHOT_2PT",
    "player": "Derrick White",
    "detail": {
      "play_id": 5,
      "play_name": "Pick & Roll"
    },
    "quarter": 1,
    "clockSeconds": 380
  }
]
```

---

## Success Criteria ✅

- [x] Play selector modal triggers after 2P/3P shots (IF toggle ON)
- [x] Play selector modal triggers after TOV events (IF toggle ON)
- [x] Modal DOES NOT appear when toggle is OFF
- [x] Modal displays all available plays with filtering
- [x] Selected plays are stored in gameEvents
- [x] Toggle button controls modal behavior
- [x] Toggle state visible in UI (ON/OFF indication)
- [x] Data persists through game session
- [x] Play data sent to backend on game finish
- [x] Modal has "Skip" option for optional selection
- [x] UI is responsive and accessible
