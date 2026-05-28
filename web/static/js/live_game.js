class GameTracker {
    constructor() {
        this.fullRoster = [];
        this.activeLineup = [];
        this.stats = {};
        this.opponentScore = 0;
        this.shotLocations = [];
        this.gameEvents = [];
        this.lineupHistory = [];
        this.startingLineup = [];
        this.oppRecentActions = [];

        // ===========================================
        // FORMAT VERSION & FEATURE FLAGS
        // ===========================================
        // Schema version for backwards compatibility during post-processing
        // Version history:
        //   v1 - Original format (no lineup tracking, no opponent shot location)
        //   v2 - Added lineup tracking (lineupHistory, startingLineup, event.active_lineup)
        //   v3 - Added opponent shot location tracking, remove action feature
        //   v4 - Added lineup_segment_id linking, full court tracking
        //   v5 - Added TECHNICAL_FOUL and FLAGRANT_FOUL event types
        this.SCHEMA_VERSION = 5;

        // Feature flags - indicate which features are enabled/tracked
        this.FEATURES = {
            LINEUP_TRACKING: true,          // Tracks lineupHistory, startingLineup, event.active_lineup
            OPPONENT_SHOT_LOCATION: true,   // Tracks opponent shot locations on court
            OPPONENT_ACTION_REMOVAL: true,  // Allows removing opponent actions
            EVENT_INDEXING: true,           // Events have event_index field
            SEGMENT_LINKING: true,          // Events can be linked to lineup segments
            POSSESSION_TRACKING: true,      // Tracks possession_number on events
            TIMELINE_FIELDS: true,          // Events have quarter, time_remaining, game_seconds, score_margin
            FOUL_TYPES: true                // Tracks TECHNICAL_FOUL and FLAGRANT_FOUL event types
        };
        // ===========================================

        // Pending actions
        this.pendingMadeShot = null;
        this.pendingOreb = null;
        this.pendingMissShot = null;
        this.pendingPlaySelection = null;
        this.pendingTurnover = null;

        // **NEW: Track last added shot index for retroactive play_id assignment**
        this.lastShotIndex = null;

        // **NEW: FT Trip tracking**
        this.pendingFTTrip = null;  // { player, totalFt, ftm: 0 }

        // **NEW: Opponent shot tracking**
        this.pendingOppShot = null;  // { type: '2pt'|'3pt'|'ft', points: 2|3|1 }

        // **NEW: Possession tracking**
        this.possessionNumber = 0;
        this.lastPossessionTeam = null;

        // **NEW: Quarter length constant (10 minutes)**
        this.QUARTER_LENGTH_SECONDS = 600;

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
        this.oppShotLocListenerAttached = false;

        // Plays cache
        this.playsCache = [];
        this.playTypes = [];
        this.recentPlays = [];
        this.showSpecial = false;

        // Play selector toggle state
        this.playSelectMode = true;
        this.shotPositionMode = true;

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
        const restored = this.loadState();
        this.initRosterSelection();  // Initialize roster event delegation
        this.initLineupSelection();  // Initialize lineup event delegation
        this.bindEvents();
        this.renderCachedGamesUI();
        this.loadPlays();
        this.updateShotPositionToggleUI();

        if (restored && Object.keys(this.stats).length > 0) {
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
        document.addEventListener('fullscreenchange', () => this.updateFullscreenToggleUI());
        this.updateFullscreenToggleUI();
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


    toggleShotPosition() {
        this.shotPositionMode = !this.shotPositionMode;
        this.updateShotPositionToggleUI();
        this.saveState();
    }


    async toggleFullscreen() {
        const fullscreenRoot = document.getElementById('live-game-shell');
        if (!fullscreenRoot) return;

        try {
            if (document.fullscreenElement === fullscreenRoot) {
                await document.exitFullscreen();
            } else {
                await fullscreenRoot.requestFullscreen();
            }
        } catch (error) {
            console.error('Fullscreen toggle failed:', error);
        } finally {
            this.updateFullscreenToggleUI();
        }
    }


    updateFullscreenToggleUI() {
        const btn = document.getElementById('btn-fullscreen-toggle');
        const label = document.getElementById('fullscreen-toggle-label');
        if (!btn || !label) return;

        const fullscreenRoot = document.getElementById('live-game-shell');
        const isFullscreen = !!fullscreenRoot && document.fullscreenElement === fullscreenRoot;
        const icon = btn.querySelector('i');

        if (icon) {
            icon.className = isFullscreen ? 'fas fa-compress-alt' : 'fas fa-expand-alt';
        }

        label.textContent = isFullscreen ? 'Exit' : 'Full';
    }


    updateShotPositionToggleUI() {
        const btn = document.getElementById('btn-shot-position');
        const status = document.getElementById('shot-position-status');
        if (!btn || !status) return;

        if (this.shotPositionMode) {
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
    }


    // --- TOOLS & SETTINGS ---
    showSettingsModal() {
        $('#settingsModal').modal('show');
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


        if (this.pendingFTTrip) {
            this.confirmFTPlaySelection(play);
            this.pendingPlaySelection = null;
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


    recordTechFoul(player) {
        this.updateStat(player, 'pf', 1);
        this.logEvent('TECHNICAL_FOUL', player);
        this.saveState();
    }


    recordFlagrantFoul(player) {
        this.updateStat(player, 'pf', 1);
        this.logEvent('FLAGRANT_FOUL', player);
        this.saveState();
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
        this.lineupHistory = snapshot.lineupHistory || [];
        this.startingLineup = snapshot.startingLineup || [];
        this.playSelectMode = snapshot.playSelectMode !== false;
        this.shotPositionMode = snapshot.shotPositionMode !== false;

        if (snapshot.gameDate) document.getElementById('game-date').value = snapshot.gameDate;
        if (snapshot.opponentName) document.getElementById('opponent').value = snapshot.opponentName;
        if (snapshot.gameType) document.getElementById('game-type').value = snapshot.gameType;
        this.updateShotPositionToggleUI();

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
            schema_version: this.SCHEMA_VERSION,
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
            gameType: document.getElementById('game-type').value,
            lineupHistory: this.lineupHistory,
            startingLineup: this.startingLineup,
            oppRecentActions: this.oppRecentActions,
            playSelectMode: this.playSelectMode,
            shotPositionMode: this.shotPositionMode
        };
        localStorage.setItem(this.CONSTANTS.STORAGE_KEY, JSON.stringify(state));
    }


    loadState() {
        const stored = localStorage.getItem(this.CONSTANTS.STORAGE_KEY);
        if (!stored) return false;
        try {
            const state = JSON.parse(stored);
            const hasProgress = state && state.stats && Object.keys(state.stats).length > 0;
            if (hasProgress) {
                const oppName = state.opponentName || 'Unknown';
                const when = state.gameDate ? ` on ${state.gameDate}` : '';
                const resume = confirm(`Resume saved live game vs ${oppName}${when}? Click Cancel to start a new game.`);
                if (!resume) {
                    localStorage.removeItem(this.CONSTANTS.STORAGE_KEY);
                    return false;
                }
            }

            const savedVersion = state.schema_version || 1;

            if (savedVersion < 2) {
                this.lineupHistory = [];
                this.startingLineup = [];
            } else {
                this.lineupHistory = state.lineupHistory || [];
                this.startingLineup = state.startingLineup || [];
            }

            if (savedVersion < 3) {
                this.oppRecentActions = [];
            } else {
                this.oppRecentActions = state.oppRecentActions || [];
            }

            this.fullRoster = state.fullRoster || [];
            this.activeLineup = state.activeLineup || [];
            this.stats = state.stats || {};
            this.opponentScore = state.opponentScore || 0;
            this.shotLocations = state.shotLocations || [];
            this.gameEvents = state.gameEvents || [];
            this.quarter = state.quarter || 1;
            this.quarterSeconds = state.quarterSeconds || 0;
            this.gameSeconds = state.gameSeconds || 0;
            this.playSelectMode = state.playSelectMode !== false;
            this.shotPositionMode = state.shotPositionMode !== false;

            if (state.gameDate) document.getElementById('game-date').value = state.gameDate;
            if (state.opponentName) document.getElementById('opponent').value = state.opponentName;
            if (state.gameType) document.getElementById('game-type').value = state.gameType;
            this.updateShotPositionToggleUI();

            return true;
        } catch (e) {
            console.error("Failed to load state", e);
            return false;
        }

    }


    clearState() {
        localStorage.removeItem(this.CONSTANTS.STORAGE_KEY);
        this.stopAutoCacheTimer();
    }


    // --- SETUP ---
    toggleRosterPlayer(name, btn) {
        console.log('toggleRosterPlayer called for:', name);
        if (!name || !btn) {
            console.log('Missing name or btn');
            return;
        }
        
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

    initRosterSelection() {
        const container = document.getElementById('roster-selection');
        if (!container) {
            console.error('roster-selection container not found');
            return;
        }
        console.log('Roster selection initialized, found', container.querySelectorAll('.player-select-btn').length, 'buttons');
        
        // Use event delegation for roster buttons
        container.addEventListener('click', (e) => {
            // Find the closest button with player-select-btn class
            let btn = e.target;
            if (!btn.classList.contains('player-select-btn')) {
                btn = btn.closest('.player-select-btn');
            }
            if (!btn) return;
            
            e.preventDefault();
            e.stopPropagation();
            
            const name = btn.getAttribute('data-player-name');
            if (name) {
                this.toggleRosterPlayer(name, btn);
            }
        });
        
        // Also attach direct handlers to any existing buttons for redundancy
        container.querySelectorAll('.player-select-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const name = btn.getAttribute('data-player-name');
                if (name) {
                    this.toggleRosterPlayer(name, btn);
                }
            });
        });
    }


    addNewPlayer() {
        const input = document.getElementById('new-player-name');
        const name = input.value.trim();
        if (name && !this.fullRoster.includes(name)) {
            this.fullRoster.push(name);
            const container = document.getElementById('roster-selection');
            const btn = document.createElement('button');
            btn.type = "button";
            btn.className = "btn btn-primary btn-sm active player-select-btn";;
            btn.style.margin = '2px';
            btn.textContent = name;  // Use textContent for safety
            btn.setAttribute('data-player-name', name);
            // No onclick needed - handled by event delegation
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
            btn.className = 'btn btn-outline-secondary m-1 starter-select-btn';
            btn.textContent = p;
            btn.setAttribute('data-player-name', p);
            // onclick handled by event delegation
            if (this.activeLineup.includes(p)) {
                btn.classList.remove('btn-outline-secondary');
                btn.classList.add('btn-primary');
            }
            container.appendChild(btn);
        });
        this.saveState();
    }

    initLineupSelection() {
        const container = document.getElementById('starter-selection');
        if (!container) return;
        
        // Use event delegation for lineup buttons
        container.addEventListener('click', (e) => {
            const btn = e.target.closest('.starter-select-btn');
            if (!btn) return;
            
            const name = btn.getAttribute('data-player-name');
            if (!name) return;
            
            if (this.activeLineup.includes(name)) {
                this.activeLineup = this.activeLineup.filter(x => x !== name);
                btn.classList.remove('btn-primary');
                btn.classList.add('btn-outline-secondary');
            } else {
                if (this.activeLineup.length >= 5) {
                    alert("You can only select 5 starters.");
                    return;
                }
                this.activeLineup.push(name);
                btn.classList.remove('btn-outline-secondary');
                btn.classList.add('btn-primary');
            }
            this.saveState();
        });
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
                    last_sub_in: this.activeLineup.includes(p) ? Date.now() : null,
                    reb_conceded: 0
                };
            });

            this.startingLineup = [...this.activeLineup];
            this.lineupHistory = [{
                players: [...this.activeLineup],
                startEventIndex: 0,
                quarter: this.quarter,
                gameSeconds: (this.quarter - 1) * this.QUARTER_LENGTH_SECONDS + this.quarterSeconds
            }];
        } else {
            this.activeLineup.forEach(p => {
                if (!this.stats[p].last_sub_in) this.stats[p].last_sub_in = Date.now();
                // Initialize quarter_minutes if missing (for backward compatibility)
                if (!this.stats[p].quarter_minutes) {
                    this.stats[p].quarter_minutes = {1: 0, 2: 0, 3: 0, 4: 0};
                }

            });

            if (this.startingLineup.length === 0 && this.activeLineup.length === 5) {
                this.startingLineup = [...this.activeLineup];
            }

            if (this.lineupHistory.length === 0) {
                this.lineupHistory = [{
                    players: [...this.activeLineup],
                    startEventIndex: this.gameEvents.length,
                    quarter: this.quarter,
                    gameSeconds: (this.quarter - 1) * this.QUARTER_LENGTH_SECONDS + this.quarterSeconds
                }];
            }

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
                                    <div></div>
                                    <span class="mx-2 font-weight-bold" id="disp-ft-${p}">${s.ftm}/${s.fta}</span>
                                    <div class="btn-group btn-group-sm">
                                        <button class="btn btn-warning font-weight-bold py-0" onclick="gameTracker.openFTModal('${p}')">FT</button>
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
                            <div class="row no-gutters text-center mt-1">
                                <div class="col-6 px-1">
                                    <div class="bg-light rounded p-1 border">
                                        <div class="small text-muted font-weight-bold mb-1">TECH</div>
                                        <button class="btn btn-sm btn-warning py-1 px-2 mx-1 font-weight-bold" onclick="gameTracker.recordTechFoul('${p}')">T</button>
                                    </div>
                                </div>
                                <div class="col-6 px-1">
                                    <div class="bg-light rounded p-1 border">
                                        <div class="small text-muted font-weight-bold mb-1">FLAGRANT</div>
                                        <button class="btn btn-sm btn-danger py-1 px-2 mx-1 font-weight-bold" onclick="gameTracker.recordFlagrantFoul('${p}')">F</button>
                                    </div>
                                </div>
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

        grid.insertAdjacentHTML('beforeend', this.buildLiveTipsCardHtml());
    }


    renderLiveTipsCard() {
        const grid = document.getElementById('player-grid');
        if (!grid) return;

        const existingCard = document.getElementById('live-tips-card-col');
        const html = this.buildLiveTipsCardHtml();

        if (existingCard) {
            existingCard.outerHTML = html;
        } else if (this.activeLineup.length > 0) {
            grid.insertAdjacentHTML('beforeend', html);
        }
    }


    buildLiveTipsCardHtml() {
        const insights = this.computeLiveTipsData();
        const currentLineupRow = this.buildCurrentLineupSummaryHtml(insights.playerMetrics);
        const foulRow = insights.foulAlerts.length > 0
            ? `<div class="live-tips-foul-row">${insights.foulAlerts.map(alert => `
                <span class="live-tips-foul-chip">
                    <i class="fas fa-exclamation-triangle mr-1"></i>${alert.player} ${alert.pf} PF
                </span>
            `).join('')}</div>`
            : '';

        const tipsList = insights.alerts.length > 0
            ? insights.alerts.map(alert => `
                <div class="live-tip-row ${alert.tone}">
                    <div class="live-tip-topline">
                        <span class="live-tip-badge ${alert.tone}">${alert.label}</span>
                        <span class="live-tip-title">${alert.title}</span>
                    </div>
                    <div class="live-tip-body">${alert.body}</div>
                </div>
            `).join('')
            : `<div class="live-tip-empty">No major current-stint alerts. Keep current rhythm.</div>`;

        return `
            <div class="col-md-6 col-lg-4 mb-3" id="live-tips-card-col">
                <div class="card h-100 shadow-sm border-0 live-tips-card">
                    <div class="card-header live-tips-header d-flex justify-content-between align-items-center py-2">
                        <h5 class="mb-0 font-weight-bold">Live Tips</h5>
                        <span class="live-tips-context">Current Stint</span>
                    </div>
                    <div class="card-body p-2 d-flex flex-column">
                        ${currentLineupRow}
                        ${foulRow}
                        <div class="live-tips-list">${tipsList}</div>
                    </div>
                </div>
            </div>
        `;
    }


    buildCurrentLineupSummaryHtml(playerMetrics) {
        if (!playerMetrics || playerMetrics.length === 0) {
            return `
                <div class="live-tip-row info">
                    <div class="live-tip-topline">
                        <span class="live-tip-badge info">On Court</span>
                        <span class="live-tip-title">No active lineup</span>
                    </div>
                </div>
            `;
        }

        const playersLine = playerMetrics
            .map(metrics => `${metrics.player} ${this.formatMinutes(metrics.stintSeconds)}`)
            .join(' | ');

        return `
            <div class="live-tip-row info">
                <div class="live-tip-topline">
                    <span class="live-tip-badge info">On Court</span>
                    <span class="live-tip-title">Continuous stint</span>
                </div>
                <div class="live-tip-body">${playersLine}</div>
            </div>
        `;
    }


    computeLiveTipsData() {
        const currentGameSeconds = (this.quarter - 1) * this.QUARTER_LENGTH_SECONDS + this.quarterSeconds;
        const lineupStartSeconds = this.getCurrentLineupStartGameSeconds();
        const shotEventsInLineup = this.shotLocations.filter(shot =>
            this.getShotGameSeconds(shot) >= lineupStartSeconds && shot.play_id
        );
        const teamEventsInLineup = this.gameEvents.filter(event =>
            (event.game_seconds || 0) >= lineupStartSeconds
        );

        const foulThreshold = this.quarter <= 1 ? 2 : (this.quarter === 2 ? 3 : 4);
        const foulAlerts = this.activeLineup
            .filter(player => (this.stats[player]?.pf || 0) >= foulThreshold)
            .map(player => ({ player, pf: this.stats[player].pf }));

        const alerts = [];
        const playerMetrics = this.activeLineup.map(player => this.getCurrentStintMetrics(player, currentGameSeconds));
        const longestStint = playerMetrics.reduce((max, metrics) => Math.max(max, metrics.stintSeconds), 0);
        const averageStint = playerMetrics.length > 0
            ? playerMetrics.reduce((sum, metrics) => sum + metrics.stintSeconds, 0) / playerMetrics.length
            : 0;

        playerMetrics.forEach(metrics => {
            if (metrics.shotAttempts >= 2 && metrics.shotMade >= 2 && metrics.shotPct >= 0.6 && metrics.points >= 4) {
                alerts.push({
                    score: 84 + metrics.points,
                    tone: 'success',
                    label: 'Hot Hand',
                    title: metrics.player,
                    body: `${metrics.player} has ${metrics.points} pts this stint on ${metrics.shotMade}/${metrics.shotAttempts} FG.`
                });
            }

            if (metrics.shotAttempts >= 3 && metrics.shotPct <= 0.34) {
                alerts.push({
                    score: 88 + metrics.shotAttempts,
                    tone: 'warning',
                    label: 'Cold Stint',
                    title: metrics.player,
                    body: `${metrics.player} is ${metrics.shotMade}/${metrics.shotAttempts} FG this stint. Consider easier looks.`
                });
            }

            if (metrics.turnovers >= 2 || (metrics.turnovers >= 1 && metrics.lastActionType === 'TURNOVER')) {
                alerts.push({
                    score: 92 + (metrics.turnovers * 4),
                    tone: 'danger',
                    label: 'Ball Security',
                    title: metrics.player,
                    body: `${metrics.player} has ${metrics.turnovers} turnover${metrics.turnovers === 1 ? '' : 's'} this stint. Simplify the next action.`
                });
            }

            if (metrics.assists >= 2) {
                alerts.push({
                    score: 68 + (metrics.assists * 3),
                    tone: 'info',
                    label: 'Playmaking',
                    title: metrics.player,
                    body: `${metrics.player} already created ${metrics.assists} assist${metrics.assists === 1 ? '' : 's'} this stint.`
                });
            }

            if (metrics.rebounds >= 3) {
                alerts.push({
                    score: 64 + (metrics.rebounds * 2),
                    tone: 'info',
                    label: 'Boards',
                    title: metrics.player,
                    body: `${metrics.player} has ${metrics.rebounds} rebounds this stint. Keep using that activity.`
                });
            }

            const involvement = metrics.shotAttempts + metrics.fta + metrics.turnovers + metrics.assists + metrics.rebounds;
            if (metrics.stintSeconds >= 240 && involvement <= 1) {
                alerts.push({
                    score: 54 + Math.floor(metrics.stintSeconds / 60),
                    tone: 'neutral',
                    label: 'Quiet Stint',
                    title: metrics.player,
                    body: `${metrics.player} has been on for ${this.formatMinutes(metrics.stintSeconds)} with little involvement.`
                });
            }

            if (
                metrics.stintSeconds >= 360 &&
                metrics.stintSeconds >= averageStint + 120 &&
                metrics.stintSeconds >= longestStint - 30
            ) {
                alerts.push({
                    score: 76 + Math.floor(metrics.stintSeconds / 60),
                    tone: 'warning',
                    label: 'Long Stint',
                    title: metrics.player,
                    body: `${metrics.player} is at ${this.formatMinutes(metrics.stintSeconds)} this stint. Watch legs and execution.`
                });
            }
        });

        const playAlerts = this.computePlayPppAlerts(shotEventsInLineup, teamEventsInLineup);
        alerts.push(...playAlerts);

        alerts.sort((a, b) => b.score - a.score);

        const dedupedAlerts = [];
        const seenKeys = new Set();
        alerts.forEach(alert => {
            const key = `${alert.label}:${alert.title}`;
            if (!seenKeys.has(key) && dedupedAlerts.length < 5) {
                seenKeys.add(key);
                dedupedAlerts.push(alert);
            }
        });

        return { foulAlerts, playerMetrics, alerts: dedupedAlerts };
    }


    computePlayPppAlerts(shotEventsInLineup, teamEventsInLineup) {
        const playsById = new Map();
        this.playsCache.forEach(play => playsById.set(play.id, play.name));

        const playStats = new Map();
        const ensurePlay = (playId, playName = null) => {
            if (!playId) return null;
            if (!playStats.has(playId)) {
                playStats.set(playId, {
                    playId,
                    playName: playsById.get(playId) || playName || `Play ${playId}`,
                    possessions: 0,
                    points: 0,
                    turnovers: 0
                });
            }
            return playStats.get(playId);
        };

        shotEventsInLineup.forEach(shot => {
            const play = ensurePlay(shot.play_id);
            if (!play) return;
            play.possessions += 1;
            play.points += shot.result === 'made' ? (shot.points || 0) : 0;
        });

        teamEventsInLineup.forEach(event => {
            if (!event.play_id) return;
            if (event.type === 'TURNOVER') {
                const play = ensurePlay(event.play_id, event.detail?.play_name);
                if (!play) return;
                play.possessions += 1;
                play.turnovers += 1;
            }
            if (event.type === 'FT') {
                const play = ensurePlay(event.play_id, event.detail?.play_name);
                if (!play) return;
                play.possessions += 1;
                play.points += event.detail?.ftm || 0;
            }
        });

        const candidates = Array.from(playStats.values())
            .filter(play => play.possessions >= 2)
            .map(play => ({ ...play, ppp: play.points / play.possessions }));

        if (candidates.length === 0) return [];

        candidates.sort((a, b) => b.ppp - a.ppp);
        const positive = candidates.find(play => play.ppp >= 1.3 && play.points >= 3);
        const negative = [...candidates].reverse().find(play => play.ppp <= 0.7);

        const alerts = [];
        if (positive) {
            alerts.push({
                score: 83 + positive.ppp,
                tone: 'success',
                label: 'Play PPP',
                title: positive.playName,
                body: `${positive.playName} has ${positive.points} pts on ${positive.possessions} possessions this lineup (${positive.ppp.toFixed(2)} PPP).`
            });
        }
        if (negative && (!positive || negative.playId !== positive.playId)) {
            alerts.push({
                score: 82 + ((1 - negative.ppp) * 10),
                tone: 'warning',
                label: 'Play PPP',
                title: negative.playName,
                body: `${negative.playName} has ${negative.points} pts on ${negative.possessions} possessions${negative.turnovers ? ` with ${negative.turnovers} TOV` : ''} (${negative.ppp.toFixed(2)} PPP).`
            });
        }

        return alerts;
    }


    getCurrentStintMetrics(player, currentGameSeconds) {
        const stintStartSeconds = this.getPlayerStintStartGameSeconds(player);
        const shots = this.shotLocations.filter(shot =>
            shot.shooter === player && this.getShotGameSeconds(shot) >= stintStartSeconds
        );
        const events = this.gameEvents.filter(event =>
            (event.game_seconds || 0) >= stintStartSeconds &&
            (
                event.player === player ||
                ((event.type === 'FT' || event.type === 'TURNOVER') && event.player === player) ||
                (event.type && event.type.startsWith('REBOUND_') && event.player === player)
            )
        );
        const ftEvents = events.filter(event => event.type === 'FT');
        const turnovers = events.filter(event => event.type === 'TURNOVER').length;
        const rebounds = events.filter(event => event.type === 'REBOUND_OFFENSIVE' || event.type === 'REBOUND_DEFENSIVE').length;
        const assists = shots.filter(shot => shot.assister === player && shot.result === 'made').length;
        const points = shots.reduce((sum, shot) => sum + (shot.result === 'made' ? (shot.points || 0) : 0), 0) +
            ftEvents.reduce((sum, event) => sum + (event.detail?.ftm || 0), 0);
        const shotAttempts = shots.length;
        const shotMade = shots.filter(shot => shot.result === 'made').length;
        const fta = ftEvents.reduce((sum, event) => sum + (event.detail?.fta || 0), 0);
        const lastRelevant = [...events]
            .sort((a, b) => (b.game_seconds || 0) - (a.game_seconds || 0))[0];

        return {
            player,
            stintStartSeconds,
            stintSeconds: Math.max(0, currentGameSeconds - stintStartSeconds),
            points,
            shotAttempts,
            shotMade,
            shotPct: shotAttempts > 0 ? shotMade / shotAttempts : 0,
            turnovers,
            rebounds,
            assists,
            fta,
            lastActionType: lastRelevant?.type || null
        };
    }


    getCurrentLineupStartGameSeconds() {
        if (this.lineupHistory.length === 0) return 0;
        const latestSegment = this.lineupHistory[this.lineupHistory.length - 1];
        return latestSegment?.gameSeconds || 0;
    }


    getPlayerStintStartGameSeconds(player) {
        for (let i = this.gameEvents.length - 1; i >= 0; i--) {
            const event = this.gameEvents[i];
            if (event.type === 'SUB_IN' && event.player === player) {
                return event.game_seconds || 0;
            }
        }

        return this.startingLineup.includes(player) ? 0 : this.getCurrentLineupStartGameSeconds();
    }


    getShotGameSeconds(shot) {
        const quarter = Number(shot.quarter || 1);
        const clockSeconds = Number(shot.clockSeconds || 0);
        return ((quarter - 1) * this.QUARTER_LENGTH_SECONDS) + clockSeconds;
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
        this.renderLiveTipsCard();
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
        list.classList.add('split');

        const noneBtn = document.createElement('button');
        noneBtn.type = 'button';
        noneBtn.className = 'live-option-btn secondary';
        noneBtn.innerHTML = `<span><div class="live-option-title">No Assist</div></span><span class="live-option-tag">SKIP</span>`;
        noneBtn.onclick = () => this.pickAssister(null);
        list.appendChild(noneBtn);

        this.activeLineup.forEach(p => {
            if (p === shooter) return;
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'live-option-btn primary';
            btn.innerHTML = `<span><div class="live-option-title">${p}</div></span><span class="live-option-tag">AST</span>`;
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
        if (!this.shotPositionMode) {
            this.skipShotLocation();
            return;
        }
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
        if (!this.shotPositionMode) {
            this.skipShotLocation();
            return;
        }
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
        list.classList.add('split');

        const noneBtn = document.createElement('button');
        noneBtn.type = 'button';
        noneBtn.className = 'live-option-btn danger';
        noneBtn.innerHTML = `<span><div class="live-option-title">No O-Reb</div><div class="live-option-subtitle">Defensive possession change</div></span><span class="live-option-tag">DEF</span>`;
        noneBtn.onclick = () => this.confirmOreb(null);
        list.appendChild(noneBtn);

        this.activeLineup.forEach(p => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'live-option-btn primary';
            btn.innerHTML = `<span><div class="live-option-title">${p}</div><div class="live-option-subtitle">Offensive rebound</div></span><span class="live-option-tag">OREB</span>`;
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

        // **NEW: Log events for key stats (STL, BLK, REB, PF)**
        if (delta > 0) {
            let eventType = null;
            if (key === 'stl') eventType = 'STEAL';
            if (key === 'blk') eventType = 'BLOCK';
            if (key === 'dreb') eventType = 'REBOUND_DEFENSIVE';
            if (key === 'oreb') eventType = 'REBOUND_OFFENSIVE';
            if (key === 'pf') eventType = 'FOUL_PERSONAL';
            
            if (eventType) {
                this.logEvent(eventType, player);
            }

        }


        this.stats[player][key] += delta;
        this.updateUI(player);
        this.saveState();
    }


    logEvent(type, player = null, detail = null, playId = null) {
        const remaining = Math.max(0, this.QUARTER_LENGTH_SECONDS - this.quarterSeconds);
        const mins = Math.floor(remaining / 60);
        const secs = remaining % 60;
        const timeRemaining = `${mins}:${secs.toString().padStart(2, '0')}`;
        
        const teamScore = this.calculateTeamScore();
        const margin = teamScore - this.opponentScore;
        
        const gameSeconds = (this.quarter - 1) * this.QUARTER_LENGTH_SECONDS + this.quarterSeconds;
        
        if (['SHOT_2PT', 'SHOT_3PT', 'FT', 'TURNOVER', 'OPP_SCORE'].includes(type)) {
            const isOpponent = type === 'OPP_SCORE';
            if (this.lastPossessionTeam !== (isOpponent ? 'opp' : 'team')) {
                this.possessionNumber++;
            }

            this.lastPossessionTeam = isOpponent ? 'opp' : 'team';
        }

        
        this.gameEvents.push({
            type,
            player,
            detail,
            quarter: this.quarter,
            clockSeconds: this.quarterSeconds,
            time_remaining: timeRemaining,
            score_margin: margin,
            game_seconds: gameSeconds,
            possession_number: this.possessionNumber,
            play_id: playId,
            event_index: this.gameEvents.length,
            active_lineup: [...this.activeLineup],
            timestamp: Date.now()
        });
    }


    setStartingLineup(players) {
        this.startingLineup = players;
        this.activeLineup = players;
        this.lineupHistory = [{
            players: [...players],
            startEventIndex: 0,
            quarter: this.quarter,
            gameSeconds: (this.quarter - 1) * this.QUARTER_LENGTH_SECONDS + this.quarterSeconds
        }];
        this.renderActivePlayers();
        this.saveState();
    }


    calculateTeamScore() {
        return Object.values(this.stats).reduce((sum, s) => sum + (s.points || 0), 0);
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
        this.trackOppAction('OPP_SCORE', { points, manual: true });
        this.saveState();
    }

    
    // --- FREE THROW TRIP HANDLING ---
    
    openFTModal(player) {
        this.pendingFTTrip = { player, totalFt: 2, ftm: 0 };
        
        document.getElementById('ft-player-name').innerText = player;
        document.getElementById('ft-count-select').value = 2;
        this.renderFTMadeOptions(2, 0);
        
        $('#ftModal').modal('show');
    }

    
    setFTCount(count) {
        const parsedCount = parseInt(count);
        this.pendingFTTrip.totalFt = parsedCount;
        const nextMade = Math.min(this.pendingFTTrip.ftm || 0, parsedCount);
        this.pendingFTTrip.ftm = nextMade;
        this.renderFTMadeOptions(parsedCount, nextMade);
    }

    renderFTMadeOptions(totalFt, selectedFtm = 0) {
        const container = document.getElementById('ft-made-options');
        if (!container) return;

        container.innerHTML = '';

        for (let made = 0; made <= totalFt; made++) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = `btn btn-lg m-1 ${made === selectedFtm ? 'btn-success' : 'btn-outline-secondary'}`;
            btn.textContent = `${made}`;
            btn.onclick = () => {
                this.pendingFTTrip.ftm = made;
                this.renderFTMadeOptions(totalFt, made);
            };
            container.appendChild(btn);
        }
    }

    
    confirmFTCount() {
        const totalFt = this.pendingFTTrip.totalFt;
        const ftm = Math.min(this.pendingFTTrip.ftm || 0, totalFt);
        
        this.pendingFTTrip.ftm = ftm;
        
        $('#ftModal').modal('hide');
        
        // Open play selector for this FT trip
        this.openPlaySelector('FT', this.pendingFTTrip.player, 'ft');
    }

    
    confirmFTPlaySelection(play) {
        if (!this.pendingFTTrip) return;
        
        const { player, totalFt, ftm } = this.pendingFTTrip;
        
        // Update stats
        this.stats[player].ftm += ftm;
        this.stats[player].fta += totalFt;
        this.stats[player].points += ftm;
        
        // Update plus/minus for active lineup
        this.activeLineup.forEach(pName => {
            if (this.stats[pName]) {
                this.stats[pName].plus_minus += ftm;
            }

        });
        
        // Log single batch event with play_id
        this.logEvent('FT', player, { ftm: ftm, fta: totalFt }, play ? play.id : null);
        
        this.updateUI(player);
        this.activeLineup.forEach(pName => this.updateUI(pName));
        this.updateScoreboard();
        this.pendingFTTrip = null;
        this.saveState();
    }

    
    // --- OPPONENT SHOT TRACKING ---
    
    oppShot(type) {
        const points = type === '2pt' ? 2 : (type === '3pt' ? 3 : 1);
        this.pendingOppShot = { type, points };
        
        document.getElementById('opp-shot-type').innerText = type.toUpperCase();
        $('#oppShotModal').modal('show');
    }

    

    
    
    trackOppAction(type, detail = null) {
        this.oppRecentActions.push({
            eventIndex: this.gameEvents.length - 1,
            type,
            detail,
            timestamp: Date.now()
        });
        if (this.oppRecentActions.length > 10) {
            this.oppRecentActions.shift();
        }
    }


    showRemoveOppActionModal() {
        const list = document.getElementById('remove-opp-action-list');
        if (!list) return;
        
        list.innerHTML = '';
        
        const recentOpp = this.oppRecentActions.slice(-3).reverse();
        
        if (recentOpp.length === 0) {
            alert('No recent opponent actions to remove.');
            return;
        }

        recentOpp.forEach((action, idx) => {
            const btn = document.createElement('button');
            btn.className = 'live-option-btn danger';
            
            let label = '';
            let sub = '';
            if (action.type === 'OPP_SCORE') {
                const pts = action.detail?.points || 0;
                const result = action.detail?.result || 'made';
                label = `OPP ${pts}PT ${result.toUpperCase()}`;
                sub = result === 'made' ? `Subtract ${pts} points` : 'Remove miss event';
            } else if (action.type === 'OPP_OREB') {
                label = 'OPP OREB';
                sub = 'Remove offensive rebound';
            } else {
                label = action.type;
                sub = 'Remove event';
            }

            btn.innerHTML = `<span><div class="live-option-title">${label}</div><div class="live-option-subtitle">${sub}</div></span><span class="live-option-tag">REMOVE</span>`;
            
            btn.onclick = (e) => {
                e.preventDefault();
                this.removeOppAction(action);
            };
            list.appendChild(btn);
        });

        $('#removeOppActionModal').modal('show');
    }


    removeOppAction(action) {
        if (action.eventIndex >= 0 && action.eventIndex < this.gameEvents.length) {
            const event = this.gameEvents[action.eventIndex];
            
            if (event.type === 'OPP_SCORE' && event.detail?.result === 'made') {
                const pts = event.detail?.points || 0;
                this.opponentScore -= pts;
                if (this.opponentScore < 0) this.opponentScore = 0;
                document.getElementById('opp-score-display').innerText = this.opponentScore;
                
                this.activeLineup.forEach(pName => {
                    if (this.stats[pName]) {
                        this.stats[pName].plus_minus += pts;
                    }

                    this.updateUI(pName);
                });
            }

            
            this.gameEvents.splice(action.eventIndex, 1);
            
            this.oppRecentActions = this.oppRecentActions.filter(a => a.eventIndex !== action.eventIndex);
            
            this.oppRecentActions.forEach(a => {
                if (a.eventIndex > action.eventIndex) {
                    a.eventIndex--;
                }
            });
            
            this.updateScoreboard();
            $('#removeOppActionModal').modal('hide');
            this.saveState();
        }
    }

    
    confirmOppShot(made) {
        if (!this.pendingOppShot) return;
        
        const { type, points } = this.pendingOppShot;
        
        if (made) {
            // Made shot - log score and show location modal
            this.logEvent('OPP_SCORE', null, { 
                points, 
                shot_type: type,
                result: 'made' 
            });
            
            this.trackOppAction('OPP_SCORE', { points, shot_type: type, result: 'made' });
            
            this.opponentScore += points;
            document.getElementById('opp-score-display').innerText = this.opponentScore;
            
            this.activeLineup.forEach(pName => {
                if (this.stats[pName]) {
                    this.stats[pName].plus_minus -= points;
                }

                this.updateUI(pName);
            });
            
            if (type === 'ft') {
                // Skip location for free throws
                this.pendingOppShot = null;
                this.pendingOppShotLocation = null;
                $('#oppShotModal').modal('hide');
                this.updateScoreboard();
                this.saveState();
            } else {
                this.pendingOppShotLocation = { type, points };
                document.getElementById('opp-shotloc-info').innerText = `${type.toUpperCase()} MADE (${points}PT)`;
                document.getElementById('opp-shotloc-coords').innerText = '';
                document.getElementById('btn-confirm-opp-shotloc').disabled = true;
                
                const marker = document.getElementById('opp-shotloc-marker');
                marker.setAttribute('cx', -20);
                marker.setAttribute('cy', -20);
                
                this.setupOppShotLocationClick();
                
                $('#oppShotModal').modal('hide');
                $('#oppShotLocModal').modal('show');
            }
        } else {
            // Missed shot - log as missed (no location) and show rebound modal
            this.logEvent('OPP_SCORE', null, { 
                points: 0, 
                shot_type: type,
                result: 'missed' 
            });
            
            $('#oppShotModal').modal('hide');
            $('#oppReboundModal').modal('show');
        }

    }

    confirmOppRebound(reboundType) {
        if (!this.pendingOppShot) return;
        
        const { type, points } = this.pendingOppShot;
        
        if (reboundType === 'offensive') {
            // Opponent got the offensive rebound
            this.logEvent('OPP_OREB', null, { shot_type: type });
            this.trackOppAction('OPP_OREB');
            
            this.activeLineup.forEach(pName => {
                if (this.stats[pName]) {
                    this.stats[pName].reb_conceded = (this.stats[pName].reb_conceded || 0) + 1;
                    this.updateUI(pName);
                }

            });
            
            this.pendingOppShot = null;
            $('#oppReboundModal').modal('hide');
            this.saveState();
        } else {
            // We got the defensive rebound - show player selector
            $('#oppReboundModal').modal('hide');
            this.showDrebPlayerSelector();
        }

    }

    
    showDrebPlayerSelector() {
        const list = document.getElementById('dreb-player-list');
        list.innerHTML = '';
        list.classList.add('split');

        // Add "Team" option for unknown player
        const teamBtn = document.createElement('button');
        teamBtn.className = 'live-option-btn secondary';
        teamBtn.innerHTML = `<span><div class="live-option-title">Team</div><div class="live-option-subtitle">Unknown rebounder</div></span><span class="live-option-tag">TEAM</span>`;
        teamBtn.onclick = () => this.confirmDrebPlayer(null);
        list.appendChild(teamBtn);

        // Add active players
        this.activeLineup.forEach(p => {
            const btn = document.createElement('button');
            btn.className = 'live-option-btn primary';
            btn.innerHTML = `<span><div class="live-option-title">${p}</div><div class="live-option-subtitle">Defensive rebound</div></span><span class="live-option-tag">DREB</span>`;
            btn.onclick = () => this.confirmDrebPlayer(p);
            list.appendChild(btn);
        });

        $('#drebPlayerModal').modal('show');
    }
    
    confirmDrebPlayer(player) {
        if (player && this.stats[player]) {
            this.updateStat(player, 'dreb', 1);
        }

        
        this.pendingOppShot = null;
        $('#drebPlayerModal').modal('hide');
        this.saveState();
    }


    


    
    setupOppShotLocationClick() {
        if (this.oppShotLocListenerAttached) return;

        const svg = document.getElementById('oppHalfCourtSvg');
        const hitbox = document.getElementById('opp-court-hitbox');
        const marker = document.getElementById('opp-shotloc-marker');

        if (!hitbox || !svg) return;

        hitbox.addEventListener('pointerdown', (evt) => {
            evt.preventDefault();

            const pt = svg.createSVGPoint();
            pt.x = evt.clientX;
            pt.y = evt.clientY;
            const ctm = svg.getScreenCTM();
            if (!ctm) return;
            const cursor = pt.matrixTransform(ctm.inverse());

            let x = Math.max(0, Math.min(this.CONSTANTS.SVG_WIDTH, cursor.x));
            let y = Math.max(0, Math.min(this.CONSTANTS.SVG_HEIGHT, cursor.y));

            marker.setAttribute('cx', x);
            marker.setAttribute('cy', y);

            this._pendingOppShotX = x;
            this._pendingOppShotY = y;

            document.getElementById('opp-shotloc-coords').innerText = `(${Math.round(x)}, ${Math.round(y)})`;
            document.getElementById('btn-confirm-opp-shotloc').disabled = false;
        });

        this.oppShotLocListenerAttached = true;
    }


    confirmOppShotLocation() {
        if (!this.pendingOppShotLocation) return;
        
        // Add location to the last OPP_SCORE event
        if (this._pendingOppShotX !== null && this._pendingOppShotY !== null) {
            // Find the last OPP_SCORE event
            for (let i = this.gameEvents.length - 1; i >= 0; i--) {
                const ev = this.gameEvents[i];
                if (ev.type === 'OPP_SCORE') {
                    // Update detail with location
                    ev.detail = ev.detail || {};
                    ev.detail.x_loc = this._pendingOppShotX;
                    ev.detail.y_loc = this._pendingOppShotY;
                    // Also add at top level for easier access
                    ev.x_loc = this._pendingOppShotX;
                    ev.y_loc = this._pendingOppShotY;
                    break;
                }

            }

        }

        
        this.pendingOppShotLocation = null;
        this._pendingOppShotX = null;
        this._pendingOppShotY = null;
        
        $('#oppShotLocModal').modal('hide');
        this.pendingOppShot = null;
        this.updateScoreboard();
        this.saveState();
    }


    skipOppShotLocation() {
        this.pendingOppShotLocation = null;
        this._pendingOppShotX = null;
        this._pendingOppShotY = null;
        
        $('#oppShotLocModal').modal('hide');
        this.pendingOppShot = null;
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
            gameType: document.getElementById('game-type').value,
            lineupHistory: JSON.parse(JSON.stringify(this.lineupHistory)),
            startingLineup: [...this.startingLineup],
            playSelectMode: this.playSelectMode,
            shotPositionMode: this.shotPositionMode
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
                        quarterBreakdown += `<span class="${qClass} mx-1" style="font-size: 0.75rem;">Q${q}: ${this.formatMinutes(displayQ)}</span>`;
                    }

                    qEl.innerHTML = quarterBreakdown;
                }

            }

        });

        this.renderLiveTipsCard();
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
        if (this.quarter === 2) {
            if (confirm('End of Q2 - Generate Half-Time Summary PDF?')) {
                this.generateHalftimePDF();
            }

        }

        
        if (this.isClockRunning) this.toggleClock();
        
        this.logEvent('NEXT_QUARTER', null, { from_quarter: this.quarter, to_quarter: this.quarter + 1 });
        
        this.quarter++;
        this.quarterSeconds = 0;
        this.updateQuarterDisplay();
        this.saveState();
        
        alert(`Started Quarter ${this.quarter}`);
    }

    
    updateQuarterDisplay() {
        document.getElementById('quarter-display').innerText = 'Q' + this.quarter;
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
            const playerStats = this.stats[p] || {
                plus_minus: 0,
                minutes_seconds: 0,
                quarter_minutes: {1: 0, 2: 0, 3: 0, 4: 0},
                last_sub_in: null
            };
            const pmVal = playerStats.plus_minus || 0;
            const pmSign = pmVal > 0 ? '+' : '';
            const pmClass = pmVal > 0 ? 'text-success' : (pmVal < 0 ? 'text-danger' : 'text-muted');

            // Calculate total minutes displayed
            let totalDisplayedSeconds = playerStats.minutes_seconds || 0;
            if (isActive && playerStats.last_sub_in) {
                const diffSeconds = Math.floor((now - playerStats.last_sub_in) / 1000);
                totalDisplayedSeconds += diffSeconds;
            }


            const totalTimeStr = this.formatMinutes(totalDisplayedSeconds);
            const quarterMins = playerStats.quarter_minutes || {1: 0, 2: 0, 3: 0, 4: 0};
            let quarterBreakdown = '';
            for (let q = 1; q <= 4; q++) {
                let displayQ = quarterMins[q] || 0;
                const isCurrentQ = q === this.quarter;
                if (isActive && isCurrentQ && playerStats.last_sub_in) {
                    const diffSeconds = Math.floor((now - playerStats.last_sub_in) / 1000);
                    displayQ += diffSeconds;
                }

                const qClass = isCurrentQ ? 'sub-quarter-chip current' : 'sub-quarter-chip';
                quarterBreakdown += `<span class="${qClass}">Q${q}: ${this.formatMinutes(displayQ)}</span>`;
            }

            const btn = document.createElement('button');
            btn.className = `list-group-item list-group-item-action sub-player-card ${isActive ? 'active' : ''}`;
            btn.style.cursor = 'pointer';
            btn.innerHTML = `<div class="sub-player-main">
                                <div class="flex-grow-1">
                                    <div class="sub-player-name">${p} <small class="sub-player-pm ${pmClass} font-weight-bold">(${pmSign}${pmVal})</small></div>
                                    <div class="sub-player-meta">
                                        <span class="sub-total-time">Total: ${totalTimeStr}</span>
                                    </div>
                                    <div class="sub-quarter-grid">
                                        ${quarterBreakdown}
                                    </div>
                                </div>
                                <small data-role="lineup-status" class="sub-status font-weight-bold">${isActive ? 'ON COURT' : 'BENCH'}</small>
                             </div>`;

            btn.onclick = () => {
                if (this._tempLineup.includes(p)) {
                    this._tempLineup = this._tempLineup.filter(x => x !== p);
                    btn.classList.remove('active');
                    btn.querySelector('[data-role="lineup-status"]').innerText = 'BENCH';
                } else {
                    if (this._tempLineup.length >= 5) {
                        alert("Only 5 players allowed on court.");
                        return;
                    }

                    this._tempLineup.push(p);
                    btn.classList.add('active');
                    btn.querySelector('[data-role="lineup-status"]').innerText = 'ON COURT';
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

        if (this.lineupHistory.length > 0) {
            this.lineupHistory[this.lineupHistory.length - 1].endEventIndex = this.gameEvents.length;
        }


        [...prevLineup].filter(p => !newLineup.has(p)).forEach(p => this.logEvent('SUB_OUT', p));
        [...newLineup].filter(p => !prevLineup.has(p)).forEach(p => this.logEvent('SUB_IN', p));

        this.activeLineup = [...this._tempLineup];

        this.lineupHistory.push({
            players: [...this.activeLineup],
            startEventIndex: this.gameEvents.length,
            quarter: this.quarter,
            gameSeconds: (this.quarter - 1) * this.QUARTER_LENGTH_SECONDS + this.quarterSeconds
        });

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
            let displayedSeconds = s.minutes_seconds || 0;
            if (this.isClockRunning && s.last_sub_in) {
                const diffSeconds = Math.floor((Date.now() - s.last_sub_in) / 1000);
                displayedSeconds += diffSeconds;
            }

            return {
                name,
                ...s,
                total_reb: s.oreb + s.dreb,
                display_minutes: this.formatMinutes(displayedSeconds)
            };
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
            const pmChipClass = p.plus_minus > 0
                ? 'stats-chip stats-chip-pm-positive'
                : (p.plus_minus < 0 ? 'stats-chip stats-chip-pm-negative' : 'stats-chip stats-chip-pm-neutral');

            row.innerHTML = `
                <td class="text-left text-nowrap font-weight-bold stats-player-cell">
                    <div class="stats-player-name">
                        ${p.name}
                    </div>
                    ${isActive ? '<span class="badge badge-success ml-1" style="font-size:0.6em">ON</span>' : ''}
                </td>
                <td><span class="stats-chip stats-chip-min">${p.display_minutes}</span></td>
                <td class="border-left"><span class="stats-chip stats-chip-points">${p.points}</span></td>
                <td>${p.total_reb}<span class="stats-subtext">${p.oreb}/${p.dreb}</span></td>
                <td>${p.ast}</td>
                <td>${p.stl}</td>
                <td>${p.blk}</td>
                <td>${p.tov}</td>
                <td class="${p.pf >= 3 ? 'text-danger font-weight-bold' : ''}">${p.pf}</td>
                <td class="border-left text-nowrap">${p.fgm}/${p.fga}<span class="stats-subtext">${fgPct}%</span></td>
                <td class="text-nowrap">${p.tpm}/${p.tpa}<span class="stats-subtext">${tpPct}%</span></td>
                <td class="text-nowrap">${p.ftm}/${p.fta}<span class="stats-subtext">${ftPct}%</span></td>
                <td class="${pmClass} font-weight-bold border-left"><span class="${pmChipClass}">${pmSign}${p.plus_minus}</span></td>
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
                <td><span class="stats-chip stats-chip-min">-</span></td>
                <td class="border-left"><span class="stats-chip stats-chip-points">${team.points}</span></td>
                <td>${team.reb}<span class="stats-subtext">${team.oreb}/${team.dreb}</span></td>
                <td>${team.ast}</td>
                <td>${team.stl}</td>
                <td>${team.blk}</td>
                <td>${team.tov}</td>
                <td>${team.pf}</td>
                <td class="border-left">${team.fgm}/${team.fga}<span class="stats-subtext">${teamFgPct}%</span></td>
                <td>${team.tpm}/${team.tpa}<span class="stats-subtext">${teamTpPct}%</span></td>
                <td>${team.ftm}/${team.fta}<span class="stats-subtext">${teamFtPct}%</span></td>
                <td class="border-left"><span class="stats-chip stats-chip-pm-neutral">-</span></td>
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
        const btn = document.getElementById('btn-finish-game');

        // Validation check
        const opponent = document.getElementById('opponent').value;
        const date = document.getElementById('game-date').value;
        if (!opponent || opponent.trim() === "") {
            alert("Please provide an opponent name before finishing.");
            return;
        }

        if (!confirm(`Are you sure you want to finish and save the game against ${opponent}?`)) return;

        // Visual feedback
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i>Saving...';
        }

        if (this.isClockRunning) this.toggleClock();

        if (this.lineupHistory.length > 0) {
            this.lineupHistory[this.lineupHistory.length - 1].endEventIndex = this.gameEvents.length;
        }

        let total = 0;
        Object.values(this.stats).forEach(s => total += (s.points || 0));

        const finalStats = {};
        Object.keys(this.stats).forEach(p => {
            const s = this.stats[p];
            s.minutes = this.formatMinutes(s.minutes_seconds);
            finalStats[p] = s;
        });

        const payload = {
            schema_version: this.SCHEMA_VERSION,
            features: this.FEATURES,
            opponent: opponent,
            date: date,
            game_type: document.getElementById('game-type').value,
            team_score: total,
            opponent_score: this.opponentScore,
            shot_locations: this.shotLocations,
            game_events: this.gameEvents,
            player_stats: finalStats,
            starting_lineup: this.startingLineup,
            lineup_history: this.lineupHistory
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
                throw new Error(data.error || data.details || "Server error occurred");
            }
        }).catch(err => {
            console.error("Save failed:", err);

            // Re-enable button
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-save mr-1"></i>Retry Save';
            }

            // Show error modal with rescue options
            document.getElementById('save-error-msg').innerText = err.message || "Network error or server timeout.";
            $('#saveErrorModal').modal('show');
        });
    }


    downloadRawData() {
        const opponent = document.getElementById('opponent').value || "Unknown";
        const date = document.getElementById('game-date').value || new Date().toISOString().split('T')[0];

        let total = 0;
        Object.values(this.stats).forEach(s => total += (s.points || 0));

        const payload = {
            schema_version: this.SCHEMA_VERSION,
            exported_at: new Date().toISOString(),
            game: {
                opponent: opponent,
                date: date,
                team_score: total,
                opponent_score: this.opponentScore,
                game_type: document.getElementById('game-type').value,
                source: "LIVE_RESCUE"
            },
            player_stats: this.stats,
            shot_locations: this.shotLocations,
            game_events: this.gameEvents,
            starting_lineup: this.startingLineup,
            lineup_history: this.lineupHistory
        };

        const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `rescue_game_${opponent}_${date}.json`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        alert("Game data downloaded. You can import this JSON file if you cannot fix the save issue.");
    }

    async generateHalftimePDF() {
        const payload = {
            opponent: document.getElementById('opponent').value,
            date: document.getElementById('game-date').value,
            team_score: this.calculateTeamScore(),
            opp_score: this.opponentScore,
            player_stats: this.stats,
            game_events: this.gameEvents.filter(e => e.quarter === 1 || e.quarter === 2),
            shot_locations: this.shotLocations.filter(s => s.quarter === 1 || s.quarter === 2),
            schema_version: this.SCHEMA_VERSION
        };
        
        try {
            const csrfToken = document.getElementById('csrf_token').value;
            
            const response = await fetch('/reports/live/halftime-pdf', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify(payload)
            });
            
            if (response.ok) {
                const blob = await response.blob();
                
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `halftime_${payload.opponent}_${payload.date}.pdf`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
                
                console.log('Half-time PDF generated successfully');
            } else {
                console.error('Failed to generate halftime PDF');
            }

        } catch (err) {
            console.error('Error generating halftime PDF:', err);
        }

    }

}


// Instantiate the game tracker when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
    window.gameTracker = new GameTracker();
});
