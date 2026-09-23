/**
 * Live Game v2 console (slice: roster rails + court tap + action pad + log + undo).
 *
 * Backend contract notes (mirrors legacy web/static/js/live_game.js):
 * - Legacy persists via bulk POST /live-game/save (full game JSON: schema_version,
 *   shot_locations, game_events, player_stats) on finish, GET /api/plays for the
 *   play selector, and POST /reports/live/halftime-pdf for exports. There is NO
 *   per-shot/per-event POST endpoint in legacy, so v2 records every action to the
 *   DOM game log + localStorage autosave queue and marks rows "pending" until a
 *   per-event endpoint lands.
 * - TODO(v2-backend): add POST /api/live-v2/events (single GameEvent/ShotEvent row)
 *   and flip syncEvent() below from queue-only to real POST with the same
 *   CSRF (X-CSRFToken) + JSON pattern legacy uses. Never break the page if the
 *   endpoint is missing — keep DOM + localStorage as source of truth.
 *   (DONE: syncEvent() POSTs to /api/live-v2/events; rows without a live
 *   game context in window.V2_BOOTSTRAP stay queued locally as before.)
 */
(function () {
  "use strict";

  var STORAGE_BASE = "live_game_v2_state";
  var MAX_STACK = 50; // undo depth persisted; in-memory requirement is >= 20
  var COURT_W = 500;
  var COURT_H = 470;
  var HOOP = { x: 250, y: 55 };
  var THREE_RADIUS = 220; // matches the SVG arc (A 220,220)

  var state = {
    period: 1,
    clock: "10:00",
    home: [], // {id,name,num,team,fouls,onCourt}
    away: [],
    selectedId: null,
    pendingShot: null, // {x,y,zone,points}
    log: [], // {id,team,num,name,action,period,clock,synced,undone,scoreDelta,foulDelta,subA,subB,ts}
    stack: [], // ids of undoable log entries (persisted, capped at MAX_STACK)
    seq: 0,
    hadRestore: false, // true when a persisted session was loaded from localStorage
  };

  function getEl(id) {
    return document.getElementById(id);
  }

  // ---------- persistence (scoped to user + team + session) ----------
  // The storage key and every snapshot carry the bootstrap identity
  // (userId/teamId/sessionId from /live-v2). A different login, team, or day
  // never restores another session's roster/score/log.
  function bootIds() {
    var boot = window.V2_BOOTSTRAP || {};
    return {
      userId: boot.userId === undefined ? null : boot.userId,
      teamId: boot.teamId === undefined ? null : boot.teamId,
      sessionId: boot.sessionId === undefined ? null : boot.sessionId,
    };
  }

  function storageKey() {
    var ids = bootIds();
    return STORAGE_BASE + ":" + ids.userId + ":" + ids.teamId;
  }

  function persist() {
    var ids = bootIds();
    try {
      localStorage.setItem(
        storageKey(),
        JSON.stringify({
          userId: ids.userId,
          teamId: ids.teamId,
          sessionId: ids.sessionId,
          home: state.home,
          away: state.away,
          selectedId: state.selectedId,
          log: state.log,
          stack: state.stack.slice(-MAX_STACK),
          seq: state.seq,
          period: state.period,
          clock: state.clock,
          scoreA: getEl("v2-team-a-score") ? getEl("v2-team-a-score").textContent : "0",
          scoreB: getEl("v2-team-b-score") ? getEl("v2-team-b-score").textContent : "0",
          foulsA: getEl("v2-team-a-fouls") ? getEl("v2-team-a-fouls").textContent : "0",
          foulsB: getEl("v2-team-b-fouls") ? getEl("v2-team-b-fouls").textContent : "0",
        })
      );
    } catch (e) {
      /* storage full/blocked — page still works */
    }
  }

  function restore() {
    var raw = null;
    try {
      // Drop pre-identity snapshots stored under the legacy unscoped key.
      localStorage.removeItem(STORAGE_BASE);
      raw = localStorage.getItem(storageKey());
    } catch (e) {
      return;
    }
    if (!raw) {
      return;
    }
    try {
      var s = JSON.parse(raw);
      // Reject snapshots from another user/team/session (or legacy
      // snapshots without identity) — start fresh instead of leaking
      // the previous session's roster, score, and log.
      var ids = bootIds();
      if (
        s.userId === undefined ||
        s.teamId === undefined ||
        s.sessionId === undefined ||
        s.userId !== ids.userId ||
        s.teamId !== ids.teamId ||
        s.sessionId !== ids.sessionId
      ) {
        try {
          localStorage.removeItem(storageKey());
        } catch (e2) {
          /* ignore */
        }
        return;
      }
      state.hadRestore = true;
      if (Array.isArray(s.home)) {
        state.home = s.home;
      }
      if (Array.isArray(s.away)) {
        state.away = s.away;
      }
      state.selectedId = s.selectedId || null;
      state.log = Array.isArray(s.log) ? s.log : [];
      state.stack = Array.isArray(s.stack) ? s.stack.slice(-MAX_STACK) : [];
      state.seq = s.seq || state.log.length;
      if (s.period) {
        state.period = s.period;
      }
      if (s.clock) {
        state.clock = s.clock;
      }
      if (s.scoreA && getEl("v2-team-a-score")) {
        getEl("v2-team-a-score").textContent = s.scoreA;
      }
      if (s.scoreB && getEl("v2-team-b-score")) {
        getEl("v2-team-b-score").textContent = s.scoreB;
      }
      if (s.foulsA && getEl("v2-team-a-fouls")) {
        getEl("v2-team-a-fouls").textContent = s.foulsA;
      }
      if (s.foulsB && getEl("v2-team-b-fouls")) {
        getEl("v2-team-b-fouls").textContent = s.foulsB;
      }
    } catch (e) {
      /* corrupt cache — start fresh */
    }
  }

  // ---------- roster ----------
  function parseNumber(name, fallback) {
    var m = /^#?\s*(\d{1,2})\b/.exec(String(name || "").trim());
    if (m) {
      return parseInt(m[1], 10);
    }
    return fallback;
  }

  function cleanName(name) {
    return String(name || "")
      .replace(/^#?\s*\d{1,2}\s*[-–—.]?\s*/, "")
      .trim() || String(name || "Player");
  }

  function buildRosters() {
    var boot = window.V2_BOOTSTRAP || {};
    var names = Array.isArray(boot.homePlayers) ? boot.homePlayers : [];
    if (state.home.length || state.away.length) {
      // Restored from localStorage: merge any bootstrap names added to the
      // roster since the snapshot (same-day roster edits keep the same
      // sessionId, so without a merge new players stay invisible).
      var seen = {};
      state.home.forEach(function (p) {
        if (p && p.name) {
          seen[cleanName(p.name).toLowerCase()] = true;
        }
      });
      var nextId = state.home.length;
      names.forEach(function (raw) {
        var nm = typeof raw === "string" ? raw : raw.name || "";
        var key = cleanName(nm).toLowerCase();
        if (!key || seen[key]) {
          return;
        }
        seen[key] = true;
        state.home.push({
          id: "h" + nextId + "_" + key.replace(/[^a-z0-9]+/g, "-"),
          name: cleanName(nm),
          num: parseNumber(nm, nextId + 1),
          team: "HOME",
          fouls: 0,
          onCourt: false,
        });
        nextId += 1;
      });
      if (!state.away.length) {
        state.away = [0, 1, 2, 3, 4].map(function (i) {
          return { id: "a" + i, name: "Opp " + (i + 1), num: i + 1, team: "AWAY", fouls: 0, onCourt: true };
        });
      }
      return;
    }
    state.home = names.map(function (raw, i) {
      var nm = typeof raw === "string" ? raw : raw.name || "Player " + (i + 1);
      return {
        id: "h" + i,
        name: cleanName(nm),
        num: parseNumber(nm, i + 1),
        team: "HOME",
        // TODO(v2-backend): per-player fouls not in /live-v2 context yet; default 0.
        fouls: 0,
        onCourt: i < 5,
      };
    });
    // Route passes no away roster; use 5 opponent placeholders so the away rail,
    // court tap (as opponent), and sub sheet all work. TODO(v2-backend): pass
    // real opponent roster in /live-v2 context.
    state.away = [0, 1, 2, 3, 4].map(function (i) {
      return { id: "a" + i, name: "Opp " + (i + 1), num: i + 1, team: "AWAY", fouls: 0, onCourt: true };
    });
  }

  function findPlayer(id) {
    var all = state.home.concat(state.away);
    for (var i = 0; i < all.length; i++) {
      if (all[i].id === id) {
        return all[i];
      }
    }
    return null;
  }

  function renderRoster(containerId, players) {
    var box = getEl(containerId);
    if (!box) {
      return;
    }
    box.innerHTML = "";
    if (!players.length) {
      var d = document.createElement("div");
      d.className = "v2-stub";
      d.textContent = "No players — TODO(v2): empty roster state.";
      box.appendChild(d);
      return;
    }
    // On-court first, then bench, each sorted by number.
    var sorted = players.slice().sort(function (a, b) {
      if (a.onCourt !== b.onCourt) {
        return a.onCourt ? -1 : 1;
      }
      return a.num - b.num;
    });
    sorted.forEach(function (p) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className =
        "v2-player " + (p.onCourt ? "v2-oncourt" : "v2-bench") + (p.id === state.selectedId ? " v2-selected" : "");
      btn.dataset.playerId = p.id;
      btn.setAttribute("aria-pressed", p.id === state.selectedId ? "true" : "false");
      // Foul dots: text badge (•) — context has no per-player foul counts yet.
      var dots = "";
      for (var f = 0; f < 5; f++) {
        dots += f < p.fouls ? "●" : "○";
      }
      var num = document.createElement("span");
      num.className = "v2-num";
      num.textContent = p.num;
      var mid = document.createElement("span");
      mid.className = "v2-pname";
      mid.textContent = p.name;
      var meta = document.createElement("span");
      meta.className = "v2-fouls";
      meta.textContent = dots;
      meta.title = p.fouls + " fouls";
      var st = document.createElement("span");
      st.className = "v2-state";
      st.textContent = p.onCourt ? "on" : "bench";
      btn.appendChild(num);
      btn.appendChild(mid);
      btn.appendChild(meta);
      btn.appendChild(st);
      btn.addEventListener("click", function () {
        selectPlayer(p.id);
      });
      box.appendChild(btn);
    });
  }

  function renderRosters() {
    renderRoster("v2-roster-home", state.home);
    renderRoster("v2-roster-away", state.away);
    renderSelectedDisplay();
  }

  function renderSelectedDisplay() {
    var el = getEl("v2-selected-display");
    if (!el) {
      return;
    }
    var p = state.selectedId ? findPlayer(state.selectedId) : null;
    el.textContent = p ? "Selected: #" + p.num + " " + p.name + " (" + p.team + ")" : "No player selected";
  }

  function selectPlayer(id) {
    state.selectedId = state.selectedId === id ? null : id;
    var hint = getEl("v2-need-player");
    if (hint) {
      hint.textContent = "";
    }
    renderRosters();
    persist();
    return state.selectedId ? findPlayer(state.selectedId) : null;
  }

  function requireSelection() {
    var p = state.selectedId ? findPlayer(state.selectedId) : null;
    var hint = getEl("v2-need-player");
    if (!p && hint) {
      hint.textContent = "Select a player first — tap a roster card.";
    } else if (hint) {
      hint.textContent = "";
    }
    return p;
  }

  // ---------- game log ----------
  function currentClock() {
    var el = getEl("v2-clock");
    if (el && el.textContent.trim()) {
      state.clock = el.textContent.trim();
    }
    return state.clock;
  }

  function appendLogRow(entry) {
    var log = getEl("v2-game-log");
    if (!log) {
      return;
    }
    var row = document.createElement("div");
    row.className = "v2-log-row" + (entry.undone ? " v2-undone" : "");
    row.dataset.entryId = String(entry.id);
    var main = document.createElement("span");
    main.textContent =
      entry.team + " · #" + entry.num + " " + entry.name + " · " + entry.action + " · P" + entry.period + " · " + entry.clock;
    var sync = document.createElement("span");
    sync.className = entry.synced ? "v2-sync-ok" : "v2-sync-pending";
    sync.textContent = entry.synced ? "✓" : "pending";
    sync.title = entry.synced ? "synced" : "pending sync";
    row.appendChild(main);
    row.appendChild(sync);
    log.appendChild(row);
    log.scrollTop = log.scrollHeight;
  }

  function rerenderLog() {
    var log = getEl("v2-game-log");
    if (!log) {
      return;
    }
    log.innerHTML = "";
    state.log.forEach(appendLogRow);
  }

  function appendBanner(text) {
    var log = getEl("v2-game-log");
    if (!log) {
      return;
    }
    var p = document.createElement("p");
    p.className = "v2-log-banner";
    p.textContent = text;
    log.appendChild(p);
    log.scrollTop = log.scrollHeight;
  }

  // ---------- sync (POST each queued event to /api/live-v2/events) ----------
  function getGameId() {
    try {
      var boot = window.V2_BOOTSTRAP || {};
      var gid = boot.gameId != null ? boot.gameId : boot.game_id;
      if (gid == null || gid === "") {
        return null;
      }
      var n = parseInt(gid, 10);
      return isNaN(n) ? null : n;
    } catch (e) {
      return null;
    }
  }

  function getCsrfToken() {
    try {
      var meta = document.querySelector('meta[name="csrf-token"]');
      if (meta && meta.content) {
        return meta.content;
      }
      var hidden = document.getElementById("csrf_token");
      if (hidden && hidden.value) {
        return hidden.value;
      }
    } catch (e) {
      /* no token available — server may still accept (e.g. tests) */
    }
    return "";
  }

  function shotPoints(action) {
    var m = /(\d)\s*PT/.exec(String(action || ""));
    return m ? parseInt(m[1], 10) : null;
  }

  function markRowSynced(entryId) {
    try {
      var badge = document.querySelector(
        '.v2-log-row[data-entry-id="' + entryId + '"] .v2-sync-pending'
      );
      if (badge) {
        badge.className = "v2-sync-ok";
        badge.textContent = "✓";
        badge.title = "synced";
      }
    } catch (e) {
      /* never break the page */
    }
  }

  function postEntry(entry) {
    var gameId = getGameId();
    if (gameId == null || !window.fetch) {
      return; // no live game context yet — stay queued locally
    }
    if (!entry.clientEventId) {
      entry.clientEventId = "v2-" + entry.ts + "-" + entry.id;
    }
    var payload = {
      game_id: gameId,
      client_event_id: entry.clientEventId,
      player: entry.name,
      number: entry.num,
      team: entry.team,
      action: entry.action,
      period: entry.period,
      clock: entry.clock,
      x: entry.x,
      y: entry.y,
      zone: entry.zone,
      points: shotPoints(entry.action),
    };
    try {
      window
        .fetch("/api/live-v2/events", {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCsrfToken(),
          },
          body: JSON.stringify(payload),
        })
        .then(function (resp) {
          if (resp && resp.ok) {
            entry.synced = true;
            try {
              persist();
            } catch (e) {
              /* storage may be unavailable */
            }
            markRowSynced(entry.id);
          }
          // Non-2xx: keep "pending" — retried on the next action.
        })
        .catch(function () {
          /* network error: keep "pending", retry on next action */
        });
    } catch (e) {
      /* never break the page */
    }
  }

  function flushPending() {
    try {
      state.log.forEach(function (entry) {
        if (!entry.synced && !entry.undone) {
          postEntry(entry);
        }
      });
    } catch (e) {
      /* never break the page */
    }
  }

  function syncEvent(entry) {
    // Mirrors legacy patterns (same CSRF/JSON POST shape as /live-game/save):
    // POST to /api/live-v2/events, set entry.synced = true on 2xx, keep
    // "pending" otherwise. Never throw — page must not break.
    entry.synced = false;
    try {
      postEntry(entry);
    } catch (e) {
      /* never break the page */
    }
    return false;
  }

  function pushUndo(entryId) {
    state.stack.push(entryId);
    state.stack = state.stack.slice(-MAX_STACK);
  }

  function recordAction(action, player, extra) {
    extra = extra || {};
    state.seq += 1;
    var entry = {
      id: state.seq,
      team: player ? player.team : extra.team || "HOME",
      num: player ? player.num : "–",
      name: player ? player.name : extra.teamLabel || "Team",
      action: action,
      period: state.period,
      clock: currentClock(),
      synced: false,
      undone: false,
      scoreDelta: extra.scoreDelta || 0,
      foulDelta: extra.foulDelta || 0,
      subA: extra.subA || null, // SUB swap pair — restored by undoLast()
      subB: extra.subB || null,
      x: extra.x,
      y: extra.y,
      zone: extra.zone,
      ts: Date.now(),
    };
    if (extra.scoreDelta) {
      bumpScore(entry.team, extra.scoreDelta);
    }
    if (extra.foulDelta && player) {
      player.fouls += extra.foulDelta;
    }
    if (extra.foulDelta && !player) {
      bumpFouls(extra.team || "HOME", extra.foulDelta);
    }
    if (player && (action === "FOUL" || action === "TECH FOUL")) {
      bumpFouls(player.team, 1);
    }
    flushPending(); // retry previously failed queue entries on each new action
    syncEvent(entry);
    state.log.push(entry);
    pushUndo(entry.id);
    appendLogRow(entry);
    renderRosters();
    persist();
    return entry;
  }

  function bumpScore(team, delta) {
    var id = team === "AWAY" ? "v2-team-b-score" : "v2-team-a-score";
    var el = getEl(id);
    if (el) {
      el.textContent = String((parseInt(el.textContent, 10) || 0) + delta);
    }
  }

  function bumpFouls(team, delta) {
    var id = team === "AWAY" ? "v2-team-b-fouls" : "v2-team-a-fouls";
    var el = getEl(id);
    if (el) {
      el.textContent = String((parseInt(el.textContent, 10) || 0) + delta);
    }
  }

  function undoLast() {
    while (state.stack.length) {
      var id = state.stack.pop();
      var entry = null;
      for (var i = state.log.length - 1; i >= 0; i--) {
        if (state.log[i].id === id && !state.log[i].undone) {
          entry = state.log[i];
          break;
        }
      }
      if (!entry) {
        continue; // already undone — keep popping
      }
      entry.undone = true;
      // TODO(v2): also remove the matching #v2-shot-marks circle on shot undo
      // (track circle element refs per entry id).
      if (entry.action === "SUB" && entry.subA && entry.subB) {
        var pa = findPlayer(entry.subA);
        var pb = findPlayer(entry.subB);
        if (pa && pb) {
          var t = pa.onCourt;
          pa.onCourt = pb.onCourt;
          pb.onCourt = t;
        }
      }
      if (entry.scoreDelta) {
        bumpScore(entry.team, -entry.scoreDelta);
      }
      if (entry.foulDelta) {
        var p = findPlayerByNameNum(entry);
        if (p) {
          p.fouls = Math.max(0, p.fouls - entry.foulDelta);
        }
        // Record path bumps team fouls exactly once per foulDelta (either via
        // the no-player path or the FOUL/TECH-FOUL player path), so revert once.
        bumpFouls(entry.team, -entry.foulDelta);
      }
      rerenderLog();
      renderRosters();
      persist();
      appendUndoNotice(entry);
      // Propagate to backend for synced entries: the GameEvent/ShotEvent
      // rows stay in the DB otherwise, so win-probability/analytics keep
      // counting the undone action and resync resurfaces it. Local revert
      // above is the fallback when the request fails. Same CSRF/JSON shape
      // as postEntry().
      try {
        if (entry.synced && window.fetch) {
          var gameId = getGameId();
          if (gameId != null) {
            window
              .fetch("/api/live-v2/undo", {
                method: "POST",
                credentials: "same-origin",
                headers: {
                  "Content-Type": "application/json",
                  "X-CSRFToken": getCsrfToken(),
                },
                body: JSON.stringify({ game_id: gameId }),
              })
              .catch(function () {
                /* keep local revert; stays pending-reconcile */
              });
          }
        }
      } catch (e) {
        /* never break the page */
      }
      return entry;
    }
    var hint = getEl("v2-need-player");
    if (hint) {
      hint.textContent = "Nothing to undo.";
    }
    return null;
  }

  function findPlayerByNameNum(entry) {
    var all = state.home.concat(state.away);
    for (var i = 0; i < all.length; i++) {
      if (all[i].name === entry.name && all[i].num === entry.num) {
        return all[i];
      }
    }
    return null;
  }

  function appendUndoNotice(entry) {
    var log = getEl("v2-game-log");
    if (!log) {
      return;
    }
    var p = document.createElement("p");
    p.textContent = "↩ Undid: " + entry.action + " (#" + entry.num + " " + entry.name + ")";
    log.appendChild(p);
    log.scrollTop = log.scrollHeight;
  }

  // ---------- court tap ----------
  function computeZone(x, y) {
    var dx = x - HOOP.x;
    var dy = y - HOOP.y;
    var dist = Math.sqrt(dx * dx + dy * dy);
    var points = dist > THREE_RADIUS ? 3 : 2;
    var zone;
    if (x >= 170 && x <= 330 && y <= 190) {
      zone = "PAINT";
    } else if (points === 3) {
      zone = "3PT";
    } else {
      zone = "MIDRANGE";
    }
    return { x: Math.round(x), y: Math.round(y), zone: zone, points: points, dist: Math.round(dist) };
  }

  function svgPoint(evt) {
    var svg = getEl("v2-court");
    var rect = svg.getBoundingClientRect();
    var cx = (evt.clientX - rect.left) * (COURT_W / rect.width);
    var cy = (evt.clientY - rect.top) * (COURT_H / rect.height);
    cx = Math.max(0, Math.min(COURT_W, cx));
    cy = Math.max(0, Math.min(COURT_H, cy));
    return { x: Math.round(cx), y: Math.round(cy) };
  }

  function markShot(x, y, made) {
    var g = getEl("v2-shot-marks");
    if (!g || !g.ownerSVGElement) {
      return;
    }
    var c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    c.setAttribute("cx", x);
    c.setAttribute("cy", y);
    c.setAttribute("r", "8");
    c.setAttribute("fill", "none");
    c.setAttribute("stroke", made ? "#4ade80" : "#ef4444");
    c.setAttribute("stroke-width", "3");
    g.appendChild(c);
  }

  function showPopover(x, y, zone) {
    var pop = getEl("v2-shot-popover");
    var label = getEl("v2-shot-label");
    if (!pop) {
      return;
    }
    state.pendingShot = { x: zone.x, y: zone.y, zone: zone.zone, points: zone.points };
    if (label) {
      label.textContent = zone.points + "PT · " + zone.zone + " (" + zone.x + "," + zone.y + ") — made or miss?";
    }
    pop.hidden = false;
    // Position near tap, clamped inside wrap.
    var wrap = getEl("v2-court-wrap");
    if (wrap) {
      var wr = wrap.getBoundingClientRect();
      var left = (x / COURT_W) * wr.width;
      var top = (y / COURT_H) * wr.height;
      pop.style.left = Math.max(0, Math.min(wr.width - 200, left + 12)) + "px";
      pop.style.top = Math.max(0, Math.min(wr.height - 120, top + 12)) + "px";
    }
    var madeBtn = getEl("v2-shot-made");
    if (madeBtn) {
      madeBtn.focus();
    }
  }

  function hidePopover() {
    var pop = getEl("v2-shot-popover");
    if (pop) {
      pop.hidden = true;
    }
    state.pendingShot = null;
  }

  function resolveShot(made) {
    var shot = state.pendingShot;
    if (!shot) {
      return;
    }
    var player = requireSelection();
    if (!player) {
      return; // keep popover open so they can select then retry
    }
    var action = made ? shot.points + "PT MADE" : shot.points + "PT MISS";
    recordAction(action, player, {
      x: shot.x,
      y: shot.y,
      zone: shot.zone,
      scoreDelta: made ? shot.points : 0,
    });
    markShot(shot.x, shot.y, made);
    hidePopover();
  }

  function initCourtTap() {
    var svg = getEl("v2-court");
    if (!svg) {
      return;
    }
    svg.addEventListener("click", function (evt) {
      var pt = svgPoint(evt);
      var zone = computeZone(pt.x, pt.y);
      showPopover(pt.x, pt.y, zone);
    });
    svg.addEventListener("keydown", function (evt) {
      if (evt.key === "Enter" || evt.key === " ") {
        evt.preventDefault();
        showPopover(COURT_W / 2, 200, computeZone(COURT_W / 2, 200));
      }
    });
    var made = getEl("v2-shot-made");
    var miss = getEl("v2-shot-miss");
    var cancel = getEl("v2-shot-cancel");
    if (made) {
      made.addEventListener("click", function () {
        resolveShot(true);
      });
    }
    if (miss) {
      miss.addEventListener("click", function () {
        resolveShot(false);
      });
    }
    if (cancel) {
      cancel.addEventListener("click", hidePopover);
    }
    document.addEventListener("keydown", function (evt) {
      if (evt.key === "Escape") {
        hidePopover();
      }
    });
  }

  // ---------- action pad ----------
  var ACTIONS = {
    "v2-action-assist": { label: "ASSIST", needsPlayer: true },
    "v2-action-rebound": { label: "REBOUND", needsPlayer: true },
    "v2-action-block": { label: "BLOCK", needsPlayer: true },
    "v2-action-steal": { label: "STEAL", needsPlayer: true },
    "v2-action-ft-made": { label: "FT MADE", needsPlayer: true, scoreDelta: 1 },
    "v2-action-ft-miss": { label: "FT MISS", needsPlayer: true },
    "v2-action-foul": { label: "FOUL", needsPlayer: true, foulDelta: 1 },
    "v2-action-tech": { label: "TECH FOUL", needsPlayer: true, foulDelta: 1 },
    "v2-action-tov": { label: "TOV", needsPlayer: true },
    "v2-action-timeout": { label: "TIME OUT", needsPlayer: false },
  };

  function handleActionButton(btnId) {
    if (btnId === "v2-action-undo") {
      undoLast();
      return;
    }
    if (btnId === "v2-action-sub") {
      openSubSheet();
      return;
    }
    var cfg = ACTIONS[btnId];
    if (!cfg) {
      return;
    }
    var player = null;
    if (cfg.needsPlayer) {
      player = requireSelection();
      if (!player) {
        return;
      }
    }
    if (btnId === "v2-action-timeout") {
      var sel = state.selectedId ? findPlayer(state.selectedId) : null;
      recordAction("TIME OUT", null, { team: sel ? sel.team : "HOME", teamLabel: sel ? sel.team : "Team" });
      return;
    }
    recordAction(cfg.label, player, { scoreDelta: cfg.scoreDelta || 0, foulDelta: cfg.foulDelta || 0 });
  }

  function initActionPad() {
    Object.keys(ACTIONS).forEach(function (id) {
      var b = getEl(id);
      if (b) {
        b.addEventListener("click", function () {
          handleActionButton(id);
        });
      }
    });
    var undo = getEl("v2-action-undo");
    if (undo) {
      undo.addEventListener("click", function () {
        handleActionButton("v2-action-undo");
      });
    }
    var sub = getEl("v2-action-sub");
    if (sub) {
      sub.addEventListener("click", function () {
        handleActionButton("v2-action-sub");
      });
    }
    var share = getEl("v2-action-share");
    if (share) {
      share.addEventListener("click", function () {
        shareHalftime();
      });
    }
    var close = getEl("v2-sub-close");
    if (close) {
      close.addEventListener("click", closeSubSheet);
    }
  }

  // ---------- halftime one-tap share (Slice N1) ----------
  function setShareStatus(msg) {
    var el = getEl("v2-need-player");
    if (el) {
      el.textContent = msg;
    }
  }

  function showShareText(text, copied) {
    // Fallback path: no staff group configured server-side. Render the
    // message inline so it can be copied manually, and also try the
    // clipboard when the browser allows it. Never throws.
    var el = getEl("v2-need-player");
    if (!el) {
      return;
    }
    try {
      el.textContent = "";
      var note = document.createElement("div");
      note.textContent = copied
        ? "Halftime update copied to clipboard:"
        : "No staff group configured — copy manually:";
      el.appendChild(note);
      var pre = document.createElement("pre");
      pre.textContent = text;
      pre.style.whiteSpace = "pre-wrap";
      pre.style.textAlign = "left";
      el.appendChild(pre);
    } catch (e) {
      /* never break the page */
    }
  }

  function textOf(id, fallback) {
    var el = getEl(id);
    return el && el.textContent ? el.textContent.trim() : fallback;
  }

  function collectHalftimePayload() {
    var stats = {};
    function ensure(name) {
      if (!stats[name]) {
        stats[name] = {
          points: 0, fgm: 0, fga: 0, tpm: 0, tpa: 0, ftm: 0, fta: 0,
          oreb: 0, dreb: 0, ast: 0, stl: 0, blk: 0, tov: 0, pf: 0,
          minutes_seconds: 0, plus_minus: 0,
        };
      }
      return stats[name];
    }
    // Roster names first so the payload is never empty, even scoreless.
    state.home.concat(state.away).forEach(function (p) {
      if (p && p.name) {
        ensure(p.name);
      }
    });
    state.log.forEach(function (e) {
      if (!e || e.undone || !e.name) {
        return;
      }
      if (e.scoreDelta) {
        ensure(e.name).points += e.scoreDelta;
      }
    });
    var boot = window.V2_BOOTSTRAP || {};
    return {
      opponent: textOf("v2-team-b-name", "Opponent"),
      date: boot.nowDate || "",
      team_score: parseInt(textOf("v2-team-a-score", "0"), 10) || 0,
      opp_score: parseInt(textOf("v2-team-b-score", "0"), 10) || 0,
      player_stats: stats,
    };
  }

  function shareHalftime() {
    // One tap: POST the current console state to /reports/live/halftime-share.
    // The server texts the staff group when one is configured; otherwise it
    // returns the message for manual copy. Never break the page on failure.
    if (!window.fetch) {
      setShareStatus("Sharing is unavailable in this browser.");
      return;
    }
    setShareStatus("Sharing halftime update…");
    try {
      window
        .fetch("/reports/live/halftime-share", {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCsrfToken(),
          },
          body: JSON.stringify(collectHalftimePayload()),
        })
        .then(function (resp) {
          return resp.json().then(function (data) {
            return { ok: resp.ok, data: data || {} };
          });
        })
        .then(function (result) {
          if (result.ok && result.data.sent) {
            setShareStatus("Halftime update sent to staff. ✓");
          } else if (result.ok && result.data.text) {
            var msg = result.data.text;
            try {
              if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(msg).then(
                  function () {
                    showShareText(msg, true);
                  },
                  function () {
                    showShareText(msg, false);
                  }
                );
              } else {
                showShareText(msg, false);
              }
            } catch (e) {
              showShareText(msg, false);
            }
          } else {
            setShareStatus(
              "Share failed: " + (result.data.error || "server error")
            );
          }
        })
        .catch(function () {
          setShareStatus("Share failed: network error. Retry from the log.");
        });
    } catch (e) {
      setShareStatus("Share failed unexpectedly.");
    }
  }

  // ---------- substitutions ----------
  var subArmed = [];

  function openSubSheet() {
    var sheet = getEl("v2-sub-sheet");
    var list = getEl("v2-sub-list");
    if (!sheet || !list) {
      return;
    }
    subArmed = [];
    renderSubList();
    sheet.hidden = false;
  }

  function closeSubSheet() {
    var sheet = getEl("v2-sub-sheet");
    if (sheet) {
      sheet.hidden = true;
    }
    subArmed = [];
  }

  function renderSubList() {
    var list = getEl("v2-sub-list");
    if (!list) {
      return;
    }
    list.innerHTML = "";
    // Only the selected player's team matters; default HOME if none selected.
    var sel = state.selectedId ? findPlayer(state.selectedId) : null;
    var team = sel && sel.team === "AWAY" ? "AWAY" : "HOME";
    var group = team === "AWAY" ? state.away : state.home;
    group.forEach(function (p) {
      var row = document.createElement("button");
      row.type = "button";
      row.className = "v2-sub-row" + (subArmed.indexOf(p.id) >= 0 ? " v2-armed" : "");
      row.dataset.playerId = p.id;
      var label = document.createElement("span");
      label.textContent = "#" + p.num + " " + p.name + " — " + (p.onCourt ? "ON-COURT" : "BENCH");
      row.appendChild(label);
      row.addEventListener("click", function () {
        armSub(p.id);
      });
      list.appendChild(row);
    });
  }

  function armSub(id) {
    var ix = subArmed.indexOf(id);
    if (ix >= 0) {
      subArmed.splice(ix, 1);
    } else {
      subArmed.push(id);
    }
    if (subArmed.length === 2) {
      var a = findPlayer(subArmed[0]);
      var b = findPlayer(subArmed[1]);
      if (a && b && a.team === b.team && a.onCourt !== b.onCourt) {
        var tmp = a.onCourt;
        a.onCourt = b.onCourt;
        b.onCourt = tmp;
        recordAction("SUB", null, {
          team: a.team,
          teamLabel: a.team,
          subA: a.id,
          subB: b.id,
        });
        // Replace generic SUB log text with detail.
        var last = state.log[state.log.length - 1];
        if (last) {
          last.name = "#" + a.num + " " + a.name + " ↔ #" + b.num + " " + b.name;
          rerenderLog();
          persist();
        }
        subArmed = [];
        // The selected player may have left the court — clear so the next
        // action can't be recorded against a benched player.
        state.selectedId = null;
        renderRosters();
        renderSubList();
        return;
      }
      // Invalid pair — keep the latest tap only.
      subArmed = [id];
    }
    renderSubList();
  }

  // ---------- score strip / periods ----------
  function renderPeriod() {
    var el = getEl("v2-period");
    if (el) {
      el.textContent = "P" + state.period;
    }
  }

  function renderClock() {
    var el = getEl("v2-clock");
    if (el) {
      el.textContent = state.clock;
    }
  }

  function setPeriod(n) {
    if (n < 1) {
      n = 1;
    }
    var changed = n !== state.period;
    state.period = n;
    renderPeriod();
    if (changed) {
      appendBanner("START OF PERIOD " + state.period);
      persist();
    }
  }

  function initScoreStrip() {
    // A restored session is the source of truth for period and clock; the
    // server-rendered P1/10:00 defaults must not clobber it.
    var restored = state.hadRestore;
    var periodEl = getEl("v2-period");
    if (periodEl && !restored) {
      var m = /P?\s*(\d+)/.exec(periodEl.textContent || "");
      if (m) {
        state.period = parseInt(m[1], 10) || 1;
      }
    }
    var clockEl = getEl("v2-clock");
    if (clockEl && !restored && clockEl.textContent.trim()) {
      state.clock = clockEl.textContent.trim();
    }
    renderPeriod();
    renderClock();

    var prev = getEl("v2-period-prev");
    var next = getEl("v2-period-next");
    if (prev) {
      prev.addEventListener("click", function () {
        setPeriod(state.period - 1);
      });
    }
    if (next) {
      next.addEventListener("click", function () {
        setPeriod(state.period + 1);
      });
    }
  }

  function initLiveGameV2() {
    restore();
    buildRosters();
    initScoreStrip();
    // Re-render any restored log rows (period banners are re-created on change).
    rerenderLog();
    renderRosters();
    initCourtTap();
    initActionPad();
    persist();
  }

  window.LiveGameV2 = {
    init: initLiveGameV2,
    setPeriod: setPeriod,
    selectPlayer: selectPlayer,
    computeZone: computeZone,
    recordAction: recordAction,
    undo: undoLast,
    getState: function () {
      return {
        period: state.period,
        clock: currentClock(),
        selectedId: state.selectedId,
        home: state.home,
        away: state.away,
        log: state.log,
        stack: state.stack,
      };
    },
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initLiveGameV2);
  } else {
    initLiveGameV2();
  }
})();
