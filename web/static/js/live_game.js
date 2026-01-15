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
        this.pendingPlaySelection = null;
        this.pendingTurnover = null;

        // **NEW: Track last added shot index for retroactive play_id assignment**
        this.lastShotIndex = null;

        // Timer State
        this.timerInterval = null;
        this.quarter = 1;
        this.quarterSeconds = 0;
        this.gameSeconds = 0;
        this.isClockRunning = false;

        // Auto-cache timer
        this.autoCacheInterval = null;
        this.lastCacheTimestamp = 0;

        // UI Helpers
        this.shotLocListenerAttached = false;

        // Plays cache
        this.playsCache = [];
        this.playTypes = [];
        this.recentPlays = [];
        this.showSpecial = false;

        // Play selector toggle state
        this.playSelectMode = true;

        // Constants
        this.CONSTANTS = {
            SVG_WIDTH: 500,
            SVG_HEIGHT: 470,
            COURT_HITBOX_ID: 'court-hitbox',
            SVG_ID: 'halfCourtSvg',
            STORAGE_KEY: 'basketball_live_game_state',
            CACHE_KEY: 'basketball_live_game_cache',
            MAX_CACHED_GAMES: 3,
            AUTO_CACHE_INTERVAL_MS: 30000,
            MAX_RECENT_PLAYS: 3
        };

        this.init();
    }

    init() {
        this.loadState();
        this.bindEvents();
        this.renderCachedGamesUI();
        this.loadPlays();

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

            this.startAutoCacheTimer();
        }
    }

    bindEvents() {
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
        // Always attempt fetch from API first to get fresh data (IDs)
        const csrfToken = document.getElementById('csrf_token')?.value || '';
        
        console.log("Fetching fresh plays from API...");
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
        .catch(err => {
            console.error('Failed to load plays from API, falling back to injected data:', err);
            // Fallback to injected data if API fails
            if (window.AVAILABLE_PLAYS && window.AVAILABLE_PLAYS.length > 0) {
                console.log("Using injected plays data as fallback.");
                this.playsCache = window.AVAILABLE_PLAYS;
                this.processPlayTypes();
            }
        });
    }

    processPlayTypes() {
        const types = [...new Set(this.playsCache.map(p => p.type))];
        this.playTypes = types.sort();
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
        this.renderPlaysList();
    }

    addToRecentPlays(play) {
        this.recentPlays = this.recentPlays.filter(p => p.id !== play.id);
        this.recentPlays.unshift(play);
        this.recentPlays = this.recentPlays.slice(0, this.CONSTANTS.MAX_RECENT_PLAYS);
    }

    renderPlaysList() {
        const container = document.getElementById('plays-list');
        if (!container) return;

        let targetType = 'Offense';
        if (this.showSpecial) {
            targetType = 'Special';
        }

        let filteredPlays = this.playsCache.filter(p => p.type === targetType);
        
        const macroMap = new Map();

        filteredPlays.forEach(play => {
            const parts = play.name.split('-');
            let macroName = play.name;
            
            if (parts.length > 1) {
                macroName = parts[0].trim();
            }

            if (!macroMap.has(macroName)) {
                macroMap.set(macroName, []);
            }
            macroMap.get(macroName).push(play);
        });

        container.innerHTML = '';

        if (filteredPlays.length === 0) {
            container.innerHTML = '<div class="text-muted text-center p-4">No ' + targetType + ' plays found</div>';
            return;
        }

        // Recent plays section (cards)
        if (targetType === 'Offense' && this.recentPlays.length > 0) {
            const recentHeader = document.createElement('div');
            recentHeader.className = 'px-3 py-2 bg-light border-bottom';
            recentHeader.innerHTML = '<small class="text-primary font-weight-bold"><i class="fas fa-history"></i> RECENT</small>';
            container.appendChild(recentHeader);

            const recentGrid = document.createElement('div');
            recentGrid.className = 'row no-gutters p-2';
            
            this.recentPlays.forEach(play => {
                const card = this.createPlayCard(play, false, true);
                recentGrid.appendChild(card);
            });
            
            container.appendChild(recentGrid);
            
            const divider = document.createElement('div');
            divider.className = 'px-3 py-2 bg-light border-top border-bottom';
            divider.innerHTML = '<small class="text-secondary font-weight-bold"><i class="fas fa-list"></i> ALL PLAYS</small>';
            container.appendChild(divider);
        }

        // All plays section (cards grid)
        const playsGrid = document.createElement('div');
        playsGrid.className = 'row no-gutters p-2';

        const macros = Array.from(macroMap.entries()).sort((a, b) => a[0].localeCompare(b[0]));

        macros.forEach(([name, variations]) => {
            if (variations.length === 1) {
                playsGrid.appendChild(this.createPlayCard(variations[0], false, false));
            } else {
                playsGrid.appendChild(this.createPlayCard(variations[0], true, false, name));
            }
        });

        container.appendChild(playsGrid);
    }

    createPlayCard(play, isMacro = false, isRecent = false, customLabel = null) {
        const col = document.createElement('div');
        col.className = 'col-6 col-sm-4 col-md-3 p-1';
        
        const displayName = customLabel || play.name;
        
        const card = document.createElement('div');
        card.className = 'card h-100 shadow-sm border-0';
        card.style.cursor = 'pointer';
        card.style.transition = 'all 0.15s';
        
        // Add hover effect
        card.onmouseenter = () => {
            card.style.transform = 'translateY(-2px)';
            card.style.boxShadow = '0 4px 8px rgba(0,0,0,0.2)';
        };
        card.onmouseleave = () => {
            card.style.transform = 'translateY(0)';
            card.style.boxShadow = '';
        };
        
        // Apply colors based on type
        let headerClass = 'bg-primary text-white';
        if (isRecent) {
            headerClass = 'bg-info text-white';
        } else if (isMacro) {
            headerClass = 'bg-secondary text-white';
        }
        
        card.innerHTML = `
            <div class="card-header ${headerClass} py-2 px-2 text-center">
                <div class="font-weight-bold" style="font-size: 0.9rem; line-height: 1.2;">${displayName}</div>
                ${isMacro ? '<small class="badge badge-light mt-1" style="font-size: 0.65rem;"><i class="fas fa-layer-group"></i> Group</small>' : ''}
                ${isRecent ? '<small class="badge badge-light mt-1" style="font-size: 0.65rem;"><i class="fas fa-star"></i></small>' : ''}
            </div>
            <div class="card-body p-2 d-flex align-items-center justify-content-center" style="min-height: 50px;">
                <i class="fas fa-basketball-ball text-muted" style="font-size: 1.5rem; opacity: 0.3;"></i>
            </div>
        `;
        
        card.onclick = () => this.selectPlay(play);
        
        col.appendChild(card);
        return col;
    }

    openPlaySelector(eventType, shooter = null, shotType = null) {
        if (!this.playSelectMode) {
            this.finalizePlaySelection(null);
            return;
        }

        this.pendingPlaySelection = {
            eventType,
            shooter,
            shotType
        };

        this.showSpecial = false;
        this.updateSpecialToggleBtn();

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

    // **FIX: Retroactively update shot's play_id**
    selectPlay(play) {
        if (!this.pendingPlaySelection && !this.pendingTurnover) {
            $('#playSelectorModal').modal('hide');
            return;
        }

        console.log(`Play selected: ID ${play.id} (${play.name})`);

        // **CRITICAL FIX: Update the last shot's play_id retroactively**
        if (this.lastShotIndex !== null && this.lastShotIndex < this.shotLocations.length) {
            this.shotLocations[this.lastShotIndex].play_id = play.id;
            console.log(`Updated shot at index ${this.lastShotIndex} with play_id ${play.id}`);
            this.lastShotIndex = null; // Clear after use
        }

        this.addToRecentPlays(play);
        this.finalizePlaySelection(play);
        $('#playSelectorModal').modal('hide');
    }

    skipPlaySelection() {
        // **FIX: Clear pending shot index if skipped**
        this.lastShotIndex = null;
        this.finalizePlaySelection(null);
        $('#playSelectorModal').modal('hide');
    }

    finalizePlaySelection(play) {
        if (this.pendingTurnover) {
            const { player } = this.pendingTurnover;
            
            this.updateStat(player, 'tov', 1);

            const event = {
                type: 'TURNOVER',
                player: player,
                detail: play ? {
                    play_id: play.id,
                    play_name: play.name
                } : null,
                quarter: this.quarter,
                clockSeconds: this.quarterSeconds,
                timestamp: Date.now(),
                play_id: play ? play.id : null
            };
            this.gameEvents.push(event);

            this.pendingTurnover = null;
            this.saveState();
            return;
        }

        if (this.pendingPlaySelection) {
            const { eventType, shooter } = this.pendingPlaySelection;

            if (play) {
                const event = {
                    type: eventType,
                    player: shooter,
                    detail: {
                        play_id: play.id,
                        play_name: play.name
                    },
                    quarter: this.quarter,
                    clockSeconds: this.quarterSeconds,
                    timestamp: Date.now(),
                    play_id: play.id
                };
                this.gameEvents.push(event);
            }

            this.pendingPlaySelection = null;
            this.saveState();
        }
    }

    recordTurnover(player) {
        this.pendingTurnover = { player };
        
        if (this.playSelectMode) {
            this.openPlaySelector('TURNOVER', player);
        } else {
            this.finalizePlaySelection(null);
        }
    }

    // --- AUTO-CACHE TIMER ---
    startAutoCacheTimer() {
        if (this.autoCacheInterval) {
            clearInterval(this.autoCacheInterval);
        }

        this.autoCacheInterval = setInterval(() => {
            const now = Date.now();
            const timeSinceLastCache = now - this.lastCacheTimestamp;

            if (timeSinceLastCache >= this.CONSTANTS.AUTO_CACHE_INTERVAL_MS) {
                this.addToCache(this.getCurrentState(), true);
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

        const snapshot = {
            ...state,
            timestamp: Date.now(),
            id: Date.now() + Math.random()
        };

        this.lastCacheTimestamp = snapshot.timestamp;

        cache.unshift(snapshot);

        const trimmed = cache.slice(0, this.CONSTANTS.MAX_CACHED_GAMES);

        localStorage.setItem(this.CONSTANTS.CACHE_KEY, JSON.stringify(trimmed));
        this.renderCachedGamesUI();

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

        this.fullRoster = snapshot.fullRoster || [];
        this.activeLineup = snapshot.activeLineup || [];
        this.stats = snapshot.stats || {};
        this.opponentScore = snapshot.opponentScore || 0;
        this.shotLocations = snapshot.shotLocations || [];
        this.gameEvents = snapshot.gameEvents || [];
        this.quarter = snapshot.quarter || 1;
        this.quarterSeconds = snapshot.quarterSeconds || 0;
        this.gameSeconds = snapshot.gameSeconds || 0;

        if (snapshot.gameDate) document.getElementById('game-date').value = snapshot.gameDate;
        if (snapshot.opponentName) document.getElementById('opponent').value = snapshot.opponentName;
        if (snapshot.gameType) document.getElementById('game-type').value = snapshot.gameType;

        this.saveState();

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
            quarterSeconds: this.quarterSeconds,
            gameSeconds: this.gameSeconds,
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
                this.quarterSeconds = state.quarterSeconds || 0;
                this.gameSeconds = state.gameSeconds || 0;

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
                this.saveState();
            };
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
        
        // **NEW: Ensure latest plays are loaded when game starts**
        this.loadPlays();

        if (Object.keys(this.stats).length === 0) {
            this.fullRoster.forEach(p => {
                this.stats[p] = {
                    points: 0, fgm: 0, fga: 0, tpm: 0, tpa: 0, ftm: 0, fta: 0,
                    oreb: 0, dreb: 0, ast: 0, tov: 0, stl: 0, blk: 0, pf: 0,
                    plus_minus: 0,
                    minutes_seconds: 0,
                    quarter_minutes: {1: 0, 2: 0, 3: 0, 4: 0},
                    last_sub_in: this.activeLineup.includes(p) ? Date.now() : null
                };
            });
        } else {
            this.activeLineup.forEach(p => {
                if (!this.stats[p].last_sub_in) this.stats[p].last_sub_in = Date.now();
                // Initialize quarter_minutes if missing (for backward compatibility)
                if (!this.stats[p].quarter_minutes) {
                    this.stats[p].quarter_minutes = {1: 0, 2: 0, 3: 0, 4: 0};
                }
            });
        }

        document.getElementById('lineup-panel').style.display = 'none';
        document.getElementById('tracker-panel').style.display = 'block';
        document.getElementById('display-opponent').innerText = "vs " + opponent;

        this.renderActivePlayers();
        this.saveState();

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

            // Calculate display minutes (total)
            let displayedSeconds = s.minutes_seconds;
            if (this.isClockRunning && s.last_sub_in) {
                const diffSeconds = Math.floor((Date.now() - s.last_sub_in) / 1000);
                displayedSeconds += diffSeconds;
            }

            // Calculate quarter minutes for display
            let quarterMins = s.quarter_minutes || {1: 0, 2: 0, 3: 0, 4: 0};
            let displayedQuarterSeconds = quarterMins[this.quarter] || 0;
            if (this.isClockRunning && s.last_sub_in) {
                const diffSeconds = Math.floor((Date.now() - s.last_sub_in) / 1000);
                displayedQuarterSeconds += diffSeconds;
            }

            // Generate quarter breakdown HTML
            let quarterBreakdown = '';
            for (let q = 1; q <= 4; q++) {
                const qMins = quarterMins[q] || 0;
                const isCurrentQ = (q === this.quarter);
                const displayQ = isCurrentQ ? displayedQuarterSeconds : qMins;
                const qClass = isCurrentQ ? 'text-primary font-weight-bold' : 'text-muted';
                quarterBreakdown += `<span class="${qClass} mx-1" style="font-size: 0.75rem;">Q${q}: ${this.formatMinutes(displayQ)}</span>`;
            }

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

                            <!-- MINUTES DISPLAY -->
                            <div class="mt-2 text-center small">
                                <div class="font-weight-bold mb-1" id="time-${p}">TOTAL: ${this.formatMinutes(displayedSeconds)}</div>
                                <div class="d-flex justify-content-center flex-wrap" id="quarter-time-${p}">
                                    ${quarterBreakdown}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        });
    }

    renderStatBox(player, label, key, value, textClass = '', isToV = false) {
        const tovHtml = isToV ? `
            <div class="d-flex justify-content-center align-items-center">
                <button class="btn btn-sm btn-secondary py-1 px-2 mx-1" style="font-size: 0.95rem; min-width: 36px;" onclick="gameTracker.updateStat('${player}', '${key}', -1)">−</button>
                <span class="h5 m-0 mx-2 font-weight-bold ${textClass}" id="disp-${key}-${player}">${value}</span>
                <button class="btn btn-sm btn-danger py-1 px-2 mx-1 font-weight-bold" style="font-size: 1rem; min-width: 36px;" onclick="gameTracker.recordTurnover('${player}')">+</button>
            </div>
        ` : `
            <div class="d-flex justify-content-center align-items-center">
                <button class="btn btn-sm btn-secondary py-1 px-2 mx-1" style="font-size: 0.95rem; min-width: 36px;" onclick="gameTracker.updateStat('${player}', '${key}', -1)">−</button>
                <span class="h5 m-0 mx-2 font-weight-bold ${textClass}" id="disp-${key}-${player}">${value}</span>
                <button class="btn btn-sm btn-dark py-1 px-2 mx-1" style="font-size: 0.95rem; min-width: 36px;" onclick="gameTracker.updateStat('${player}', '${key}', 1)">+</button>
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

    // --- MODALS ---

    openAssistModal(shooter, type, points) {
        this.pendingMadeShot = { shooter, type, points, assister: null, location: null };
        document.getElementById('assist-shot-label').innerText = `${shooter} ${points}PT MADE`;

        const list = document.getElementById('assist-list');
        list.innerHTML = '';

        const noneBtn = document.createElement('button');
        noneBtn.type = 'button';
        noneBtn.className = 'list-group-item list-group-item-action font-weight-bold';
        noneBtn.innerText = 'No assist';
        noneBtn.onclick = () => this.pickAssister(null);
        list.appendChild(noneBtn);

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
        if (this.pendingMadeShot) {
            const { shooter, type, points, assister, location } = this.pendingMadeShot;

            this.updateShooting(shooter, type, 1, 1);

            if (assister && this.stats[assister]) {
                this.updateStat(assister, 'ast', 1);
            }

            if (!skipped && location) {
                // **FIX: Push shot WITHOUT play_id, store index for later update**
                this.shotLocations.push({
                    shooter, type, points,
                    assister: assister || null,
                    result: 'made',
                    x: location.x, y: location.y,
                    nx: location.nx, ny: location.ny,
                    quarter: this.quarter,
                    clockSeconds: this.quarterSeconds,
                    timestamp: Date.now(),
                    play_id: null  // Will be updated after play selection
                });
                
                // Store the index of this shot for retroactive play_id update
                this.lastShotIndex = this.shotLocations.length - 1;
                console.log(`Shot added at index ${this.lastShotIndex}, awaiting play selection`);
            }

            this.openPlaySelector('SHOT_' + type.toUpperCase(), shooter, type);

            this.pendingMadeShot = null;
            $('#shotLocModal').modal('hide');
            this.saveState();
            return;
        }

        if (this.pendingMissShot) {
            const { shooter, type, location } = this.pendingMissShot;

            this.updateShooting(shooter, type, 0, 1);

            if (!skipped && location) {
                // **FIX: Push shot WITHOUT play_id, store index for later update**
                this.shotLocations.push({
                    shooter,
                    type,
                    points: 0,
                    assister: null,
                    result: 'missed',
                    x: location.x, y: location.y,
                    nx: location.nx, ny: location.ny,
                    quarter: this.quarter,
                    clockSeconds: this.quarterSeconds,
                    timestamp: Date.now(),
                    play_id: null  // Will be updated after play selection
                });
                
                // Store the index of this shot for retroactive play_id update
                this.lastShotIndex = this.shotLocations.length - 1;
                console.log(`Shot added at index ${this.lastShotIndex}, awaiting play selection`);
            }

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
            clockSeconds: this.quarterSeconds,
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
            
            this.commitPlayerTimes();

            this.addToCache(this.getCurrentState());
        } else {
            const now = Date.now();
            this.activeLineup.forEach(p => {
                this.stats[p].last_sub_in = now;
            });
            
            this.timerInterval = setInterval(() => {
                this.quarterSeconds++;
                this.gameSeconds++;
                this.updateClockDisplay();
                this.updatePlayerTimeDisplays();
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
            stats: JSON.parse(JSON.stringify(this.stats)),
            opponentScore: this.opponentScore,
            shotLocations: JSON.parse(JSON.stringify(this.shotLocations)),
            gameEvents: JSON.parse(JSON.stringify(this.gameEvents)),
            quarter: this.quarter,
            quarterSeconds: this.quarterSeconds,
            gameSeconds: this.gameSeconds,
            gameDate: document.getElementById('game-date').value,
            opponentName: document.getElementById('opponent').value,
            gameType: document.getElementById('game-type').value
        };
    }

    updatePlayerTimeDisplays() {
        const now = Date.now();
        this.activeLineup.forEach(p => {
            if (this.stats[p].last_sub_in) {
                const diffSeconds = Math.floor((now - this.stats[p].last_sub_in) / 1000);
                const totalDisplayed = this.stats[p].minutes_seconds + diffSeconds;
                
                const el = document.getElementById(`time-${p}`);
                if (el) el.innerText = 'TOTAL: ' + this.formatMinutes(totalDisplayed);

                // Update quarter time display
                const quarterMins = this.stats[p].quarter_minutes || {1: 0, 2: 0, 3: 0, 4: 0};
                const quarterDisplayed = (quarterMins[this.quarter] || 0) + diffSeconds;
                
                const qEl = document.getElementById(`quarter-time-${p}`);
                if (qEl) {
                    let quarterBreakdown = '';
                    for (let q = 1; q <= 4; q++) {
                        const qMins = quarterMins[q] || 0;
                        const isCurrentQ = (q === this.quarter);
                        const displayQ = isCurrentQ ? quarterDisplayed : qMins;
                        const qClass = isCurrentQ ? 'text-primary font-weight-bold' : 'text-muted';
                        quarterBreakdown += `<span class=\"${qClass} mx-1\" style=\"font-size: 0.75rem;\">Q${q}: ${this.formatMinutes(displayQ)}</span>`;
                    }
                    qEl.innerHTML = quarterBreakdown;
                }
            }
        });
    }

    commitPlayerTimes() {
        const now = Date.now();
        this.activeLineup.forEach(p => {
            if (this.stats[p].last_sub_in) {
                const diffSeconds = Math.floor((now - this.stats[p].last_sub_in) / 1000);
                this.stats[p].minutes_seconds += diffSeconds;
                
                // Update quarter-specific minutes
                if (!this.stats[p].quarter_minutes) {
                    this.stats[p].quarter_minutes = {1: 0, 2: 0, 3: 0, 4: 0};
                }
                this.stats[p].quarter_minutes[this.quarter] = (this.stats[p].quarter_minutes[this.quarter] || 0) + diffSeconds;
                
                this.stats[p].last_sub_in = null;
            }
            // Update UI with finalized time
            const el = document.getElementById(`time-${p}`);
            if (el) el.innerText = 'TOTAL: ' + this.formatMinutes(this.stats[p].minutes_seconds);
        });
    }

    updatePlayerTimes() {
        this.commitPlayerTimes();
    }

    resetClock() {
        if (this.isClockRunning) this.toggleClock();
        this.quarterSeconds = 0;
        this.updateClockDisplay();
        this.saveState();
    }

    nextQuarter() {
        if (this.isClockRunning) this.toggleClock();
        this.quarter++;
        document.getElementById('quarter-display').innerText = 'Q' + this.quarter;
        this.quarterSeconds = 0;
        this.updateClockDisplay();

        this.logEvent('NEXT_QUARTER', null, { quarter: this.quarter });

        this.addToCache(this.getCurrentState());
        this.saveState();
    }

    updateClockDisplay() {
        const gm = Math.floor(this.gameSeconds / 60);
        const gs = this.gameSeconds % 60;
        document.getElementById('game-clock').innerText =
            `${gm.toString().padStart(2, '0')}:${gs.toString().padStart(2, '0')}`;

        const qEl = document.getElementById('quarter-clock');
        if (qEl) {
            const qm = Math.floor(this.quarterSeconds / 60);
            const qs = this.quarterSeconds % 60;
            qEl.innerText = `${qm.toString().padStart(2, '0')}:${qs.toString().padStart(2, '0')}`;
        }
    }

    // --- SUBS ---
    showSubstitutionModal() {
        if (this.isClockRunning) this.toggleClock();

        this._tempLineup = [...this.activeLineup];
        const container = document.getElementById('sub-roster-list');
        container.innerHTML = '';

        const now = Date.now();

        this.fullRoster.forEach(p => {
            const isActive = this._tempLineup.includes(p);
            const pmVal = this.stats[p] ? this.stats[p].plus_minus : 0;
            const pmSign = pmVal > 0 ? '+' : '';
            const pmClass = pmVal > 0 ? 'text-success' : (pmVal < 0 ? 'text-danger' : 'text-muted');

            // Calculate total minutes displayed
            let totalDisplayedSeconds = this.stats[p].minutes_seconds || 0;
            if (isActive && this.stats[p].last_sub_in) {
                const diffSeconds = Math.floor((now - this.stats[p].last_sub_in) / 1000);
                totalDisplayedSeconds += diffSeconds;
            }

            // Calculate current quarter minutes displayed
            const quarterMins = this.stats[p].quarter_minutes || {1: 0, 2: 0, 3: 0, 4: 0};
            let quarterDisplayedSeconds = quarterMins[this.quarter] || 0;
            if (isActive && this.stats[p].last_sub_in) {
                const diffSeconds = Math.floor((now - this.stats[p].last_sub_in) / 1000);
                quarterDisplayedSeconds += diffSeconds;
            }

            const totalTimeStr = this.formatMinutes(totalDisplayedSeconds);
            const quarterTimeStr = this.formatMinutes(quarterDisplayedSeconds);

            const btn = document.createElement('button');
            btn.className = `list-group-item list-group-item-action ${isActive ? 'active' : ''}`;
            btn.style.cursor = 'pointer';
            btn.innerHTML = `<div class="d-flex justify-content-between align-items-center">
                                <div class="flex-grow-1">
                                    <span>${p} <small class="${pmClass} font-weight-bold">(${pmSign}${pmVal})</small></span>
                                    <div style="font-size: 0.85rem; margin-top: 4px;">
                                        <span class="text-muted">Total: ${totalTimeStr}</span>
                                        <span class="text-primary font-weight-bold mx-2">Q${this.quarter}: ${quarterTimeStr}</span>
                                    </div>
                                </div>
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

        [...prevLineup].filter(p => !newLineup.has(p)).forEach(p => this.logEvent('SUB_OUT', p));
        [...newLineup].filter(p => !prevLineup.has(p)).forEach(p => this.logEvent('SUB_IN', p));

        this.activeLineup = [...this._tempLineup];
        this.renderActivePlayers();
        $('#subModal').modal('hide');

        this.addToCache(this.getCurrentState());
        this.saveState();
    }

    // --- STATS VIEW ---
    showCurrentStats() {
        const tbody = document.getElementById('current-stats-table-body');
        const tfoot = document.getElementById('current-stats-table-footer');
        if (!tbody || !tfoot) return;

        tbody.innerHTML = '';
        tfoot.innerHTML = '';

        // Convert stats object to array for sorting
        // Filter out players with no minutes/stats if desired, or show all roster
        const players = Object.keys(this.stats).map(name => {
            const s = this.stats[name];
            return { name, ...s, total_reb: s.oreb + s.dreb };
        });

        // Sort: Active players first, then by Points descending
        players.sort((a, b) => {
            const aActive = this.activeLineup.includes(a.name) ? 1 : 0;
            const bActive = this.activeLineup.includes(b.name) ? 1 : 0;
            if (aActive !== bActive) return bActive - aActive;
            return b.points - a.points;
        });

        let team = {
            points: 0, reb: 0, oreb: 0, dreb: 0, ast: 0, stl: 0, blk: 0, tov: 0, pf: 0,
            fgm: 0, fga: 0, tpm: 0, tpa: 0, ftm: 0, fta: 0
        };

        players.forEach(p => {
            // Accumulate Team Totals
            team.points += p.points;
            team.reb += p.total_reb;
            team.oreb += p.oreb;
            team.dreb += p.dreb;
            team.ast += p.ast;
            team.stl += p.stl;
            team.blk += p.blk;
            team.tov += p.tov;
            team.pf += p.pf;
            team.fgm += p.fgm;
            team.fga += p.fga;
            team.tpm += p.tpm;
            team.tpa += p.tpa;
            team.ftm += p.ftm;
            team.fta += p.fta;

            const row = document.createElement('tr');
            const isActive = this.activeLineup.includes(p.name);
            
            // Highlight active players gently
            if (isActive) row.classList.add('table-primary');

            // Format percentages
            const fgPct = p.fga > 0 ? Math.round((p.fgm / p.fga) * 100) : 0;
            const tpPct = p.tpa > 0 ? Math.round((p.tpm / p.tpa) * 100) : 0;
            const ftPct = p.fta > 0 ? Math.round((p.ftm / p.fta) * 100) : 0;
            
            // PM Color
            const pmClass = p.plus_minus > 0 ? 'text-success' : (p.plus_minus < 0 ? 'text-danger' : 'text-muted');
            const pmSign = p.plus_minus > 0 ? '+' : '';

            row.innerHTML = `
                <td class="text-left text-nowrap font-weight-bold">
                    ${p.name} 
                    ${isActive ? '<span class="badge badge-success ml-1" style="font-size:0.6em">ON</span>' : ''}
                </td>
                <td class="font-weight-bold border-left">${p.points}</td>
                <td>${p.total_reb} <small class="text-muted">(${p.oreb}/${p.dreb})</small></td>
                <td>${p.ast}</td>
                <td>${p.stl}</td>
                <td>${p.blk}</td>
                <td>${p.tov}</td>
                <td class="${p.pf >= 3 ? 'text-danger font-weight-bold' : ''}">${p.pf}</td>
                <td class="border-left text-nowrap">${p.fgm}/${p.fga} <small class="text-muted">${fgPct}%</small></td>
                <td class="text-nowrap">${p.tpm}/${p.tpa} <small class="text-muted">${tpPct}%</small></td>
                <td class="text-nowrap">${p.ftm}/${p.fta} <small class="text-muted">${ftPct}%</small></td>
                <td class="${pmClass} font-weight-bold border-left">${pmSign}${p.plus_minus}</td>
            `;
            tbody.appendChild(row);
        });

        // Render Footer (Team Totals)
        const teamFgPct = team.fga > 0 ? Math.round((team.fgm / team.fga) * 100) : 0;
        const teamTpPct = team.tpa > 0 ? Math.round((team.tpm / team.tpa) * 100) : 0;
        const teamFtPct = team.fta > 0 ? Math.round((team.ftm / team.fta) * 100) : 0;

        tfoot.innerHTML = `
            <tr>
                <td class="text-left text-uppercase">Team Total</td>
                <td class="border-left">${team.points}</td>
                <td>${team.reb} <small class="text-muted">(${team.oreb}/${team.dreb})</small></td>
                <td>${team.ast}</td>
                <td>${team.stl}</td>
                <td>${team.blk}</td>
                <td>${team.tov}</td>
                <td>${team.pf}</td>
                <td class="border-left">${team.fgm}/${team.fga} <small class="text-muted">${teamFgPct}%</small></td>
                <td>${team.tpm}/${team.tpa} <small class="text-muted">${teamTpPct}%</small></td>
                <td>${team.ftm}/${team.fta} <small class="text-muted">${teamFtPct}%</small></td>
                <td class="border-left">-</td>
            </tr>
        `;

        $('#currentStatsModal').modal('show');
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
                alert("Error saving game: " + (data.error || "Unknown error") + (data.details ? ` (${data.details})` : ''));
            }
        }).catch(err => {
            alert("Network error occurred.");
            console.error(err);
        });
    }
}

const gameTracker = new GameTracker();