/**
 * PlayBuilder Core Application
 * Handles canvas initialization, tool management, and API interactions.
 */

class PlayBuilder {
    constructor(canvasId) {
        this.canvas = new fabric.Canvas(canvasId, {
            selection: false, // Default false, enabled by SelectTool
            preserveObjectStacking: true,
            backgroundColor: '#ffffff'
        });

        // Registry for tools
        this.tools = {};
        this.activeTool = null;

        // History
        this.history = null;
        this.isHistoryLocked = false; // Prevent save during undo/redo

        // Configuration
        this.config = window.PlayBuilderConfig || {};
        
        // Initialize
        this.initCourt();
        this.initTools();
        this.initHistory();
        this.initEvents();

        // Load data if editing
        if (this.config.playId) {
            this.loadPlay(this.config.playId);
        } else {
            console.log("New play initialized");
            this.selectTool('select');
            this.saveStateToHistory(); // Initial state
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
        } else {
            console.warn("HistoryManager not loaded");
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

        // History Events
        this.canvas.on('object:added', (e) => {
             // Ignore if adding court lines (initial load)
             if (e.target?.custom?.kind === 'court-line') return;
             this.saveStateToHistory();
        });
        this.canvas.on('object:modified', () => this.saveStateToHistory());
        this.canvas.on('object:removed', () => this.saveStateToHistory());
    }

    saveStateToHistory() {
        if (this.isHistoryLocked || !this.history) return;
        
        // Serialize
        const json = JSON.stringify(this.canvas.toJSON(['custom']));
        this.history.pushState(json);
    }

    /**
     * Switch the active tool.
     * @param {string} toolId 
     */
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

        const canvasJson = this.canvas.toJSON(['custom']);

        const payload = {
            play_id: this.config.playId ? parseInt(this.config.playId) : null,
            metadata: {
                name: name,
                play_type: type,
                tags: tags
            },
            canvas_json: canvasJson
        };

        try {
            const res = await fetch(`${this.config.apiBase}/plays/api/save-canvas`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
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
        
        // Lock history during load
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
                        
                        // Initial history state after load
                        this.isHistoryLocked = false;
                        this.saveStateToHistory(); 
                    });
                } else {
                    statusSpan.innerText = "Ready (Empty)";
                    this.selectTool('select');
                    this.isHistoryLocked = false;
                    this.saveStateToHistory();
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
            // Keep history unlocked to record the clear
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
                console.log("Undo performed");
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
                console.log("Redo performed");
            });
        }
    }
    
    refreshLayers() { console.log("Refresh layers not implemented yet"); }
    
    /**
     * Draw the basketball court background.
     */
    initCourt() {
        const strokeColor = '#333';
        const strokeWidth = 2;
        const width = 800;
        const height = 600;

        const courtObjects = [];

        // 1. Full Court Outline
        courtObjects.push(new fabric.Rect({
            left: 0, top: 0, width: width, height: height,
            fill: '#fff', stroke: strokeColor, strokeWidth: strokeWidth,
            selectable: false, evented: false
        }));

        // 2. Center Circle
        courtObjects.push(new fabric.Circle({
            left: 350, top: -50, radius: 50,
            fill: 'transparent', stroke: strokeColor, strokeWidth: strokeWidth,
            selectable: false, evented: false
        }));

        // 3. 3-Point Line (Simplified)
        const pathData = `M 50 0 C 50 300, 750 300, 750 0`; 
        courtObjects.push(new fabric.Path(pathData, {
            fill: 'transparent', stroke: strokeColor, strokeWidth: strokeWidth,
            selectable: false, evented: false
        }));

        // 4. Paint
        courtObjects.push(new fabric.Rect({
            left: 300, top: 0, width: 200, height: 250,
            fill: 'transparent', stroke: strokeColor, strokeWidth: strokeWidth,
            selectable: false, evented: false
        }));

        // 5. Hoop
        courtObjects.push(new fabric.Circle({
            left: 390, top: 40, radius: 10,
            fill: 'transparent', stroke: strokeColor, strokeWidth: strokeWidth,
            selectable: false, evented: false
        }));

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
        
        this.canvas.sendToBack(courtObjects[0]);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    window.app = new PlayBuilder("playCanvas");
});
