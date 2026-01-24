/**
 * PlayBuilder Core Application
 * Handles canvas initialization, tool management, and API interactions.
 */

class PlayBuilder {
    constructor(canvasId) {
        // Initialize Canvas
        this.canvas = new fabric.Canvas(canvasId, {
            selection: false, 
            preserveObjectStacking: true,
            backgroundColor: '#ffffff'
        });

        // Registry for tools
        this.tools = {};
        this.activeTool = null;

        // Managers
        this.history = null;
        this.layers = null;
        this.sequence = null;
        
        this.isHistoryLocked = false; 

        // Configuration
        this.config = window.PlayBuilderConfig || {};
        
        // Initialize Tools & Managers
        this.initTools();
        this.initHistory();
        this.initLayers();
        this.initSequence(); 
        this.initEvents();

        // Initialize Court (First Draw)
        this.initCourtBackground();

        // Load data if editing
        if (this.config.playId) {
            this.loadPlay(this.config.playId);
        } else {
            console.log("New play initialized");
            this.selectTool('select');
            
            // Initial save state
            setTimeout(() => {
                this.saveStateToHistory(); 
                if (this.sequence && this.sequence.frames.length === 0) {
                     this.sequence.captureCurrentAsFrame("Start");
                }
            }, 200);
        }
    }

    initTools() {
        if (typeof SelectTool !== 'undefined') this.tools['select'] = new SelectTool(this.canvas);
        if (typeof PlayerTool !== 'undefined') this.tools['player'] = new PlayerTool(this.canvas);
        if (typeof ArrowTool !== 'undefined') this.tools['arrow'] = new ArrowTool(this.canvas);
        if (typeof TextTool !== 'undefined') this.tools['text'] = new TextTool(this.canvas);
    }

    initHistory() {
        if (typeof HistoryManager !== 'undefined') {
            this.history = new HistoryManager();
        }
    }
    
    initLayers() {
        if (typeof LayersPanel !== 'undefined') {
            this.layers = new LayersPanel(this.canvas, 'layers-list');
        }
    }
    
    initSequence() {
        if (typeof SequenceManager !== 'undefined') {
            this.sequence = new SequenceManager(this, 'timeline-frames');
        }
    }

    initEvents() {
        // Save Button
        const saveBtn = document.getElementById("save-btn");
        if (saveBtn) {
            saveBtn.addEventListener("click", (e) => {
                e.preventDefault();
                this.savePlay();
            });
        }

        // Canvas Events Delegation to Active Tool
        this.canvas.on('mouse:down', (opt) => {
            if (this.activeTool) this.activeTool.onMouseDown(opt);
        });
        this.canvas.on('mouse:move', (opt) => {
            if (this.activeTool) this.activeTool.onMouseMove(opt);
        });
        this.canvas.on('mouse:up', (opt) => {
            if (this.activeTool) this.activeTool.onMouseUp(opt);
        });

        // Object Events (History & Layers & Sequence)
        const updateAll = (e) => {
             // Ignore if adding court lines (initial load)
             if (e && e.target?.custom?.kind === 'court-line') return;
             
             this.saveStateToHistory();
             if (this.layers) this.layers.refresh();
             if (this.sequence) this.sequence.updateCurrentFrameData();
        };

        this.canvas.on('object:added', updateAll);
        this.canvas.on('object:modified', updateAll);
        this.canvas.on('object:removed', updateAll);
        
        // Selection events for Layers
        this.canvas.on('selection:created', () => { if(this.layers) this.layers.refresh(); });
        this.canvas.on('selection:updated', () => { if(this.layers) this.layers.refresh(); });
        this.canvas.on('selection:cleared', () => { if(this.layers) this.layers.refresh(); });
    }

    saveStateToHistory() {
        if (this.isHistoryLocked || !this.history) return;
        
        const json = JSON.stringify(this.canvas.toJSON(['custom']));
        this.history.pushState(json);
    }

    selectTool(toolId) {
        if (!this.tools[toolId]) {
            console.warn(`Tool ${toolId} not found`);
            return;
        }

        if (this.activeTool) {
            this.activeTool.deactivate();
        }

        // UI Update
        document.querySelectorAll("#tool-select, #tool-player, #tool-arrow, #tool-text").forEach(el => {
            el.classList.remove("active");
        });
        const btn = document.getElementById(`tool-${toolId}`);
        if (btn) btn.classList.add("active");

        // Activate new tool
        this.activeTool = this.tools[toolId];
        this.activeTool.activate();
    }

    async savePlay() {
        const statusSpan = document.getElementById("status-bar");
        statusSpan.innerText = "Saving...";

        const name = document.getElementById("meta-name").value;
        const type = document.getElementById("meta-type").value;
        const tags = document.getElementById("meta-tags").value;

        if (!name) {
            alert("Please enter a Play Name.");
            statusSpan.innerText = "Error: Name required";
            return;
        }

        // Current canvas state is the "thumbnail" or main view
        const canvasJson = this.canvas.toJSON(['custom']);
        
        // Frames data
        const frames = this.sequence ? this.sequence.frames : [];

        const payload = {
            play_id: this.config.playId ? parseInt(this.config.playId) : null,
            metadata: {
                name: name,
                play_type: type,
                tags: tags
            },
            canvas_json: canvasJson,
            frames: frames 
        };
        
        // CSRF Token - using generic method or meta tag
        // Assuming meta tag exists from layout
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');

        try {
            // Updated URL to match the backend prefix registration
            const res = await fetch(`/api/v1/plays/api/save-canvas`, {
                method: "POST",
                headers: { 
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken
                },
                body: JSON.stringify(payload)
            });
            
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            
            const data = await res.json();

            if (data.success) {
                statusSpan.innerText = "Saved!";
                if (!this.config.playId && data.play_id) {
                    window.history.pushState({}, "", `/plays/${data.play_id}/edit-builder`);
                    this.config.playId = data.play_id;
                    document.getElementById("play-id").value = data.play_id;
                }
            } else {
                statusSpan.innerText = "Error: " + data.error;
                alert("Save failed: " + data.error);
            }
        } catch (err) {
            console.error(err);
            statusSpan.innerText = "Network Error";
            alert("Save failed. Check console for details.");
        }
    }

    async loadPlay(playId) {
        const statusSpan = document.getElementById("status-bar");
        statusSpan.innerText = "Loading...";
        
        this.isHistoryLocked = true;

        try {
            // Match the URL structure
            const res = await fetch(`/api/v1/plays/api/load-canvas/${playId}`);
            const data = await res.json();

            if (data.success) {
                if (data.metadata) {
                    document.getElementById("meta-name").value = data.metadata.name || "";
                    document.getElementById("meta-type").value = data.metadata.play_type || "Offense";
                    document.getElementById("meta-tags").value = data.metadata.tags || "";
                }

                if (data.canvas_json) {
                    this.canvas.loadFromJSON(data.canvas_json, () => {
                        // CRITICAL: Re-apply court background after loading
                        // Because the saved JSON might have a blank background from previous bugs
                        this.initCourtBackground();
                        
                        this.canvas.renderAll();
                        statusSpan.innerText = "Ready";
                        this.selectTool('select');
                        
                        this.isHistoryLocked = false;
                        this.saveStateToHistory(); 
                        if(this.layers) this.layers.refresh();
                        
                        if (data.frames && data.frames.length > 0 && this.sequence) {
                             this.sequence.frames = data.frames;
                             this.sequence.currentIndex = 0;
                             this.sequence.renderTimeline();
                        } else if (this.sequence) {
                             this.sequence.captureCurrentAsFrame("Start");
                        }
                    });
                } else {
                    statusSpan.innerText = "Ready (Empty)";
                    this.selectTool('select');
                    this.isHistoryLocked = false;
                    this.saveStateToHistory();
                    if(this.layers) this.layers.refresh();
                    if (this.sequence) this.sequence.captureCurrentAsFrame("Start");
                }
            } else {
                statusSpan.innerText = "Error loading play";
                this.isHistoryLocked = false;
            }
        } catch (err) {
            console.error(err);
            statusSpan.innerText = "Error loading play";
            this.isHistoryLocked = false;
        }
    }

    clearCanvas() {
        if(confirm("Clear all objects?")) {
            const objects = this.canvas.getObjects();
            for (let i = objects.length - 1; i >= 0; i--) {
                const o = objects[i];
                if (o.custom?.kind !== 'court-line') {
                    this.canvas.remove(o);
                }
            }
        }
    }
    
    undo() {
        if (!this.history || !this.history.canUndo()) return;
        
        const prevState = this.history.undo();
        if (prevState) {
            this.isHistoryLocked = true;
            this.canvas.loadFromJSON(prevState, () => {
                this.initCourtBackground(); // Ensure BG persists on undo
                this.canvas.renderAll();
                this.isHistoryLocked = false;
                if(this.layers) this.layers.refresh();
                if(this.sequence) this.sequence.updateCurrentFrameData();
            });
        }
    }

    redo() {
        if (!this.history || !this.history.canRedo()) return;

        const nextState = this.history.redo();
        if (nextState) {
            this.isHistoryLocked = true;
            this.canvas.loadFromJSON(nextState, () => {
                this.initCourtBackground(); // Ensure BG persists on redo
                this.canvas.renderAll();
                this.isHistoryLocked = false;
                if(this.layers) this.layers.refresh();
                if(this.sequence) this.sequence.updateCurrentFrameData();
            });
        }
    }
    
    refreshLayers() { 
        if(this.layers) this.layers.refresh(); 
    }
    
    /**
     * Draw the basketball court background using a static Image.
     */
    initCourtBackground() {
        const strokeColor = '#000000'; 
        const strokeWidth = 2;
        const width = 800;
        const height = 500;
        const margin = 20;

        // Create a temporary static canvas to draw the court
        const tempCanvas = new fabric.StaticCanvas(null, { width: width, height: height });
        tempCanvas.setBackgroundColor('#ffffff', () => {}); 

        // --- Draw logic ---
        const courtObjects = [];
        const baseX = margin;
        const midY = height / 2;
        
        // Sidelines
        courtObjects.push(new fabric.Line([baseX, margin, width - margin, margin], {
            stroke: strokeColor, strokeWidth: strokeWidth
        }));
        courtObjects.push(new fabric.Line([baseX, height - margin, width - margin, height - margin], {
            stroke: strokeColor, strokeWidth: strokeWidth
        }));
        // Baseline
        courtObjects.push(new fabric.Line([baseX, margin, baseX, height - margin], {
            stroke: strokeColor, strokeWidth: strokeWidth
        }));
        
        // Key
        const keyWidth = 190;
        const keyHeight = 160;
        const keyTop = midY - (keyHeight / 2);
        courtObjects.push(new fabric.Rect({
            left: baseX, top: keyTop,
            width: keyWidth, height: keyHeight,
            fill: 'transparent', stroke: strokeColor, strokeWidth: strokeWidth
        }));
        
        // FT Circle
        const ftRadius = 60;
        courtObjects.push(new fabric.Circle({
            left: baseX + keyWidth - ftRadius, top: midY - ftRadius,
            radius: ftRadius,
            fill: 'transparent', stroke: strokeColor, strokeWidth: strokeWidth
        }));

        // Hoop
        const hoopOffset = 40; 
        const hoopRadius = 8;
        courtObjects.push(new fabric.Line([baseX + hoopOffset - 10, midY - 30, baseX + hoopOffset - 10, midY + 30], {
             stroke: strokeColor, strokeWidth: strokeWidth
        }));
        courtObjects.push(new fabric.Circle({
            left: baseX + hoopOffset - hoopRadius, top: midY - hoopRadius,
            radius: hoopRadius,
            fill: 'transparent', stroke: strokeColor, strokeWidth: strokeWidth
        }));
        
        // 3-Point
        const cornerDist = 140; 
        const threePtRadius = 240; 
        const topCornerY = margin + 40;
        const botCornerY = height - margin - 40;
        const path = `M ${baseX} ${topCornerY} ` +
                     `L ${baseX + cornerDist} ${topCornerY} ` + 
                     `Q ${baseX + threePtRadius + 100} ${midY} ${baseX + cornerDist} ${botCornerY} ` +
                     `L ${baseX} ${botCornerY}`;
        courtObjects.push(new fabric.Path(path, {
            fill: 'transparent', stroke: strokeColor, strokeWidth: strokeWidth
        }));

        // Mid Court
        const midX = 750;
        courtObjects.push(new fabric.Line([midX, margin, midX, height - margin], {
             stroke: strokeColor, strokeWidth: strokeWidth
        }));
        courtObjects.push(new fabric.Path(`M ${midX} ${midY - 60} A 60 60 0 0 0 ${midX} ${midY + 60}`, {
             fill: 'transparent', stroke: strokeColor, strokeWidth: strokeWidth
        }));
        
        courtObjects.forEach(o => tempCanvas.add(o));
        tempCanvas.renderAll();
        
        const courtDataURL = tempCanvas.toDataURL({
            format: 'png',
            quality: 1,
            enableRetinaScaling: false 
        });
        
        this.canvas.setBackgroundImage(courtDataURL, this.canvas.renderAll.bind(this.canvas), {
            originX: 'left',
            originY: 'top',
            left: 0,
            top: 0
        });
        
        console.log("Court background set/restored via DataURL");
    }
}

document.addEventListener("DOMContentLoaded", () => {
    window.app = new PlayBuilder("playCanvas");
});
