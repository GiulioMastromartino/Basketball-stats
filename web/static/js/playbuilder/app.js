/**
 * PlayBuilder Core Application
 * Handles canvas initialization, tool management, and API interactions.
 */

class PlayBuilder {
    constructor(canvasId) {
        this.canvas = new fabric.Canvas(canvasId, {
            selection: false, 
            preserveObjectStacking: true,
            backgroundColor: '#ffffff' // Set default
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
        
        // Initialize - Order is critical
        this.initCourt(); 
        
        // Render immediately
        this.canvas.requestRenderAll();
        
        this.initTools();
        this.initHistory();
        this.initLayers();
        this.initSequence(); 
        this.initEvents();

        // Load data if editing
        if (this.config.playId) {
            this.loadPlay(this.config.playId);
        } else {
            console.log("New play initialized");
            this.selectTool('select');
            
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
        
        // CSRF Token
        const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

        try {
            const res = await fetch(`${this.config.apiBase}/plays/api/save-canvas`, {
                method: "POST",
                headers: { 
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken
                },
                body: JSON.stringify(payload)
            });
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
        }
    }

    async loadPlay(playId) {
        const statusSpan = document.getElementById("status-bar");
        statusSpan.innerText = "Loading...";
        
        this.isHistoryLocked = true;

        try {
            const res = await fetch(`${this.config.apiBase}/plays/api/load-canvas/${playId}`);
            const data = await res.json();

            if (data.success) {
                if (data.metadata) {
                    document.getElementById("meta-name").value = data.metadata.name || "";
                    document.getElementById("meta-type").value = data.metadata.play_type || "Offense";
                    document.getElementById("meta-tags").value = data.metadata.tags || "";
                }

                if (data.canvas_json) {
                    this.canvas.loadFromJSON(data.canvas_json, () => {
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
     * Draw the basketball court background (Half Court).
     * Uses setBackgroundColor for white background.
     * Adds individual line objects.
     */
    initCourt() {
        const strokeColor = '#000000'; 
        const strokeWidth = 2;
        const width = 800;
        const height = 500;
        const margin = 20;

        // Force white opaque background
        this.canvas.setBackgroundColor('#ffffff', this.canvas.renderAll.bind(this.canvas));

        const courtObjects = [];

        // 2. Court Boundaries
        const baseX = margin;
        const midY = height / 2;
        
        // Sidelines
        courtObjects.push(new fabric.Line([baseX, margin, width - margin, margin], {
            stroke: strokeColor, strokeWidth: strokeWidth, selectable: false, evented: false
        }));
        courtObjects.push(new fabric.Line([baseX, height - margin, width - margin, height - margin], {
            stroke: strokeColor, strokeWidth: strokeWidth, selectable: false, evented: false
        }));
        // Baseline
        courtObjects.push(new fabric.Line([baseX, margin, baseX, height - margin], {
            stroke: strokeColor, strokeWidth: strokeWidth, selectable: false, evented: false
        }));
        
        // 3. The Key
        const keyWidth = 190;
        const keyHeight = 160;
        const keyTop = midY - (keyHeight / 2);
        
        courtObjects.push(new fabric.Rect({
            left: baseX, top: keyTop,
            width: keyWidth, height: keyHeight,
            fill: 'transparent', stroke: strokeColor, strokeWidth: strokeWidth,
            selectable: false, evented: false
        }));
        
        // Free Throw Circle
        const ftRadius = 60;
        courtObjects.push(new fabric.Circle({
            left: baseX + keyWidth - ftRadius, top: midY - ftRadius,
            radius: ftRadius,
            fill: 'transparent', stroke: strokeColor, strokeWidth: strokeWidth,
            selectable: false, evented: false
        }));

        // 4. Hoop & Backboard
        const hoopOffset = 40; 
        const hoopRadius = 8;
        
        // Backboard
        courtObjects.push(new fabric.Line([baseX + hoopOffset - 10, midY - 30, baseX + hoopOffset - 10, midY + 30], {
             stroke: strokeColor, strokeWidth: strokeWidth, selectable: false, evented: false
        }));
        // Hoop
        courtObjects.push(new fabric.Circle({
            left: baseX + hoopOffset - hoopRadius, top: midY - hoopRadius,
            radius: hoopRadius,
            fill: 'transparent', stroke: strokeColor, strokeWidth: strokeWidth,
            selectable: false, evented: false
        }));
        
        // 5. 3-Point Line
        const cornerDist = 140; 
        const threePtRadius = 240; 
        const topCornerY = margin + 40;
        const botCornerY = height - margin - 40;
        
        const path = `M ${baseX} ${topCornerY} ` +
                     `L ${baseX + cornerDist} ${topCornerY} ` + 
                     `Q ${baseX + threePtRadius + 100} ${midY} ${baseX + cornerDist} ${botCornerY} ` +
                     `L ${baseX} ${botCornerY}`;
                     
        courtObjects.push(new fabric.Path(path, {
            fill: 'transparent', stroke: strokeColor, strokeWidth: strokeWidth,
            selectable: false, evented: false
        }));

        // 6. Mid Court Line
        const midX = 750;
        courtObjects.push(new fabric.Line([midX, margin, midX, height - margin], {
             stroke: strokeColor, strokeWidth: strokeWidth, selectable: false, evented: false
        }));
        // Center Circle
        courtObjects.push(new fabric.Path(`M ${midX} ${midY - 60} A 60 60 0 0 0 ${midX} ${midY + 60}`, {
             fill: 'transparent', stroke: strokeColor, strokeWidth: strokeWidth,
             selectable: false, evented: false
        }));

        // Add objects individually
        courtObjects.forEach(obj => {
            obj.toObject = (function(toObject) {
                return function() {
                    return fabric.util.object.extend(toObject.call(this), {
                        custom: { kind: 'court-line' }
                    });
                };
            })(obj.toObject);
            obj.custom = { kind: 'court-line' };
            
            this.canvas.add(obj);
        });

        console.log("InitCourt finished. Canvas Objects:", this.canvas.getObjects().length);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    window.app = new PlayBuilder("playCanvas");
});
