# Live Game Tracking

Track basketball games in real-time with shot locations, player substitutions, play tagging, and automatic stat calculations.

> **Current console: `/live-v2`.** The tablet-first v2 console is the game-day default (score strip, roster rails, tap-to-log half-court, action pad, 50-step undo, per-event sync with offline queue, **HT SHARE** one-tap halftime button). The legacy **Live Game** page (`/live-game`, `POST /live-game/save`) is still available and documented below for reference.

---

## Overview

Both consoles provide:

- **Shot Clock & Quarter Timer** — Keep track of game time
- **Player Substitutions** — Manage who's on the court
- **Shot Charting** — Record makes and misses on a court diagram
- **Play Tagging** — Associate shots with plays from your playbook
- **+/- Tracking** — Real-time plus/minus for each player
- **Halftime Summary** — Generate PDF reports at halftime
- **Auto-Save** — Game state cached in localStorage for crash recovery

---

## Starting a Live Game (v2 console)

### 1. Access the console

Click **Live V2** in the sidebar (`GET /live-v2`). The interface opens in fullscreen mode optimized for tablets.

### 2. Set Up Players

Before tracking, ensure your roster is set up:

- Players are pre-loaded from your team roster
- Use the substitution panel to set the starting five
- Bench players appear in a separate list

### 3. Start the Game

Click **Start Game** to begin tracking. The shot clock and quarter timer start automatically.

---

## Tracking Actions

### Recording Shots

<div class="step-card">
  <div class="step-number">1</div>
  <div class="step-content">
    <h4>Select the shooter</h4>
    <p>Tap the player who took the shot from the active player list.</p>
  </div>
</div>

<div class="step-card">
  <div class="step-number">2</div>
  <div class="step-content">
    <h4>Mark the location</h4>
    <p>Tap the court diagram where the shot was taken. The system records x/y coordinates automatically.</p>
  </div>
</div>

<div class="step-card">
  <div class="step-number">3</div>
  <div class="step-content">
    <h4>Choose result & play</h4>
    <p>Select <strong>Make</strong> or <strong>Miss</strong>, optionally tag the play from your playbook, and confirm.</p>
  </div>
</div>

### Substitutions

- Tap **Sub** next to any active player
- Select the substitute from the bench
- The system tracks minutes played automatically

### Fouls & Turnovers

Use the action buttons to record:
- **Foul** — Player commits a foul
- **Turnover** — Player turns over the ball
- **Timeout** — Log a timeout

---

## Shot Charting

Shots are plotted on a half-court SVG diagram:

| Color | Meaning |
|-------|---------|
| 🟢 Green | Made shot |
| 🔴 Red | Missed shot |
| Size | 2PT vs 3PT (3PT markers are larger) |

The system automatically calculates:
- Field goal percentage by zone
- Heatmap of shot concentration
- Points per shot by court area

---

## Player +/- Tracking

Each player's plus/minus updates in real-time:

- **+1** when your team scores while they're on court
- **-1** when the opponent scores while they're on court
- Running totals displayed in the player panel

---

## Halftime & Game End

### Halftime Summary

At halftime, click **Halftime PDF** to generate a printable report with:
- First-half box score
- Shooting percentages
- Player +/- summary
- Possession breakdown

### Tablet Console v2 (`/live-v2`) — current

The game-day console is a tablet-first layout: top score strip (score, period/clock, fouls,
timeouts, possession), roster rails with foul dots, a tap-to-log
half-court, and an action pad (ASSIST, REBOUND, BLOCK, FTs, FOUL, TECH,
TOV, STEAL, TIME OUT, SUBS) with 50-step undo. Every entry syncs
per-event to `POST /api/live-v2/events` (idempotent, with resync + shot-precise undo) through
an offline-tolerant local queue, scoped per user/team/day.

At halftime, tap **✉ HT SHARE** in the action pad: it posts the current
console state to `POST /reports/live/halftime-share`, which texts the
staff WhatsApp group (when one is configured for the team) and can carry
the rendered halftime PDF as an attachment. With no group configured the
message is shown for manual copy — the page never breaks on failure.

### End Game

When the game ends, click **End Game** to:
1. Review the final stats
2. Tag any remaining plays
3. Save the game to the database
4. Generate the final PDF report

The game is then available in the **Games** list with full detail.

---

## Auto-Save & Crash Recovery

- **v2 console**: every event syncs to `POST /api/live-v2/events`; an offline-tolerant local queue holds unsynced events per user/team/day, so a dropped connection or closed tab resyncs on return (plus shot-precise undo).
- **Legacy page** (`/live-game`): game state is saved to `localStorage` every 30 seconds. If the page is accidentally closed:

1. Navigate to **Live Game** again
2. A "Recover Game" prompt appears
3. Click **Recover** to restore the last saved state

---

## Tips

- **Use a tablet** for the best experience during games
- **Pre-load your playbook** — tagged plays give you post-game effectiveness analysis
- **Set lineups before the game** to save time during tracking
- **Check the +/- panel** at halftime for substitution insights

---

## Related

- [Plays Management](plays.md) — Set up your playbook before tracking
- [Analytics & Reports](advanced-analytics.md) — Advanced game analysis
- [PDF Exports](pdf-exports.md) — Generate reports from tracked games
