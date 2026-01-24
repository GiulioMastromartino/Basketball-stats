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
        this.currentMode = 'draw'; // 'draw' | 'animate' | 'notes'

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
    
    // ... (previous methods: initTools, initHistory, initLayers, initSequence, initEvents, deleteSelected, etc.) ...
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
     * - Swap Pass Sender -> Square (Number Only)
     * - Swap Pass Receiver -> Circle (Ball Holder)
     * - Handle chaining: If Pass starts from Cut End, it uses the cutter token.
     * - Handle receive on cut: If Pass ends at Cut End, it targets the cutter token.
     */
    applyActionsAndClearForNextPhase() {
        const objs = this.canvas.getObjects();
        const tokens = objs.filter(o => o.custom?.kind === 'player-token');
        const arrows = objs.filter(o => o.custom?.kind === 'arrow');

        const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
        const near = (a, b, eps) => dist(a, b) <= eps;

        const TOKEN_ATTACH_EPS = 22; 
        const ARROW_CHAIN_EPS = 10;

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

        // --- Phase 1: Analyze & Plan Updates ---
        // We map Token -> { pos: {x,y}, style: 'circle'|'square' }
        const updates = new Map();

        const getUpdate = (tok) => {
            if (!updates.has(tok)) {
                updates.set(tok, { 
                    pos: tok.getCenterPoint(), 
                    style: tok.custom?.style || 'circle',
                    label: tok.custom?.label || (tok.text || '1'),
                    team: tok.custom?.team || 'offense'
                });
            }
            return updates.get(tok);
        };

        // 1a) Identify Cuts/Dribbles (Movement)
        const cutEnds = []; // Store cut ends to resolve Pass chaining/receiving

        for (const a of arrows) {
            const type = a.custom?.type;
            if (type !== 'cut' && type !== 'dribble') continue;

            const startPt = a.custom.start;
            const endPt = a.custom.end;

            const tok = findConnectedToken(startPt);
            if (tok) {
                const up = getUpdate(tok);
                up.pos = { x: endPt.x, y: endPt.y };
                
                // Track this token's "end location" for chaining/receiving
                cutEnds.push({ 
                    end: endPt, 
                    token: tok,
                    type: type 
                });
            }
        }

        // 1b) Identify Passes (Style Swap)
        for (const a of arrows) {
            if (a.custom?.type !== 'pass') continue;

            let passStart = a.custom.start;
            const passEnd = a.custom.end;
            
            let sender = findConnectedToken(passStart);

            // SENDER CHECK: If no direct sender, check if it chains from a Cut/Dribble
            if (!sender) {
                for (const ce of cutEnds) {
                    if (near(passStart, ce.end, ARROW_CHAIN_EPS)) {
                        sender = ce.token;
                        break;
                    }
                }
            }

            // If we found a sender, they lose the ball -> Square
            if (sender) {
                const up = getUpdate(sender);
                // Only change if it's currently a ball-holder (circle)
                if (up.style === 'circle' || up.style === 'dark-circle') {
                    up.style = 'square';
                }
            }

            // RECEIVER CHECK:
            let receiver = findConnectedToken(passEnd);
            
            // If not found at current position, check if it's a token cutting TO this position
            if (!receiver) {
                for (const ce of cutEnds) {
                    if (near(passEnd, ce.end, ARROW_CHAIN_EPS)) {
                        receiver = ce.token;
                        break;
                    }
                }
            }

            if (receiver) {
                const up = getUpdate(receiver);
                up.style = 'circle'; 
            }
        }

        // --- Phase 2: Execute Updates ---
        
        updates.forEach((data, tok) => {
            // Check if we need to replace the object (style change)
            // or just move it.
            const needsReplacement = (data.style !== (tok.custom?.style));
            
            if (needsReplacement) {
                // Remove old, Create new
                let newTok;
                const commonProps = {
                    left: data.pos.x,
                    top: data.pos.y,
                    originX: 'center',
                    originY: 'center',
                    selectable: true,
                    hasControls: true
                };

                if (data.style === 'circle') {
                    newTok = new fabric.Group([
                        new fabric.Circle({
                            radius: 15, fill: '#ffffff', stroke: '#000000', strokeWidth: 1, originX: 'center', originY: 'center'
                        }),
                        new fabric.Text(data.label, {
                            fontSize: 16, fontFamily: 'Arial', fontWeight: 'bold', originX: 'center', originY: 'center'
                        })
                    ], commonProps);
                } else if (data.style === 'square') {
                    newTok = new fabric.Text(data.label, {
                        ...commonProps,
                        fontSize: 20, fontFamily: 'Arial', fontWeight: 'bold', fill: '#000000'
                    });
                } else {
                     return; 
                }

                // Restore Metadata
                newTok.custom = {
                    kind: 'player-token',
                    team: data.team,
                    label: data.label,
                    style: data.style
                };

                newTok.toObject = (function(toObject) {
                    return function() {
                        return fabric.util.object.extend(toObject.call(this), {
                            custom: { kind: 'player-token', ...this.custom }
                        });
                    };
                })(newTok.toObject);

                this.canvas.remove(tok);
                this.canvas.add(newTok);
                newTok.setCoords();

            } else {
                // Just Move
                tok.set({ left: data.pos.x, top: data.pos.y });
                tok.setCoords();
            }
        });

        // --- Phase 3: Cleanup ---
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
        
        const activeTab = document.getElementById(`tab-${mode}`);
        if(activeTab) activeTab.classList.add('active');
        
        // Handle UI Panels
        const notesPanel = document.getElementById('notes-panel');
        if (notesPanel) {
            notesPanel.style.display = (mode === 'notes') ? 'block' : 'none';
        }
        
        console.log(`Switched to ${mode} mode`);
        
        if (mode === 'animate') {
             if (this.sequence) this.sequence.playAnimation(); 
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
        const descInput = document.getElementById("meta-description");
        const tagsInput = document.getElementById("meta-tags");
        
        const name = nameInput ? nameInput.value : "Untitled Play";
        const type = typeInput ? typeInput.value : "Offense";
        const desc = descInput ? descInput.value : "";
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
                description: desc,
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
                    const descInput = document.getElementById("meta-description");
                    const tagsInput = document.getElementById("meta-tags");
                    
                    if(nameInput) nameInput.value = data.metadata.name || "";
                    if(typeInput) typeInput.value = data.metadata.play_type || "Offense";
                    if(descInput) descInput.value = data.metadata.description || "";
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
