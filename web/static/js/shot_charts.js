/**
 * Shot Chart Visualization Module
 * Renders basketball shot charts with court mapping, hexbins, and heatmaps
 */

class ShotChart {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        this.options = {
            width: options.width || 500,
            height: options.height || 470,
            courtImage: options.courtImage || '/static/images/basketball-court.svg',
            ...options
        };
        
        this.shots = [];
        this.canvas = null;
        this.ctx = null;
        
        this.init();
    }
    
    init() {
        // Create canvas element
        this.canvas = document.createElement('canvas');
        this.canvas.width = this.options.width;
        this.canvas.height = this.options.height;
        this.canvas.style.border = '1px solid #ccc';
        this.canvas.style.background = '#f8f9fa';
        
        this.ctx = this.canvas.getContext('2d');
        
        // Load court background
        this.loadCourtBackground();
        
        this.container.appendChild(this.canvas);
    }
    
    async loadCourtBackground() {
        const img = new Image();
        img.onload = () => {
            this.courtImage = img;
            this.render();
        };
        img.src = this.options.courtImage;
    }
    
    loadShots(shots) {
        this.shots = shots;
        this.render();
    }
    
    render() {
        if (!this.ctx) return;
        
        // Clear canvas
        this.ctx.clearRect(0, 0, this.options.width, this.options.height);
        
        // Draw court background
        if (this.courtImage) {
            this.ctx.drawImage(this.courtImage, 0, 0, this.options.width, this.options.height);
        }
        
        // Draw shots
        this.shots.forEach(shot => this.drawShot(shot));
    }
    
    drawShot(shot) {
        // **FIX: Handle FTs separately or place them at the line**
        let x, y;
        
        if (shot.shot_type === 'ft') {
            // Place Free Throws at the line (approx y=190 for 15ft)
            x = 250;
            y = 190;
        } else {
            // Default to mid-paint if missing (250, 235)
            x = shot.x_loc !== null ? shot.x_loc : 250;
            y = shot.y_loc !== null ? shot.y_loc : 235;
        }

        const made = shot.result === 'made';
        
        // Draw shot marker
        this.ctx.beginPath();
        this.ctx.arc(x, y, 8, 0, Math.PI * 2);
        
        if (made) {
            this.ctx.fillStyle = 'rgba(40, 167, 69, 0.8)'; // Green for made
            this.ctx.fill();
        } else {
            this.ctx.strokeStyle = 'rgba(220, 53, 69, 0.8)'; // Red for missed
            this.ctx.lineWidth = 2;
            this.ctx.stroke();
        }
        
        // Add point value label
        if (shot.points) {
            this.ctx.fillStyle = made ? '#fff' : '#dc3545';
            this.ctx.font = 'bold 10px Arial';
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';
            this.ctx.fillText(shot.points.toString(), x, y);
        }
    }
    
    clearShots() {
        this.shots = [];
        this.render();
    }
    
    downloadImage(filename = 'shot-chart.png') {
        const link = document.createElement('a');
        link.download = filename;
        link.href = this.canvas.toDataURL('image/png');
        link.click();
    }
}


/**
 * Hexbin Shot Chart Visualization
 * Groups shots into hexagonal bins for density visualization
 */
class HexbinShotChart extends ShotChart {
    constructor(containerId, options = {}) {
        super(containerId, options);
        this.hexSize = options.hexSize || 30;
        this.colorScale = options.colorScale || this.defaultColorScale;
    }
    
    defaultColorScale(value) {
        // Color scale from blue (cold) to red (hot)
        if (value < 0.3) return 'rgba(0, 0, 255, 0.5)';
        if (value < 0.4) return 'rgba(0, 255, 255, 0.5)';
        if (value < 0.5) return 'rgba(0, 255, 0, 0.5)';
        if (value < 0.6) return 'rgba(255, 255, 0, 0.5)';
        return 'rgba(255, 0, 0, 0.5)';
    }
    
    render() {
        if (!this.ctx) return;
        
        // Clear canvas
        this.ctx.clearRect(0, 0, this.options.width, this.options.height);
        
        // Draw court background
        if (this.courtImage) {
            this.ctx.drawImage(this.courtImage, 0, 0, this.options.width, this.options.height);
        }
        
        // Calculate hexbins
        const hexbins = this.calculateHexbins();
        
        // Draw hexbins
        hexbins.forEach(hex => this.drawHexbin(hex));
        
        // Draw legend
        this.drawLegend();
    }
    
    calculateHexbins() {
        const hexSize = this.hexSize;
        const bins = new Map();
        
        // Group shots into hexagonal bins
        this.shots.forEach(shot => {
            if (shot.x_loc === null || shot.y_loc === null) return;
            
            // Convert to hexagonal grid coordinates
            const col = Math.round(shot.x_loc / (hexSize * 1.5));
            const row = Math.round(shot.y_loc / (hexSize * Math.sqrt(3)));
            
            const key = `${col},${row}`;
            
            if (!bins.has(key)) {
                bins.set(key, {
                    x: col * hexSize * 1.5,
                    y: row * hexSize * Math.sqrt(3),
                    makes: 0,
                    attempts: 0,
                    points: 0
                });
            }
            
            const bin = bins.get(key);
            bin.attempts++;
            bin.points += shot.points || 0;
            if (shot.result === 'made') bin.makes++;
        });
        
        // Calculate FG% for each bin
        return Array.from(bins.values()).map(bin => ({
            ...bin,
            fgPct: bin.attempts > 0 ? bin.makes / bin.attempts : 0,
            pps: bin.attempts > 0 ? bin.points / bin.attempts : 0
        }));
    }
    
    drawHexbin(hex) {
        const size = this.hexSize;
        const x = hex.x;
        const y = hex.y;
        
        // Draw hexagon
        this.ctx.beginPath();
        for (let i = 0; i < 6; i++) {
            const angle = (Math.PI / 3) * i;
            const hx = x + size * Math.cos(angle);
            const hy = y + size * Math.sin(angle);
            
            if (i === 0) {
                this.ctx.moveTo(hx, hy);
            } else {
                this.ctx.lineTo(hx, hy);
            }
        }
        this.ctx.closePath();
        
        // Fill based on FG%
        this.ctx.fillStyle = this.colorScale(hex.fgPct);
        this.ctx.fill();
        
        // Draw border
        this.ctx.strokeStyle = 'rgba(0, 0, 0, 0.2)';
        this.ctx.lineWidth = 1;
        this.ctx.stroke();
        
        // Draw percentage label if enough attempts
        if (hex.attempts >= 3) {
            this.ctx.fillStyle = '#000';
            this.ctx.font = 'bold 10px Arial';
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';
            this.ctx.fillText(`${Math.round(hex.fgPct * 100)}%`, x, y);
        }
    }
    
    drawLegend() {
        const legendX = 10;
        const legendY = this.options.height - 30;
        
        this.ctx.font = '12px Arial';
        this.ctx.fillStyle = '#333';
        this.ctx.textAlign = 'left';
        this.ctx.fillText('FG%: ', legendX, legendY);
        
        const colors = [
            { label: '<30%', color: 'rgba(0, 0, 255, 0.5)' },
            { label: '30-40%', color: 'rgba(0, 255, 255, 0.5)' },
            { label: '40-50%', color: 'rgba(0, 255, 0, 0.5)' },
            { label: '50-60%', color: 'rgba(255, 255, 0, 0.5)' },
            { label: '>60%', color: 'rgba(255, 0, 0, 0.5)' }
        ];
        
        colors.forEach((c, i) => {
            const x = legendX + 50 + i * 70;
            this.ctx.fillStyle = c.color;
            this.ctx.fillRect(x, legendY - 10, 15, 15);
            this.ctx.fillStyle = '#333';
            this.ctx.fillText(c.label, x + 20, legendY);
        });
    }
}


/**
 * Zone Heatmap Visualization
 * Shows shooting efficiency by court zone
 */
class ZoneHeatmap {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        this.options = {
            width: options.width || 500,
            height: options.height || 470,
            ...options
        };
        
        this.zones = {};
        this.init();
    }
    
    init() {
        // Create zone display
        // **FIX: Added Free Throw zone**
        this.container.innerHTML = `
            <div class="zone-heatmap">
                <div class="zone-grid">
                    <div class="zone zone-corner-3-left" data-zone="Corner_3">
                        <span class="zone-name">Corner 3</span>
                        <span class="zone-stats"></span>
                    </div>
                    <div class="zone zone-above-break" data-zone="Above_Break_3">
                        <span class="zone-name">Above Break 3</span>
                        <span class="zone-stats"></span>
                    </div>
                    <div class="zone zone-corner-3-right" data-zone="Corner_3">
                        <span class="zone-name">Corner 3</span>
                        <span class="zone-stats"></span>
                    </div>
                    <div class="zone zone-midrange" data-zone="Midrange">
                        <span class="zone-name">Midrange</span>
                        <span class="zone-stats"></span>
                    </div>
                    <div class="zone zone-paint" data-zone="Paint">
                        <span class="zone-name">Paint</span>
                        <span class="zone-stats"></span>
                    </div>
                    <div class="zone zone-rim" data-zone="Rim">
                        <span class="zone-name">Rim</span>
                        <span class="zone-stats"></span>
                    </div>
                    <div class="zone zone-ft" data-zone="FT">
                        <span class="zone-name">Free Throw</span>
                        <span class="zone-stats"></span>
                    </div>
                </div>
                <div class="zone-legend">
                    <span class="legend-item cold">Below Avg</span>
                    <span class="legend-item avg">Average</span>
                    <span class="legend-item hot">Above Avg</span>
                </div>
            </div>
        `;
    }
    
    loadZoneData(zones) {
        this.zones = zones;
        this.render();
    }
    
    render() {
        Object.entries(this.zones).forEach(([zoneName, stats]) => {
            const zoneEl = this.container.querySelector(`[data-zone="${zoneName}"]`);
            if (!zoneEl) return;
            
            const statsEl = zoneEl.querySelector('.zone-stats');
            if (statsEl) {
                statsEl.innerHTML = `
                    <div class="fg-pct">${stats.fg_pct || 0}%</div>
                    <div class="attempts">${stats.attempts || 0} att</div>
                    <div class="pps">${stats.actual_pps || 0} PPS</div>
                `;
            }
            
            // Color based on efficiency vs expected
            const delta = stats.efficiency_delta || 0;
            if (delta > 0.1) {
                zoneEl.classList.add('hot');
                zoneEl.classList.remove('cold');
            } else if (delta < -0.1) {
                zoneEl.classList.add('cold');
                zoneEl.classList.remove('hot');
            } else {
                zoneEl.classList.remove('hot', 'cold');
            }
        });
    }
}


/**
 * Shot Chart Manager
 * Handles API calls and chart interactions
 */
class ShotChartManager {
    constructor(options = {}) {
        this.options = options;
        this.shotChart = null;
        this.hexbinChart = null;
        this.zoneHeatmap = null;
        this.currentFilters = {
            player: null,
            game_id: null,
            play_id: null,
            game_type: 'ALL'
        };
    }
    
    async init() {
        // Initialize charts
        this.shotChart = new ShotChart('shot-chart-container', this.options);
        this.hexbinChart = new HexbinShotChart('hexbin-chart-container', this.options);
        this.zoneHeatmap = new ZoneHeatmap('zone-heatmap-container', this.options);
        
        // Load initial data
        await this.loadShots();
        
        // Setup filter handlers
        this.setupFilters();
    }
    
    async loadShots() {
        try {
            const params = new URLSearchParams();
            if (this.currentFilters.player) params.append('player', this.currentFilters.player);
            if (this.currentFilters.game_id) params.append('game_id', this.currentFilters.game_id);
            if (this.currentFilters.play_id) params.append('play_id', this.currentFilters.play_id);
            params.append('game_type', this.currentFilters.game_type);
            
            const response = await fetch(`/api/advanced/shots/chart?${params}`);
            const data = await response.json();
            
            this.shotChart.loadShots(data.shots);
            this.hexbinChart.loadShots(data.shots);
            
            // Load heatmap data
            const heatmapResponse = await fetch(`/api/advanced/shots/heatmap?${params}`);
            const heatmapData = await heatmapResponse.json();
            this.zoneHeatmap.loadZoneData(heatmapData.heatmap);
            
        } catch (error) {
            console.error('Error loading shots:', error);
        }
    }
    
    setupFilters() {
        // Player filter
        const playerSelect = document.getElementById('player-filter');
        if (playerSelect) {
            playerSelect.addEventListener('change', (e) => {
                this.currentFilters.player = e.target.value || null;
                this.loadShots();
            });
        }
        
        // Game type filter
        const gameTypeSelect = document.getElementById('game-type-filter');
        if (gameTypeSelect) {
            gameTypeSelect.addEventListener('change', (e) => {
                this.currentFilters.game_type = e.target.value;
                this.loadShots();
            });
        }
        
        // Play filter
        const playSelect = document.getElementById('play-filter');
        if (playSelect) {
            playSelect.addEventListener('change', (e) => {
                this.currentFilters.play_id = e.target.value || null;
                this.loadShots();
            });
        }
    }
    
    setFilter(filterName, value) {
        this.currentFilters[filterName] = value;
        this.loadShots();
    }
}


// Export for use in templates
window.ShotChart = ShotChart;
window.HexbinShotChart = HexbinShotChart;
window.ZoneHeatmap = ZoneHeatmap;
window.ShotChartManager = ShotChartManager;
