class GameTracker {
    constructor() {
        this.fullRoster = [];
        this.activeLineup = [];
        this.stats = {};
        this.opponentScore = 0;
        this.shotLocations = [];
        this.gameEvents = [];

        // Pending actions
        this.pendingMadeShot = null;
        this.pendingOreb = null;
        this.pendingMissShot = null;
        this.pendingPlaySelection = null; // Track pending play selection
        this.pendingTurnover = null; // NEW: Track pending turnover

        // Timer State
        this.timerInterval = null;
        this.quarter = 1;
        this.clockSeconds = 0;
        this.isClockRunning = false;

        // Auto-cache timer
        this.autoCacheInterval = null;
        this.lastCacheTimestamp = 0;

        // UI Helpers
        this.shotLocListenerAttached = false;

        // Plays cache
        this.playsCache = [];
        this.playTypes = [];
        this.recentPlays = []; // NEW: Track recently used plays
        this.showSpecial = false; // Toggle for special plays

        // Play selector toggle state
        this.playSelectMode = true;  // Toggle state for play selector

        // Constants
        this.CONSTANTS = {
            SVG_WIDTH: 500,
            SVG_HEIGHT: 470,
            COURT_HITBOX_ID: 'court-hitbox',
            SVG_ID: 'halfCourtSvg',
            STORAGE_KEY: 'basketball_live_game_state',
            CACHE_KEY: 'basketball_live_game_cache',
            MAX_CACHED_GAMES: 3,
            AUTO_CACHE_INTERVAL_MS: 30000, // 30 seconds
            MAX_RECENT_PLAYS: 3 // Show top 3 recent plays
        };

        this.init();
    }

    init() {
        this.loadState();
        this.bindEvents();
        this.renderCachedGamesUI();
        this.loadPlays(); // Load plays on init

        // If we loaded a state where game was started, show tracker
        if (Object.keys(this.stats).length > 0) {
            document.getElementById('setup-panel').style.display = 'none';
            document.getElementById('lineup-panel').style.display = 'none';
            document.getElementById('tracker-panel').style.display = 'block';

            // Restore opponent name display
            const oppName = document.getElementById('opponent').value || "Opponent";
            document.getElementById('display-opponent').innerText = "vs " + oppName;

            // Restore quarter and clock display
            document.getElementById('quarter-display').innerText = 'Q' + this.quarter;
            this.updateClockDisplay();
            document.getElementById('opp-score-display').innerText = this.opponentScore;

            this.renderActivePlayers();
            this.updateScoreboard();

            // Start auto-cache timer for active game
            this.startAutoCacheTimer();
        }
    }

    bindEvents() {
        // Bind UI buttons that are static (not generated)
        // Note: Generated buttons call methods via global instance 'gameTracker'
        window.onbeforeunload = () => {
            if (this.isClockRunning) return "Game is in progress. Are you sure?";
        };
    }

    // --- PLAY SELECTOR TOGGLE ---
    togglePlaySelector() {
        this.playSelectMode = !this.playSelectMode;
        const btn = document.getElementById('btn-play-selector');
        const status = document.getElementById('play-selector-status');
        
        if (this.playSelectMode) {
            btn.classList.remove('btn-secondary');
            btn.classList.add('btn-info');
            status.textContent = 'ON';
            status.style.color = '#28a745';
        } else {
            btn.classList.remove('btn-info');
            btn.classList.add('btn-secondary');
            status.textContent = 'OFF';
            status.style.color = '#6c757d';
        }
        this.saveState();
    }

    // --- PLAYS LOADING ---
    loadPlays() {
        // First try to load from injected variable
        if (window.AVAILABLE_PLAYS && window.AVAILABLE_PLAYS.length > 0) {
            console.log("Loading plays from injected data...");
            this.playsCache = window.AVAILABLE_PLAYS;
            this.processPlayTypes();
            return;
        }

        const csrfToken = document.getElementById('csrf_token')?.value || '';
        
        // Fallback to API fetch
        fetch('/api/plays', {
            method: 'GET',
            headers: {
                'X-CSRFToken': csrfToken
            }
        })
        .then(res => res.json())
        .then(plays => {
            console.log("Loaded plays from API:", plays.length);
            this.playsCache = plays;
            this.processPlayTypes();
        })
        .catch(err => console.error('Failed to load plays:', err));
    }

    processPlayTypes() {
        const types = [...new Set(this.playsCache.map(p => p.type))];
        this.playTypes = types.sort();
        // We no longer populate a dropdown filter, as UI is now toggle-based
    }

    toggleSpecialPlays() {
        this.showSpecial = !this.showSpecial;
        const btn = document.getElementById('btn-toggle-special');
        if (this.showSpecial) {
            btn.classList.remove('btn-outline-secondary');
            btn.classList.add('btn-warning');
            btn.innerHTML = '<i class="fas fa-star"></i> Hide Special';
        } else {
            btn.classList.remove('btn-warning');
            btn.classList.add('btn-outline-secondary');
            btn.innerHTML = '<i class="fas fa-star"></i> Show Special';
        }
        this.renderPlaysList(); // Re-render with new filter
    }

    // NEW: Track recently used plays
    addToRecentPlays(play) {
        // Remove if already in list
        this.recentPlays = this.recentPlays.filter(p => p.id !== play.id);
        // Add to front
        this.recentPlays.unshift(play);
        // Keep only top 3
        this.recentPlays = this.recentPlays.slice(0, this.CONSTANTS.MAX_RECENT_PLAYS);
    }

    renderPlaysList() {
        const list = document.getElementById('plays-list');
        if (!list) return;

        // Default to Offense unless Special is toggled
        let targetType = 'Offense';
        if (this.showSpecial) {
            // When Special is ON, we show Special plays. 
            // The requirement says "toggle button not list to show special", 
            // likely meaning toggle replaces the list or adds to it.
            // We'll show Special plays INSTEAD of Offense for clarity, or filter for them.
            targetType = 'Special';
        }

        // Filter by type
        let filteredPlays = this.playsCache.filter(p => p.type === targetType);
        
        // MACRO GROUPING LOGIC
        // "DueBasso-1" -> Macro "DueBasso"
        // We will group by the part of the name before the first hyphen
        const macroMap = new Map();

        filteredPlays.forEach(play => {
            // Check if name has a hyphen (e.g. "DueBasso-1")
            const parts = play.name.split('-');
            let macroName = play.name;
            
            // If it looks like a variation (e.g. ends in number or single char after hyphen)
            if (parts.length > 1) {
                macroName = parts[0].trim();
            }

            if (!macroMap.has(macroName)) {
                macroMap.set(macroName, []);
            }
            macroMap.get(macroName).push(play);
        });

        list.innerHTML = '';

        if (filteredPlays.length === 0) {
            list.innerHTML = `<div class="list-group-item text-muted text-center">No ${targetType} plays found</div>`;
            return;
        }

        // Show recent plays ONLY if in standard Offense mode
        if (targetType === 'Offense' && this.recentPlays.length > 0) {
            const recentHeader = document.createElement('div');
            recentHeader.className = 'list-group-item bg-light py-1';
            recentHeader.innerHTML = '<small class="text-primary font-weight-bold">RECENT</small>';
            list.appendChild(recentHeader);

            this.recentPlays.forEach(play => {
                // Determine if recent play is a variation, display its full name or macro?
                // Usually recents are specific. We'll show the specific one clicked.
                const btn = this.createPlayButton(play, false); 
                btn.classList.add('border-primary');
                list.appendChild(btn);
            });
            
            const divider = document.createElement('div');
            divider.className = 'list-group-item bg-light py-1 mt-2';
            divider.innerHTML = '<small class="text-secondary font-weight-bold">ALL PLAYS</small>';
            list.appendChild(divider);
        }

        // Render Macro Groups
        // Convert map to array and sort alpha
        const macros = Array.from(macroMap.entries()).sort((a, b) => a[0].localeCompare(b[0]));

        macros.forEach(([name, variations]) => {
            // If only 1 variation, just show it as a play
            if (variations.length === 1) {
                list.appendChild(this.createPlayButton(variations[0], false));
            } else {
                // Multiple variations: Show the MACRO name.
                // Clicking it selects the FIRST variation (or could expand, but user said "not both")
                // We'll assume clicking the macro selects the "base" or first variation.
                // Better yet: Pass the first one, but label it with the Macro Name.
                list.appendChild(this.createPlayButton(variations[0], true, name));
            }
        });
    }

    // NEW: Helper to create play button
    // isMacro: true if this represents a group
    // customLabel: override the play name (e.g. "DueBasso" instead of "DueBasso-1")
    createPlayButton(play, isMacro = false, customLabel = null) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'list-group-item list-group-item-action py-2';
        btn.style.cursor = 'pointer';
        
        const displayName = customLabel || play.name;
        
        btn.innerHTML = `
            <div class="d-flex justify-content-between align-items-center">
                <span class="font-weight-bold">${displayName}</span>
                ${isMacro ? '<small class="badge badge-light border text-muted">Group</small>' : ''}
            </div>
        `;
        btn.onclick = () => this.selectPlay(play); // If macro, this selects the first variation (play object passed in)
        return btn;
    }

    openPlaySelector(eventType, shooter = null, shotType = null) {
        // Check if play selector toggle is ON
        if (!this.playSelectMode) {
            this.finalizePlaySelection(null);
            return;
        }

        this.pendingPlaySelection = {
            eventType,  // 'SHOT_2PT', 'SHOT_3PT', 'TURNOVER'
            shooter,
            shotType
        };

        // Reset to Offense view by default
        this.showSpecial = false;
        this.updateSpecialToggleBtn(); // helper to reset button style

        // Render
        this.renderPlaysList();
        $('#playSelectorModal').modal('show');
    }

    updateSpecialToggleBtn() {
        const btn = document.getElementById('btn-toggle-special');
        if (btn) {
            btn.classList.remove('btn-warning');
            btn.classList.add('btn-outline-secondary');
            btn.innerHTML = '<i class="fas fa-star"></i> Show Special';
        }
    }

    selectPlay(play) {
        if (!this.pendingPlaySelection && !this.pendingTurnover) {
            $('#playSelectorModal').modal('hide');
            return;
        }

        // Add to recent plays
        this.addToRecentPlays(play);

        // Finalize with selected play
        this.finalizePlaySelection(play);
        $('#playSelectorModal').modal('hide');
    }

    // NEW: Skip play selection (from modal "Skip / None" button)
    skipPlaySelection() {
        this.finalizePlaySelection(null);
        $('#playSelectorModal').modal('hide');
    }

    // NEW: Centralized method to finalize play selection
    finalizePlaySelection(play) {
        // Handle turnover case
        if (this.pendingTurnover) {
            const { player } = this.pendingTurnover;
            
            // Increment turnover stat
            this.updateStat(player, 'tov', 1);

            // Log turnover event with or without play
            const event = {
                type: 'TURNOVER',
                player: player,
                detail: play ? {
                    play_id: play.id,
                    play_name: play.name
                } : null,
                quarter: this.quarter,
                clockSeconds: this.clockSeconds,
                timestamp: Date.now()
            };
            this.gameEvents.push(event);

            this.pendingTurnover = null;
            this.saveState();
            return;
        }

        // Handle shot case (already logged by confirmShotLocationFromMap)
        if (this.pendingPlaySelection) {
            const { eventType, shooter } = this.pendingPlaySelection;

            // Only log event if play was selected
            if (play) {
                const event = {
                    type: eventType,
                    player: shooter,
                    detail: {
                        play_id: play.id,
                        play_name: play.name
                    },
                    quarter: this.quarter,
                    clockSeconds: this.clockSeconds,
                    timestamp: Date.now()
                };
                this.gameEvents.push(event);
            }

            this.pendingPlaySelection = null;
            this.saveState();
        }
    }

    // NEW: Open turnover flow with play selector
    recordTurnover(player) {
        this.pendingTurnover = { player };
        
        // Open play selector if enabled
        if (this.playSelectMode) {
            this.openPlaySelector('TURNOVER', player);
        } else {
            // If play selector is off, just increment stat
            this.finalizePlaySelection(null);
        }
    }

    // --- AUTO-CACHE TIMER ---
    startAutoCacheTimer() {
        // Clear any existing timer
        if (this.autoCacheInterval) {
            clearInterval(this.autoCacheInterval);
        }

        // Start new timer
        this.autoCacheInterval = setInterval(() => {
            const now = Date.now();
            const timeSinceLastCache = now - this.lastCacheTimestamp;

            // Only auto-cache if 30s have passed since last cache
            if (timeSinceLastCache >= this.CONSTANTS.AUTO_CACHE_INTERVAL_MS) {
                this.addToCache(this.getCurrentState(), true); // true = auto-cache
            }
        }, this.CONSTANTS.AUTO_CACHE_INTERVAL_MS);
    }

    stopAutoCacheTimer() {
        if (this.autoCacheInterval) {
            clearInterval(this.autoCacheInterval);
            this.autoCacheInterval = null;
        }
    }

    // --- CACHE MANAGEMENT ---
    getCachedGames() {
        const cached = localStorage.getItem(this.CONSTANTS.CACHE_KEY);
        if (!cached) return [];
        try {
            return JSON.parse(cached);
        } catch (e) {
            console.error("Failed to parse cached games", e);
            return [];
        }
    }

    addToCache(state, isAutoCache = false) {
        const cache = this.getCachedGames();

        // Create a snapshot with timestamp
        const snapshot = {
            ...state,
            timestamp: Date.now(),
            id: Date.now() + Math.random() // unique ID
        };

        // Update last cache timestamp
        this.lastCacheTimestamp = snapshot.timestamp;

        // Add to front of array
        cache.unshift(snapshot);

        // Keep only the most recent MAX_CACHED_GAMES
        const trimmed = cache.slice(0, this.CONSTANTS.MAX_CACHED_GAMES);

        localStorage.setItem(this.CONSTANTS.CACHE_KEY, JSON.stringify(trimmed));
        this.renderCachedGamesUI();

        // Optional: Log auto-cache events for debugging
        if (isAutoCache) {
            console.log('[Auto-cache] Game state saved at', new Date(snapshot.timestamp).toLocaleTimeString());
        }
    }

    removeFromCache(id) {
        let cache = this.getCachedGames();
        cache = cache.filter(g => g.id !== id);
        localStorage.setItem(this.CONSTANTS.CACHE_KEY, JSON.stringify(cache));
        this.renderCachedGamesUI();
    }

    restoreFromCache(id) {
        const cache = this.getCachedGames();
        const snapshot = cache.find(g => g.id === id);
        if (!snapshot) {
            alert("Cached game not found.");
            return;
        }

        if (!confirm(`Restore game vs ${snapshot.opponentName || 'Unknown'} from ${this.formatTimestamp(snapshot.timestamp)}? Current progress will be lost.`)) {
            return;
        }

        // Restore state from snapshot
        this.fullRoster = snapshot.fullRoster || [];
        this.activeLineup = snapshot.activeLineup || [];
        this.stats = snapshot.stats || {};
        this.opponentScore = snapshot.opponentScore || 0;
        this.shotLocations = snapshot.shotLocations || [];
        this.gameEvents = snapshot.gameEvents || [];
        this.quarter = snapshot.quarter || 1;
        this.clockSeconds = snapshot.clockSeconds || 0;

        // Restore inputs
        if (snapshot.gameDate) document.getElementById('game-date').value = snapshot.gameDate;
        if (snapshot.opponentName) document.getElementById('opponent').value = snapshot.opponentName;
        if (snapshot.gameType) document.getElementById('game-type').value = snapshot.gameType;

        // Save to current state and show tracker
        this.saveState();

        // Navigate to tracker
        if (Object.keys(this.stats).length > 0) {
            document.getElementById('setup-panel').style.display = 'none';
            document.getElementById('lineup-panel').style.display = 'none';
            document.getElementById('tracker-panel').style.display = 'block';

            const oppName = document.getElementById('opponent').value || "Opponent";
            document.getElementById('display-opponent').innerText = "vs " + oppName;

            document.getElementById('quarter-display').innerText = 'Q' + this.quarter;
            this.updateClockDisplay();
            document.getElementById('opp-score-display').innerText = this.opponentScore;

            this.renderActivePlayers();
            this.updateScoreboard();

            // Restart auto-cache timer
            this.startAutoCacheTimer();
        }
    }

    renderCachedGamesUI() {
        const container = document.getElementById('cached-games-list');
        if (!container) return;

        const cache = this.getCachedGames();

        if (cache.length === 0) {
            container.innerHTML = '<p class="text-muted small">No saved games in cache.</p>';
            return;
        }

        container.innerHTML = '<h6 class="mb-2">Recent Games (Last 3)</h6>';

        cache.forEach(game => {
            let totalPoints = 0;
            if (game.stats) {
                Object.values(game.stats).forEach(s => totalPoints += (s.points || 0));
            }

            const div = document.createElement('div');
            div.className = 'card mb-2 shadow-sm';
            div.innerHTML = `
                <div class="card-body p-2">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <strong>${game.opponentName || 'Unknown'}</strong>
                            <small class="text-muted d-block">${this.formatTimestamp(game.timestamp)}</small>
                            <small class="text-muted">Score: ${totalPoints}-${game.opponentScore || 0} | Q${game.quarter || 1}</small>
                        </div>
                        <div class="btn-group btn-group-sm">
                            <button class="btn btn-outline-primary" onclick="gameTracker.restoreFromCache(${game.id})" title="Restore this game">
                                <i class="fas fa-undo"></i> Restore
                            </button>
                            <button class="btn btn-outline-danger" onclick="gameTracker.removeFromCache(${game.id})" title="Delete from cache">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                </div>
            `;
            container.appendChild(div);
        });
    }

    formatTimestamp(timestamp) {
        const date = new Date(timestamp);
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);

        if (diffMins < 1) return 'Just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        if (diffHours < 24) return `${diffHours}h ago`;
        if (diffDays < 7) return `${diffDays}d ago`;

        return date.toLocaleDateString();
    }

    // --- PERSISTENCE ---
    saveState() {
        const state = {
            fullRoster: this.fullRoster,
            activeLineup: this.activeLineup,
            stats: this.stats,
            opponentScore: this.opponentScore,
            shotLocations: this.shotLocations,
            gameEvents: this.gameEvents,
            quarter: this.quarter,
            clockSeconds: this.clockSeconds,
            // Inputs
            gameDate: document.getElementById('game-date').value,
            opponentName: document.getElementById('opponent').value,
            gameType: document.getElementById('game-type').value
        };
        localStorage.setItem(this.CONSTANTS.STORAGE_KEY, JSON.stringify(state));
    }

    loadState() {
        const stored = localStorage.getItem(this.CONSTANTS.STORAGE_KEY);
        if (stored) {
            try {
                const state = JSON.parse(stored);
                this.fullRoster = state.fullRoster || [];
                this.activeLineup = state.activeLineup || [];
                this.stats = state.stats || {};
                this.opponentScore = state.opponentScore || 0;
                this.shotLocations = state.shotLocations || [];
                this.gameEvents = state.gameEvents || [];
                this.quarter = state.quarter || 1;
                this.clockSeconds = state.clockSeconds || 0;

                // Restore inputs
                if (state.gameDate) document.getElementById('game-date').value = state.gameDate;
                if (state.opponentName) document.getElementById('opponent').value = state.opponentName;
                if (state.gameType) document.getElementById('game-type').value = state.gameType;

            } catch (e) {
                console.error("Failed to load state", e);
            }
        }
    }

    clearState() {
        localStorage.removeItem(this.CONSTANTS.STORAGE_KEY);
        this.stopAutoCacheTimer();
    }

    // --- SETUP ---
    toggleRosterPlayer(name, btn) {
        if (this.fullRoster.includes(name)) {
            this.fullRoster = this.fullRoster.filter(p => p !== name);
            btn.classList.remove('active', 'btn-primary');
            btn.classList.add('btn-outline-secondary');
        } else {
            this.fullRoster.push(name);
            btn.classList.remove('btn-outline-secondary');
            btn.classList.add('active', 'btn-primary');
        }
        this.saveState();
    }

    addNewPlayer() {
        const input = document.getElementById('new-player-name');
        const name = input.value.trim();
        if (name && !this.fullRoster.includes(name)) {
            this.fullRoster.push(name);
            const container = document.getElementById('roster-selection');
            const btn = document.createElement('button');
            btn.className = 'btn btn-primary btn-sm active player-select-btn';
            btn.style.margin = '2px';
            btn.innerText = name;
            btn.onclick = (e) => this.toggleRosterPlayer(name, e.target);
            container.appendChild(btn);
            input.value = '';
            this.saveState();
        }
    }

    goToLineupSelection() {
        if (this.fullRoster.length < 5) {
            alert("Please select at least 5 players for the roster.");
            return;
        }
        document.getElementById('setup-panel').style.display = 'none';
        document.getElementById('lineup-panel').style.display = 'block';

        const container = document.getElementById('starter-selection');
        container.innerHTML = '';
        this.fullRoster.forEach(p => {
            const btn = document.createElement('button');
            btn.className = 'btn btn-outline-secondary m-1';
            btn.innerText = p;
            btn.onclick = (e) => {
                if (this.activeLineup.includes(p)) {
                    this.activeLineup = this.activeLineup.filter(x => x !== p);
                    e.target.classList.remove('btn-primary');
                    e.target.classList.add('btn-outline-secondary');
                } else {
                    if (this.activeLineup.length >= 5) {
                        alert("You can only select 5 starters.");
                        return;
                    }
                    this.activeLineup.push(p);
                    e.target.classList.remove('btn-outline-secondary');
                    e.target.classList.add('btn-primary');
                }
                this.saveState(); // Save selection progress
            };
            // Pre-select if already in activeLineup (from reload)
            if (this.activeLineup.includes(p)) {
                btn.classList.remove('btn-outline-secondary');
                btn.classList.add('btn-primary');
            }
            container.appendChild(btn);
        });
        this.saveState();
    }

    startGame() {
        if (this.activeLineup.length !== 5) {
            alert("Please select exactly 5 starters.");
            return;
        }
        const opponent = document.getElementById('opponent').value;
        if (!opponent) {
            alert("Please enter an opponent name.");
            return;
        }

        // Initialize stats only if empty (preserve on reload)
        if (Object.keys(this.stats).length === 0) {
            this.fullRoster.forEach(p => {
                this.stats[p] = {
                    points: 0, fgm: 0, fga: 0, tpm: 0, tpa: 0, ftm: 0, fta: 0,
                    oreb: 0, dreb: 0, ast: 0, tov: 0, stl: 0, blk: 0, pf: 0,
                    plus_minus: 0,
                    minutes_seconds: 0,
                    last_sub_in: this.activeLineup.includes(p) ? Date.now() : null
                };
            });
        } else {
            // Ensure last_sub_in is reset for starters if resuming
            this.activeLineup.forEach(p => {
                if (!this.stats[p].last_sub_in) this.stats[p].last_sub_in = Date.now();
            });
        }

        document.getElementById('lineup-panel').style.display = 'none';
        document.getElementById('tracker-panel').style.display = 'block';
        document.getElementById('display-opponent').innerText = "vs " + opponent;

        this.renderActivePlayers();
        this.saveState();

        // Start auto-cache timer when game starts
        this.startAutoCacheTimer();
    }

    // --- GAMEPLAY ---
    renderActivePlayers() {
        const grid = document.getElementById('player-grid');
        grid.innerHTML = '';

        this.activeLineup.forEach(p => {
            const s = this.stats[p];
            const pmClass = s.plus_minus > 0 ? 'badge-success' : (s.plus_minus < 0 ? 'badge-danger' : 'badge-secondary');
            const pmSign = s.plus_minus > 0 ? '+' : '';

            grid.innerHTML += `
                <div class="col-md-6 col-lg-4 mb-3">
                    <div class="card h-100 shadow-sm border-0">
                        <div class="card-header bg-primary text-white d-flex justify-content-between align-items-center py-2">
                            <h5 class="mb-0 text-truncate" style="max-width: 50%; font-weight: bold;">${p}</h5>
                            <div>
                                <span class="badge ${pmClass} mr-1" id="pm-${p}" style="font-size: 0.9em;" title="Plus/Minus">${pmSign}${s.plus_minus}</span>
                                <span class="badge badge-light mr-1" id="pts-${p}" style="font-size: 0.9em;">${s.points} PTS</span>
                                <span class="badge badge-warning" id="pf-badge-${p}" style="font-size: 0.9em;">${s.pf} PF</span>
                            </div>
                        </div>
                        <div class="card-body p-2">

                            <!-- SHOOTING SECTION -->
                            <div class="mb-2 border-bottom pb-2">
                                <!-- 2PT -->
                                <div class="d-flex justify-content-between align-items-center mb-1">
                                    <span class="font-weight-bold small text-muted" style="width: 40px;">2PT</span>
                                    <div class="btn-group btn-group-sm">
                                        <button class="btn btn-outline-danger py-0" onclick="gameTracker.updateShooting('${p}', '2pt', -1, -1)">-M</button>
                                        <button class="btn btn-outline-secondary py-0" onclick="gameTracker.updateShooting('${p}', '2pt', 0, -1)">-A</button>
                                    </div>
                                    <span class="mx-2 font-weight-bold" id="disp-2pt-${p}">${(s.fgm - s.tpm)}/${(s.fga - s.tpa)}</span>
                                    <div class="btn-group btn-group-sm">
                                        <button class="btn btn-outline-danger py-0" onclick="gameTracker.openMissShotLocModal('${p}', '2pt', 0)">Miss</button>
                                        <button class="btn btn-success font-weight-bold py-0" onclick="gameTracker.openAssistModal('${p}', '2pt', 2)">+2</button>
                                    </div>
                                </div>

                                <!-- 3PT -->
                                <div class="d-flex justify-content-between align-items-center mb-1">
                                    <span class="font-weight-bold small text-muted" style="width: 40px;">3PT</span>
                                    <div class="btn-group btn-group-sm">
                                        <button class="btn btn-outline-danger py-0" onclick="gameTracker.updateShooting('${p}', '3pt', -1, -1)">-M</button>
                                        <button class="btn btn-outline-secondary py-0" onclick="gameTracker.updateShooting('${p}', '3pt', 0, -1)">-A</button>
                                    </div>
                                    <span class="mx-2 font-weight-bold" id="disp-3pt-${p}">${s.tpm}/${s.tpa}</span>
                                    <div class="btn-group btn-group-sm">
                                        <button class="btn btn-outline-danger py-0" onclick="gameTracker.openMissShotLocModal('${p}', '3pt', 0)">Miss</button>
                                        <button class="btn btn-success font-weight-bold py-0" onclick="gameTracker.openAssistModal('${p}', '3pt', 3)">+3</button>
                                    </div>
                                </div>

                                <!-- FT -->
                                <div class="d-flex justify-content-between align-items-center">
                                    <span class="font-weight-bold small text-muted" style="width: 40px;">FT</span>
                                    <div class="btn-group btn-group-sm">
                                        <button class="btn btn-outline-danger py-0" onclick="gameTracker.updateShooting('${p}', 'ft', -1, -1)">-M</button>
                                        <button class="btn btn-outline-secondary py-0" onclick="gameTracker.updateShooting('${p}', 'ft', 0, -1)">-A</button>
                                    </div>
                                    <span class="mx-2 font-weight-bold" id="disp-ft-${p}">${s.ftm}/${s.fta}</span>
                                    <div class="btn-group btn-group-sm">
                                        <button class="btn btn-outline-danger py-0" onclick="gameTracker.updateShooting('${p}', 'ft', 0, 1)">Miss</button>
                                        <button class="btn btn-success font-weight-bold py-0" onclick="gameTracker.updateShooting('${p}', 'ft', 1, 1)">+1</button>
                                    </div>
                                </div>
                            </div>

                            <!-- OTHER STATS GRID -->
                            <div class="row no-gutters text-center">
                                ${this.renderStatBox(p, 'OREB', 'oreb', s.oreb)}
                                ${this.renderStatBox(p, 'DREB', 'dreb', s.dreb)}
                                ${this.renderStatBox(p, 'AST', 'ast', s.ast)}
                            </div>
                            <div class="row no-gutters text-center mt-1">
                                ${this.renderStatBox(p, 'STL', 'stl', s.stl)}
                                ${this.renderStatBox(p, 'BLK', 'blk', s.blk)}
                                ${this.renderStatBox(p, 'TOV', 'tov', s.tov, '', true)}
                            </div>
                            <div class="row no-gutters text-center mt-1">
                                ${this.renderStatBox(p, 'PF', 'pf', s.pf, 'text-danger')}
                            </div>

                            <div class="mt-2 text-center small text-muted">
                                <span id="time-${p}" class="font-weight-bold">MIN: ${this.formatMinutes(s.minutes_seconds)}</span>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        });
    }

    renderStatBox(player, label, key, value, textClass = '', isToV = false) {
        // UPDATED: Use recordTurnover method for TOV button
        const tovHtml = isToV ? `
            <div class="d-flex justify-content-center align-items-center">
                <button class="btn btn-sm btn-outline-secondary py-0 px-1" style="font-size: 0.7rem; line-height:1;" onclick="gameTracker.updateStat('${player}', '${key}', -1)">-</button>
                <span class="h5 m-0 mx-2 font-weight-bold ${textClass}" id="disp-${key}-${player}">${value}</span>
                <button class="btn btn-sm btn-outline-danger py-0 px-1" style="font-size: 0.8rem; line-height:1;" onclick="gameTracker.recordTurnover('${player}')">+</button>
            </div>
        ` : `
            <div class="d-flex justify-content-center align-items-center">
                <button class="btn btn-sm btn-outline-secondary py-0 px-1" style="font-size: 0.7rem; line-height:1;" onclick="gameTracker.updateStat('${player}', '${key}', -1)">-</button>
                <span class="h5 m-0 mx-2 font-weight-bold ${textClass}" id="disp-${key}-${player}">${value}</span>
                <button class="btn btn-sm btn-outline-dark py-0 px-1" style="font-size: 0.8rem; line-height:1;" onclick="gameTracker.updateStat('${player}', '${key}', 1)">+</button>
            </div>
        `;
        
        return `
            <div class="col-4 px-1">
                <div class="bg-light rounded p-1 border">
                    <div class="small text-muted font-weight-bold mb-1">${label}</div>
                    ${tovHtml}
                </div>
            </div>
        `;
    }

    updateUI(player) {
        const s = this.stats[player];

        document.getElementById(`pts-${player}`).innerText = s.points + ' PTS';
        document.getElementById(`pf-badge-${player}`).innerText = s.pf + ' PF';

        // Update +/- Badge
        const pmEl = document.getElementById(`pm-${player}`);
        if (pmEl) {
            const pmSign = s.plus_minus > 0 ? '+' : '';
            pmEl.innerText = `${pmSign}${s.plus_minus}`;

            pmEl.className = 'badge mr-1';
            if (s.plus_minus > 0) pmEl.classList.add('badge-success');
            else if (s.plus_minus < 0) pmEl.classList.add('badge-danger');
            else pmEl.classList.add('badge-secondary');
        }

        if (document.getElementById(`disp-2pt-${player}`)) {
            const two_m = s.fgm - s.tpm;
            const two_a = s.fga - s.tpa;
            document.getElementById(`disp-2pt-${player}`).innerText = `${two_m}/${two_a}`;
        }
        if (document.getElementById(`disp-3pt-${player}`)) {
            document.getElementById(`disp-3pt-${player}`).innerText = `${s.tpm}/${s.tpa}`;
        }
        if (document.getElementById(`disp-ft-${player}`)) {
            document.getElementById(`disp-ft-${player}`).innerText = `${s.ftm}/${s.fta}`;
        }

        const keys = ['oreb', 'dreb', 'ast', 'stl', 'blk', 'tov', 'pf'];
        keys.forEach(k => {
            const el = document.getElementById(`disp-${k}-${player}`);
            if (el) el.innerText = s[k];
        });

        this.updateScoreboard();
    }

    updateScoreboard() {
        let total = 0;
        Object.values(this.stats).forEach(s => total += s.points);
        document.getElementById('scoreboard').innerText = `${total} - ${this.opponentScore}`;
    }

    // --- MODALS (Assist, ShotLoc, Oreb, PlaySelector) ---

    openAssistModal(shooter, type, points) {
        this.pendingMadeShot = { shooter, type, points, assister: null, location: null };
        document.getElementById('assist-shot-label').innerText = `${shooter} ${points}PT MADE`;

        const list = document.getElementById('assist-list');
        list.innerHTML = '';

        // No assist
        const noneBtn = document.createElement('button');
        noneBtn.type = 'button';
        noneBtn.className = 'list-group-item list-group-item-action font-weight-bold';
        noneBtn.innerText = 'No assist';
        noneBtn.onclick = () => this.pickAssister(null);
        list.appendChild(noneBtn);

        // Assist options
        this.activeLineup.forEach(p => {
            if (p === shooter) return;
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'list-group-item list-group-item-action';
            btn.innerText = p;
            btn.onclick = () => this.pickAssister(p);
            list.appendChild(btn);
        });

        $('#assistModal').modal('show');
    }

    pickAssister(assister) {
        if (!this.pendingMadeShot) return;
        this.pendingMadeShot.assister = assister;
        $('#assistModal').modal('hide');
        this.openShotLocModal();
    }

    openShotLocModal() {
        if (!this.pendingMadeShot) return;
        const { shooter, points } = this.pendingMadeShot;
        document.getElementById('shotloc-player').innerText = `${shooter} (${points}PT)`;

        this.pendingMadeShot.location = null;
        document.getElementById('shotloc-coords').innerText = '(none)';
        document.getElementById('btn-confirm-shotloc').disabled = true;
        const marker = document.getElementById('shotloc-marker');
        if (marker) {
            marker.setAttribute('cx', -20);
            marker.setAttribute('cy', -20);
        }

        this.attachShotLocListenerOnce();
        $('#shotLocModal').modal('show');
    }

    openMissShotLocModal(shooter, type, points) {
        // A missed shot always has 0 points, but keep signature consistent
        this.pendingMissShot = { shooter, type, points, location: null };
        document.getElementById('shotloc-player').innerText = `${shooter} (${type.toUpperCase()} MISS)`;

        this.pendingMissShot.location = null;
        document.getElementById('shotloc-coords').innerText = '(none)';
        document.getElementById('btn-confirm-shotloc').disabled = true;
        const marker = document.getElementById('shotloc-marker');
        if (marker) {
            marker.setAttribute('cx', -20);
            marker.setAttribute('cy', -20);
        }

        this.attachShotLocListenerOnce();
        $('#shotLocModal').modal('show');
    }

    attachShotLocListenerOnce() {
        if (this.shotLocListenerAttached) return;

        const hitbox = document.getElementById(this.CONSTANTS.COURT_HITBOX_ID);
        const svg = document.getElementById(this.CONSTANTS.SVG_ID);

        if (!hitbox || !svg) return;

        hitbox.addEventListener('pointerdown', (evt) => {
            const pending = this.pendingMadeShot || this.pendingMissShot;
            if (!pending) return;
            evt.preventDefault();

            const pt = svg.createSVGPoint();
            pt.x = evt.clientX;
            pt.y = evt.clientY;
            const ctm = svg.getScreenCTM();
            if (!ctm) return;
            const cursor = pt.matrixTransform(ctm.inverse());

            let x = Math.max(0, Math.min(this.CONSTANTS.SVG_WIDTH, cursor.x));
            let y = Math.max(0, Math.min(this.CONSTANTS.SVG_HEIGHT, cursor.y));

            const loc = {
                x, y,
                nx: x / this.CONSTANTS.SVG_WIDTH,
                ny: y / this.CONSTANTS.SVG_HEIGHT
            };

            if (this.pendingMadeShot) this.pendingMadeShot.location = loc;
            if (this.pendingMissShot) this.pendingMissShot.location = loc;

            const marker = document.getElementById('shotloc-marker');
            if (marker) {
                marker.setAttribute('cx', x);
                marker.setAttribute('cy', y);
            }
            document.getElementById('shotloc-coords').innerText = `(${x.toFixed(0)}, ${y.toFixed(0)})`;
            document.getElementById('btn-confirm-shotloc').disabled = false;
        });

        this.shotLocListenerAttached = true;
    }

    skipShotLocation() {
        if (this.pendingMissShot) {
            this.pendingMissShot.location = null;
            this.confirmShotLocationFromMap(true);
            return;
        }
        if (!this.pendingMadeShot) return;
        this.pendingMadeShot.location = null;
        this.confirmShotLocationFromMap(true);
    }

    confirmShotLocationFromMap(skipped = false) {
        // Handle made shots
        if (this.pendingMadeShot) {
            const { shooter, type, points, assister, location } = this.pendingMadeShot;

            this.updateShooting(shooter, type, 1, 1);

            if (assister && this.stats[assister]) {
                this.updateStat(assister, 'ast', 1);
            }

            if (!skipped && location) {
                this.shotLocations.push({
                    shooter, type, points,
                    assister: assister || null,
                    result: 'made',
                    x: location.x, y: location.y,
                    nx: location.nx, ny: location.ny,
                    quarter: this.quarter,
                    clockSeconds: this.clockSeconds
                });
            }

            // Open play selector after made shot (only if toggle is ON)
            this.openPlaySelector('SHOT_' + type.toUpperCase(), shooter, type);

            this.pendingMadeShot = null;
            $('#shotLocModal').modal('hide');
            this.saveState();
            return;
        }

        // Handle missed shots
        if (this.pendingMissShot) {
            const { shooter, type, location } = this.pendingMissShot;

            // Count the miss as an attempt
            this.updateShooting(shooter, type, 0, 1);

            if (!skipped && location) {
                this.shotLocations.push({
                    shooter,
                    type,
                    points: 0,
                    assister: null,
                    result: 'missed',
                    x: location.x, y: location.y,
                    nx: location.nx, ny: location.ny,
                    quarter: this.quarter,
                    clockSeconds: this.clockSeconds
                });
            }

            // Open play selector after missed shot (only if toggle is ON)
            this.openPlaySelector('SHOT_' + type.toUpperCase(), shooter, type);

            this.pendingMissShot = null;
            $('#shotLocModal').modal('hide');
            this.openOrebModal(shooter, type);
            this.saveState();
        }
    }

    openOrebModal(shooter, type) {
        this.pendingOreb = { shooter, type };
        document.getElementById('oreb-shot-label').innerText = `${shooter} ${type.toUpperCase()} MISS`;
        const list = document.getElementById('oreb-list');
        list.innerHTML = '';

        const noneBtn = document.createElement('button');
        noneBtn.type = 'button';
        noneBtn.className = 'list-group-item list-group-item-action font-weight-bold';
        noneBtn.innerText = 'No offensive rebound';
        noneBtn.onclick = () => this.confirmOreb(null);
        list.appendChild(noneBtn);

        this.activeLineup.forEach(p => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'list-group-item list-group-item-action';
            btn.innerText = p;
            btn.onclick = () => this.confirmOreb(p);
            list.appendChild(btn);
        });

        $('#orebModal').modal('show');
    }

    confirmOreb(rebounder) {
        if (!this.pendingOreb) return;
        const { shooter, type } = this.pendingOreb;

        if (rebounder && this.stats[rebounder]) {
            this.updateStat(rebounder, 'oreb', 1);
        }

        this.pendingOreb = null;
        $('#orebModal').modal('hide');
        this.saveState();
    }

    // --- UPDATE LOGIC ---
    updateShooting(player, type, makeDelta, attemptDelta) {
        if (!this.stats[player]) return;
        const s = this.stats[player];
        let pointsAdded = 0;

        if (type === '2pt') {
            const current2M = s.fgm - s.tpm;
            const current2A = s.fga - s.tpa;
            if (current2M + makeDelta < 0 || current2A + attemptDelta < 0) return;
            if (current2A + attemptDelta < current2M + makeDelta) return;
            s.fgm += makeDelta;
            s.fga += attemptDelta;
            pointsAdded = (makeDelta * 2);
            s.points += pointsAdded;
        } else if (type === '3pt') {
            if (s.tpm + makeDelta < 0 || s.tpa + attemptDelta < 0) return;
            if (s.tpa + attemptDelta < s.tpm + makeDelta) return;
            s.tpm += makeDelta;
            s.tpa += attemptDelta;
            s.fgm += makeDelta;
            s.fga += attemptDelta;
            pointsAdded = (makeDelta * 3);
            s.points += pointsAdded;
        } else if (type === 'ft') {
            if (s.ftm + makeDelta < 0 || s.fta + attemptDelta < 0) return;
            if (s.fta + attemptDelta < s.ftm + makeDelta) return;
            s.ftm += makeDelta;
            s.fta += attemptDelta;
            pointsAdded = (makeDelta * 1);
            s.points += pointsAdded;
        }

        if (makeDelta !== 0) {
            this.activeLineup.forEach(pName => {
                if (this.stats[pName]) {
                    this.stats[pName].plus_minus += pointsAdded;
                }
            });
            this.activeLineup.forEach(pName => this.updateUI(pName));
        } else {
            this.updateUI(player);
        }
        this.saveState();
    }

    updateStat(player, key, delta) {
        if (!this.stats[player]) return;
        if (this.stats[player][key] + delta < 0) return;
        this.stats[player][key] += delta;
        this.updateUI(player);
        this.saveState();
    }

    logEvent(type, player = null, detail = null) {
        this.gameEvents.push({
            type,
            player,
            detail,
            quarter: this.quarter,
            clockSeconds: this.clockSeconds,
            timestamp: Date.now()
        });
    }

    updateOppScore(points) {
        this.opponentScore += points;
        if (this.opponentScore < 0) this.opponentScore = 0;
        document.getElementById('opp-score-display').innerText = this.opponentScore;

        this.logEvent('OPP_SCORE', null, { points });

        this.activeLineup.forEach(pName => {
            if (this.stats[pName]) {
                this.stats[pName].plus_minus -= points;
            }
            this.updateUI(pName);
        });
        this.updateScoreboard();
        this.saveState();
    }

    // --- CLOCK ---
    toggleClock() {
        const btn = document.getElementById('btn-start-clock');
        if (this.isClockRunning) {
            clearInterval(this.timerInterval);
            this.isClockRunning = false;
            btn.innerText = "START";
            btn.classList.remove('btn-danger');
            btn.classList.add('btn-success');
            this.updatePlayerTimes();

            // Save to cache when clock is stopped (event-based cache)
            this.addToCache(this.getCurrentState());
        } else {
            const now = Date.now();
            this.activeLineup.forEach(p => {
                this.stats[p].last_sub_in = now;
            });
            this.timerInterval = setInterval(() => {
                this.clockSeconds++;
                this.updateClockDisplay();
            }, 1000);
            this.isClockRunning = true;
            btn.innerText = "STOP";
            btn.classList.remove('btn-success');
            btn.classList.add('btn-danger');
        }
        this.saveState();
    }

    getCurrentState() {
        return {
            fullRoster: this.fullRoster,
            activeLineup: this.activeLineup,
            stats: JSON.parse(JSON.stringify(this.stats)), // deep copy
            opponentScore: this.opponentScore,
            shotLocations: JSON.parse(JSON.stringify(this.shotLocations)),
            gameEvents: JSON.parse(JSON.stringify(this.gameEvents)),
            quarter: this.quarter,
            clockSeconds: this.clockSeconds,
            gameDate: document.getElementById('game-date').value,
            opponentName: document.getElementById('opponent').value,
            gameType: document.getElementById('game-type').value
        };
    }

    updatePlayerTimes() {
        const now = Date.now();
        this.activeLineup.forEach(p => {
            if (this.stats[p].last_sub_in) {
                const diffSeconds = Math.floor((now - this.stats[p].last_sub_in) / 1000);
                this.stats[p].minutes_seconds += diffSeconds;
                this.stats[p].last_sub_in = null;
            }
            const el = document.getElementById(`time-${p}`);
            if (el) el.innerText = 'MIN: ' + this.formatMinutes(this.stats[p].minutes_seconds);
        });
    }

    resetClock() {
        if (this.isClockRunning) this.toggleClock();
        this.clockSeconds = 0;
        this.updateClockDisplay();
        this.saveState();
    }

    nextQuarter() {
        if (this.isClockRunning) this.toggleClock();
        this.quarter++;
        document.getElementById('quarter-display').innerText = 'Q' + this.quarter;
        this.clockSeconds = 0;
        this.updateClockDisplay();

        this.logEvent('NEXT_QUARTER', null, { quarter: this.quarter });

        // Cache at quarter boundaries (event-based cache)
        this.addToCache(this.getCurrentState());
        this.saveState();
    }

    updateClockDisplay() {
        const m = Math.floor(this.clockSeconds / 60);
        const s = this.clockSeconds % 60;
        document.getElementById('game-clock').innerText =
            `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    }

    // --- SUBS ---
    showSubstitutionModal() {
        if (this.isClockRunning) this.toggleClock();

        // Use a temporary list for substitution selection
        this._tempLineup = [...this.activeLineup];
        const container = document.getElementById('sub-roster-list');
        container.innerHTML = '';

        this.fullRoster.forEach(p => {
            const isActive = this._tempLineup.includes(p);
            const pmVal = this.stats[p] ? this.stats[p].plus_minus : 0;
            const pmSign = pmVal > 0 ? '+' : '';
            const pmClass = pmVal > 0 ? 'text-success' : (pmVal < 0 ? 'text-danger' : 'text-muted');

            const btn = document.createElement('button');
            btn.className = `list-group-item list-group-item-action ${isActive ? 'active' : ''}`;
            btn.style.cursor = 'pointer';
            btn.innerHTML = `<div class="d-flex justify-content-between align-items-center">
                                <span>${p} <small class="${pmClass} font-weight-bold">(${pmSign}${pmVal})</small></span>
                                <small>${isActive ? 'ON COURT' : 'BENCH'}</small>
                             </div>`;

            btn.onclick = () => {
                if (this._tempLineup.includes(p)) {
                    this._tempLineup = this._tempLineup.filter(x => x !== p);
                    btn.classList.remove('active');
                    btn.querySelector('small:last-child').innerText = 'BENCH';
                } else {
                    if (this._tempLineup.length >= 5) {
                        alert("Only 5 players allowed on court.");
                        return;
                    }
                    this._tempLineup.push(p);
                    btn.classList.add('active');
                    btn.querySelector('small:last-child').innerText = 'ON COURT';
                }
            };
            container.appendChild(btn);
        });

        $('#subModal').modal('show');
    }

    confirmSubs() {
        if (this._tempLineup.length !== 5) {
            alert("You must select exactly 5 players.");
            return;
        }

        const prevLineup = new Set(this.activeLineup);
        const newLineup = new Set(this._tempLineup);

        // Log outs and ins
        [...prevLineup].filter(p => !newLineup.has(p)).forEach(p => this.logEvent('SUB_OUT', p));
        [...newLineup].filter(p => !prevLineup.has(p)).forEach(p => this.logEvent('SUB_IN', p));

        this.activeLineup = [...this._tempLineup];
        this.renderActivePlayers();
        $('#subModal').modal('hide');

        // Cache after substitutions (event-based cache)
        this.addToCache(this.getCurrentState());
        this.saveState();
    }

    // --- FINISH ---
    formatMinutes(totalSeconds) {
        const m = Math.floor(totalSeconds / 60);
        const s = totalSeconds % 60;
        return `${m}:${s.toString().padStart(2, '0')}`;
    }

    finishGame() {
        if (!confirm("Are you sure you want to finish and save this game?")) return;

        if (this.isClockRunning) this.toggleClock();

        let total = 0;
        Object.values(this.stats).forEach(s => total += s.points);

        const finalStats = {};
        Object.keys(this.stats).forEach(p => {
            const s = this.stats[p];
            s.minutes = this.formatMinutes(s.minutes_seconds);
            finalStats[p] = s;
        });

        const payload = {
            opponent: document.getElementById('opponent').value,
            date: document.getElementById('game-date').value,
            game_type: document.getElementById('game-type').value,
            team_score: total,
            opponent_score: this.opponentScore,
            shot_locations: this.shotLocations,
            game_events: this.gameEvents,
            player_stats: finalStats
        };

        const csrfToken = document.getElementById('csrf_token').value;

        fetch('/live-game/save', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify(payload)
        }).then(res => res.json()).then(data => {
            if (data.success) {
                this.clearState();
                window.location.href = `/game/${data.game_id}`;
            } else {
                alert("Error saving game: " + (data.error || "Unknown error"));
            }
        }).catch(err => {
            alert("Network error occurred.");
            console.error(err);
        });
    }
}

// Instantiate global tracker
const gameTracker = new GameTracker();