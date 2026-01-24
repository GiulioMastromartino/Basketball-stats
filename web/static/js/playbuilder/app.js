/**
 * PlayBuilder Core Application
 * Handles canvas initialization, tool management, and API interactions.
 */

class PlayBuilder {
    constructor(canvasId) {
        // ... (previous constructor code) ...
        // Initialize Canvas
        this.canvas = new fabric.Canvas(canvasId, {
            selection: false, 
            preserveObjectStacking: true,
            enableRetinaScaling: false,
            backgroundColor: 'rgba(0,0,0,0)'  // Transparent to show CSS background
        });

        // Registry for tools
        this.tools = {};
        this.activeTool = null;

        // Managers
        this.history = null;
        this.layers = null;
        this.sequence = null;
        
        this.isHistoryLocked = false; 
        this.currentMode = 'draw'; // 'draw' | 'animate'

        // Configuration
        this.config = window.PlayBuilderConfig || {};
        
        // Initialize Tools & Managers
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
            
            // Initial save state
            setTimeout(() => {
                this.saveStateToHistory(); 
                if (this.sequence && this.sequence.frames.length === 0) {
                     this.sequence.captureCurrentAsFrame("Start");
                }
            }, 200);
        }
    }
    
    // ... (previous methods: initTools, initHistory, initLayers, initSequence) ...

    initTools() {
        if (typeof SelectTool !== 'undefined') this.tools['select'] = new SelectTool(this.canvas);
        if (typeof PlayerTool !== 'undefined') this.tools['player'] = new PlayerTool(this.canvas);
        if (typeof ArrowTool !== 'undefined') this.tools['arrow'] = new ArrowTool(this.canvas);
        if (typeof TextTool !== 'undefined') this.tools['text'] = new TextTool(this.canvas);
        if (typeof ShapeTool !== 'undefined') this.tools['shape'] = new ShapeTool(this.canvas);
        if (typeof ImageTool !== 'undefined') this.tools['image'] = new ImageTool(this.canvas);
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
        
        // Delete key handling
        document.addEventListener('keydown', (e) => {
            if ((e.key === 'Delete' || e.key === 'Backspace') && this.canvas.getActiveObject()) {
                // Prevent backspace from navigating back if not in an input
                const tag = e.target.tagName.toLowerCase();
                if (tag !== 'input' && tag !== 'textarea') {
                    this.deleteSelected();
                }
            }
        });

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
             this.saveStateToHistory();
             if (this.layers) this.layers.refresh();
             if (this.sequence) this.sequence.updateCurrentFrameData();
        };

        this.canvas.on('object:added', updateAll);
        this.canvas.on('object:modified', updateAll);
        this.canvas.on('object:removed', updateAll);
        
        // Selection events for Layers & UI Overlay
        const onSelectionChange = () => {
             if(this.layers) this.layers.refresh();
             this.updateSelectionUI();
        };

        this.canvas.on('selection:created', onSelectionChange);
        this.canvas.on('selection:updated', onSelectionChange);
        this.canvas.on('selection:cleared', onSelectionChange);
    }
    
    updateSelectionUI() {
        const overlay = document.getElementById('delete-overlay');
        const activeObj = this.canvas.getActiveObject();
        
        if (activeObj && overlay) {
            overlay.style.display = 'block';
        } else if (overlay) {
            overlay.style.display = 'none';
        }
    }
    
    deleteSelected() {
        const activeObj = this.canvas.getActiveObject();
        if (activeObj) {
            // If multiple objects are selected
            if (activeObj.type === 'activeSelection') {
                activeObj.forEachObject(obj => {
                    this.canvas.remove(obj);
                });
                this.canvas.discardActiveObject();
            } else {
                this.canvas.remove(activeObj);
            }
            this.canvas.requestRenderAll();
        }
    }

    /**
     * Apply phase rules:
     * - Move tokens only when action is connected to a token
     * - For passes: swap "number-only" token into circled-number token at the end
     * - If pass starts from end of a cut, treat it as the cut continuation (pass start becomes cut start)
     * - Delete all action arrows after applying (clean next phase)
     */
    applyActionsAndClearForNextPhase() {
        const objs = this.canvas.getObjects();

        // Collect tokens and arrows
        const tokens = objs.filter(o => o.custom?.kind === 'player-token');
        const arrows = objs.filter(o => o.custom?.kind === 'arrow');

        const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
        const near = (a, b, eps) => dist(a, b) <= eps;

        const TOKEN_ATTACH_EPS = 22; // how close must a line endpoint be to count as "connected" to a token
        const ARROW_CHAIN_EPS = 10;  // how close to chain pass start to cut end

        const getTokenCenter = (tok) => tok.getCenterPoint();

        const findConnectedToken = (pt) => {
            let best = null;
            let bestD = TOKEN_ATTACH_EPS;
            for (const tok of tokens) {
                const c = getTokenCenter(tok);
                const d = dist(c, pt);
                if (d <= bestD) {
                    best = tok;
                    bestD = d;
                }
            }
            return best;
        };

        // 1) Build quick index of cut ends (for pass chaining)
        const cutEnds = arrows
            .filter(a => a.custom?.type === 'cut')
            .map(a => ({ arrow: a, end: a.custom.end, start: a.custom.start }));

        // 2) Apply movement actions (cut/dribble) ONLY if connected to a token
        for (const a of arrows) {
            const type = a.custom?.type;
            if (type !== 'cut' && type !== 'dribble') continue;

            const startPt = a.custom.start;
            const endPt = a.custom.end;

            const tok = findConnectedToken(startPt);
            if (!tok) continue; // safer: only move if action is connected

            tok.set({ left: endPt.x, top: endPt.y });
            tok.setCoords();
        }

        // 3) Apply pass visuals rule: at end of pass, swap number-only token -> circled token
        // Also: if pass starts from end of a cut, treat it as cut continuation (pass start = cut start)
        for (const a of arrows) {
            if (a.custom?.type !== 'pass') continue;

            let passStart = a.custom.start;
            const passEnd = a.custom.end;

            // If pass starts at cut end, use cut start for "connection" evaluation (combine)
            for (const ce of cutEnds) {
                if (near(passStart, ce.end, ARROW_CHAIN_EPS)) {
                    passStart = ce.start;
                    break;
                }
            }

            // Find the receiver token connected to pass end
            const receiver = findConnectedToken(passEnd);
            if (!receiver) continue;

            // Swap number-only (square style) -> circled number
            if (receiver.custom?.style === 'square' && receiver.type === 'text') {
                const label = receiver.text || receiver.custom?.label || '';
                const center = receiver.getCenterPoint();

                const newTok = new fabric.Group([
                    new fabric.Circle({
                        radius: 15, fill: '#ffffff', stroke: '#000000', strokeWidth: 1, originX: 'center', originY: 'center'
                    }),
                    new fabric.Text(label, {
                        fontSize: 16, fontFamily: 'Arial', fontWeight: 'bold', originX: 'center', originY: 'center'
                    })
                ], {
                    left: center.x,
                    top: center.y,
                    originX: 'center',
                    originY: 'center',
                    selectable: true,
                    hasControls: true
                });

                // Preserve custom metadata
                newTok.custom = {
                    kind: 'player-token',
                    team: receiver.custom?.team,
                    label: receiver.custom?.label || label,
                    style: 'circle'
                };

                // Preserve serialization of custom
                newTok.toObject = (function(toObject) {
                    return function() {
                        return fabric.util.object.extend(toObject.call(this), {
                            custom: { kind: 'player-token', ...this.custom }
                        });
                    };
                })(newTok.toObject);

                this.canvas.remove(receiver);
                this.canvas.add(newTok);
                newTok.setCoords();
            }
        }

        // 4) Delete all actions (arrows) for the next phase
        arrows.forEach(a => this.canvas.remove(a));

        this.canvas.discardActiveObject();
        this.canvas.requestRenderAll();
    }

    // ... (rest of the methods: setMode, saveStateToHistory, selectTool, clearCanvas, mirror, undo, redo, savePlay, loadPlay) ...
    setMode(mode) {
        this.currentMode = mode;
        
        // Update UI Tabs
        document.querySelectorAll('.nav-tab-item').forEach(el => {
            el.classList.remove('active');
        });
        // Find tab matching mode (simple implementation based on index/text or add data-mode to HTML)
        // For now, assume drawing is default
        
        console.log(`Switched to ${mode} mode`);
        
        if (mode === 'animate') {
             if (this.sequence) this.sequence.playAnimation(); // Example
        } else {
             if (this.sequence) this.sequence.stopAnimation();
        }
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
    
    clearCanvas() {
        if(confirm("Clear all objects?")) {
            this.isHistoryLocked = true;
            this.canvas.clear();
            // Retain background if set manually, or just clear objects
            this.canvas.backgroundColor = 'rgba(0,0,0,0)'; 
            
            this.isHistoryLocked = false;
            this.saveStateToHistory();
            if(this.layers) this.layers.refresh();
        }
    }
    
    mirror() {
        if (!this.canvas) return;
        
        const width = this.canvas.getWidth();
        const center = width / 2;
        
        // Save state before modification
        this.saveStateToHistory();

        this.canvas.getObjects().forEach(obj => {
            // Calculate new left position for originX=center
            if (obj.originX === 'center') {
                obj.set('left', width - obj.left);
            } else {
                // If originX is left
                obj.set('left', width - (obj.left + obj.getScaledWidth()));
            }

            // Mirror angle
            if (obj.angle !== 0) {
                obj.set('angle', -obj.angle);
            }
            
            obj.setCoords();
        });
        
        this.canvas.renderAll();
        // Trigger updates manually since we modified existing objects in batch
        // and we might be inside a bulk operation
        this.saveStateToHistory();
        if(this.layers) this.layers.refresh();
        if(this.sequence) this.sequence.updateCurrentFrameData();
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

    async savePlay() {
        const statusSpan = document.getElementById("status-bar");
        if(statusSpan) statusSpan.innerText = "Saving...";

        const nameInput = document.getElementById("meta-name");
        const typeInput = document.getElementById("meta-type");
        const tagsInput = document.getElementById("meta-tags");
        
        const name = nameInput ? nameInput.value : "Untitled Play";
        const type = typeInput ? typeInput.value : "Offense";
        const tags = tagsInput ? tagsInput.value : "";

        if (!name) {
            alert("Please enter a Play Name.");
            if(statusSpan) statusSpan.innerText = "Error: Name required";
            return;
        }

        // Current canvas state
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
        
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');

        try {
            const res = await fetch(`${this.config.apiBase}/plays/api/save-canvas`, {
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
                if(statusSpan) statusSpan.innerText = "Saved!";
                if (!this.config.playId && data.play_id) {
                    window.history.pushState({}, "", `/plays/${data.play_id}/edit-builder`);
                    this.config.playId = data.play_id;
                    const idField = document.getElementById("play-id");
                    if(idField) idField.value = data.play_id;
                }
            } else {
                if(statusSpan) statusSpan.innerText = "Error: " + data.error;
                alert("Save failed: " + data.error);
            }
        } catch (err) {
            console.error(err);
            if(statusSpan) statusSpan.innerText = "Network Error";
            alert("Save failed. Check console for details.");
        }
    }

    async loadPlay(playId) {
        const statusSpan = document.getElementById("status-bar");
        if(statusSpan) statusSpan.innerText = "Loading...";
        
        this.isHistoryLocked = true;

        try {
            const res = await fetch(`${this.config.apiBase}/plays/api/load-canvas/${playId}`);
            const data = await res.json();

            if (data.success) {
                if (data.metadata) {
                    const nameInput = document.getElementById("meta-name");
                    const typeInput = document.getElementById("meta-type");
                    const tagsInput = document.getElementById("meta-tags");
                    
                    if(nameInput) nameInput.value = data.metadata.name || "";
                    if(typeInput) typeInput.value = data.metadata.play_type || "Offense";
                    if(tagsInput) tagsInput.value = data.metadata.tags || "";
                }

                if (data.canvas_json) {
                    this.canvas.loadFromJSON(data.canvas_json, () => {
                        this.canvas.renderAll();
                        if(statusSpan) statusSpan.innerText = "Ready";
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
                    if(statusSpan) statusSpan.innerText = "Ready (Empty)";
                    this.selectTool('select');
                    this.isHistoryLocked = false;
                    this.saveStateToHistory();
                    if(this.layers) this.layers.refresh();
                    if (this.sequence) this.sequence.captureCurrentAsFrame("Start");
                }
            } else {
                if(statusSpan) statusSpan.innerText = "Error loading play";
                this.isHistoryLocked = false;
            }
        } catch (err) {
            console.error(err);
            if(statusSpan) statusSpan.innerText = "Error loading play";
            this.isHistoryLocked = false;
        }
    }
}

document.addEventListener("DOMContentLoaded", () => {
    window.app = new PlayBuilder("playCanvas");
});
