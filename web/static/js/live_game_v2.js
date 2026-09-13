/**
 * Live Game v2 console shell (slice A1).
 *
 * Wires the score-strip controls only. Roster rails, court tap, and the
 * action pad are stub hooks for later slices — see TODO(v2) markers.
 */
(function () {
  "use strict";

  var state = {
    period: 1,
    clock: "10:00",
  };

  function getEl(id) {
    return document.getElementById(id);
  }

  function appendLog(message) {
    var log = getEl("v2-game-log");
    if (!log) {
      return;
    }
    var p = document.createElement("p");
    p.textContent = message;
    log.appendChild(p);
    log.scrollTop = log.scrollHeight;
  }

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
      appendLog("START OF PERIOD " + state.period);
    }
  }

  // TODO(v2): roster rails — render Team A / Team B rails into
  // #v2-roster-home and #v2-roster-away (later slice).
  function initRosterRails() {
    getEl("v2-roster-home");
    getEl("v2-roster-away");
  }

  // TODO(v2): court tap — attach tap/click handling on #v2-court (later slice).
  function initCourtTap() {
    getEl("v2-court");
  }

  // TODO(v2): action pad — wire buttons inside #v2-action-pad (later slice).
  function initActionPad() {
    getEl("v2-action-pad");
  }

  function initScoreStrip() {
    var periodEl = getEl("v2-period");
    if (periodEl) {
      var m = /P?\s*(\d+)/.exec(periodEl.textContent || "");
      if (m) {
        state.period = parseInt(m[1], 10) || 1;
      }
    }
    var clockEl = getEl("v2-clock");
    if (clockEl && clockEl.textContent.trim()) {
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
    initScoreStrip();
    initRosterRails();
    initCourtTap();
    initActionPad();
  }

  window.LiveGameV2 = {
    init: initLiveGameV2,
    setPeriod: setPeriod,
    getState: function () {
      return { period: state.period, clock: state.clock };
    },
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initLiveGameV2);
  } else {
    initLiveGameV2();
  }
})();
