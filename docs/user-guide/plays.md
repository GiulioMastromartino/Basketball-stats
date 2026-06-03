# Plays Management

The Plays module lets you manage your team's digital playbook and associate plays with game events for post-game effectiveness analysis.

---

## Overview

The system comes pre-loaded with **65+ plays** covering standard offensive, defensive, and special situations:

| Category | Count | Examples |
|----------|-------|----------|
| **Offense** | 20+ | Pick & Roll, Spain PNR, Horns Twist, UCLA Cut, Triangle |
| **Defense** | 20+ | Man-to-Man, 2-3 Zone, 1-3-1 Zone, Box-and-One, Presses |
| **Special** | 25+ | BLOB, SLOB, ATO, Game Winner, Quick Clock |

---

## Viewing the Playbook

1. Click **Plays** in the sidebar navigation
2. Use the filter buttons (All, Offense, Defense, Special) to narrow the view
3. Click any play card to view full details and diagram

Play cards display:
- Play name and description
- Type badge (Offense/Defense/Special)
- Difficulty rating
- Tagged effectiveness (if used in games)

---

## Adding a New Play

### Via Web Form

1. On the Plays page, click **Add New Play**
2. **Name** — Enter a unique name for the play
3. **Type** — Select the category (Offense/Defense/Special)
4. **Description** — Detailed explanation of execution
5. **Diagram** — Upload an image (PNG, JPG) of the play diagram

### Via Play Builder (Canvas)

1. Click **Play Builder** to open the full-screen drawing canvas
2. Use the toolbar to create your play diagram:
    - **Player Tokens** — Drag player markers onto the court
    - **Arrows** — Draw movement paths (pass, cut, dribble, screen, shot, handoff)
    - **Shapes** — Add cones, boxes, and zone markers
    - **Text** — Label positions and actions
3. Build **animation sequences** to show movement over time
4. Save — the play is added to your playbook

---

## Play Builder Tools

The Play Builder is a Fabric.js-powered canvas with these tools:

| Tool | Icon | Purpose |
|------|------|---------|
| **Select** | ↖️ | Move, resize, and edit elements |
| **Player** | ⭕ | Add player tokens (numbered 1–5) |
| **Pass** | ➡️ | Draw pass lines (dashed) |
| **Cut** | ➡️ | Draw cut movement (solid) |
| **Dribble** | 〰️ | Draw dribble path (zigzag) |
| **Screen** | 🛡️ | Draw screen position |
| **Shot** | 🎯 | Mark shot location |
| **Handoff** | ↔️ | Draw handoff action |
| **Shape** | ⬜ | Add cones, boxes, zones |
| **Text** | T | Add labels and annotations |

**Animations**: Use the timeline at the bottom to create frame-by-frame sequences showing how the play develops over time. Each frame saves the position of all elements.

---

## Editing & Deleting

### Edit

Update descriptions, diagrams, or canvas data as your playbook evolves:

1. Navigate to the play detail page
2. Click **Edit** to modify metadata or **Edit in Builder** to update the canvas diagram

### Delete

Remove plays that are no longer used:

!!! warning "Historical Data"
    Deleting a play may affect historical stats if that play was tagged in past games. Associated shot events will lose their play reference.

---

## Using Plays in Games

### Tagging During Live Tracking

When recording a shot during live game tracking:

1. After marking the shot location, the play selector appears
2. Choose the associated play from your playbook
3. The system links the shot event to the play for analysis

### Post-Game Analysis

After tagging plays in games, the system tracks:

| Metric | Description |
|--------|-------------|
| **Frequency** | How often a play is run (total attempts) |
| **Efficiency** | Points Per Possession (PPP) for each play |
| **FG%** | Field goal percentage when running the play |
| **Shot Distribution** | Where shots come from when running the play |

### Play Rankings

The analytics dashboard ranks plays by effectiveness:

```
Plays → Advanced Analytics → Plays Rankings
```

This shows which plays yield the highest points per possession against specific opponents or in specific situations.

---

## Pre-loaded Plays Reference

### Offensive Plays

- Pick & Roll (Ball Screen)
- Spain Pick & Roll
- Horns (Double High Ball Screen)
- Horns Twist
- UCLA Cut
- Flex Offense
- Motion Strong
- Motion Weak
- Princeton Offense
- Triangle Offense
- Dribble Drive Motion
- Spread Pick & Roll
- Isolation
- Post Up
- Backdoor Cut
- Staggered Screen
- Pin Down
- Floppy
- Elevator Doors
- Zoom Action

### Defensive Plays

- Man-to-Man
- 2-3 Zone
- 3-2 Zone
- 1-3-1 Zone
- Box-and-One
- Diamond-and-One
- Amoeba Defense
- Full Court Man Press
- 2-2-1 Press
- 1-2-1-1 Press
- 3/4 Court Trap
- Half Court Trap
- Switching Defense
- Hedging Defense
- Ice Defense
- Show Defense
- Drop Coverage
- Blitz

### Special Plays

- BLOB — Baseline Out of Bounds (various sets)
- SLOB — Sideline Out of Bounds (various sets)
- ATO — After Timeout plays
- Game Winner / Final Shot
- Quick Hitters
- End of Quarter
- Jump Ball Sets
- Free Throw Rebound Sets

---

## Related

- [Live Game Tracking](live-game.md) — Tag plays during live games
- [Analytics & Reports](advanced-analytics.md) — Analyze play effectiveness
- [PDF Exports](pdf-exports.md) — Generate play-focused PDF reports
