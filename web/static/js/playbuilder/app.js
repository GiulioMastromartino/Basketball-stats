/**
 * PlayBuilder Core Application
 * Handles canvas initialization, tool management, and API interactions.
 */

class PlayBuilder {
    constructor(canvasId) {
        this.canvas = new fabric.Canvas(canvasId, {
            selection: true,
            preserveObjectStacking: true,
            backgroundColor: '#ffffff'
        });

        // Registry for tools (populated by separate files)
        this.tools = {};
        this.activeTool = null;

        // Configuration
        this.config = window.PlayBuilderConfig || {};
        
        // Initialize
        this.initCourt();
        this.initEvents();

        // Load data if editing
        if (this.config.playId) {
            this.loadPlay(this.config.playId);
        } else {
            console.log("New play initialized");
        }
    }

    /**
     * Draw the basketball court background.
     * Objects are locked and non-interactive.
     */
    initCourt() {
        const strokeColor = '#333';
        const strokeWidth = 2;
        const width = 800;
        const height = 600;

        // Group for all court lines
        const courtObjects = [];

        // 1. Full Court Outline (Half court visible mainly)
        courtObjects.push(new fabric.Rect({
            left: 0, top: 0, width: width, height: height,
            fill: '#fff', stroke: strokeColor, strokeWidth: strokeWidth,
            selectable: false, evented: false
        }));

        // 2. Center Circle (Top middle)
        courtObjects.push(new fabric.Circle({
            left: 350, top: -50, radius: 50,
            fill: 'transparent', stroke: strokeColor, strokeWidth: strokeWidth,
            selectable: false, evented: false
        }));

        // 3. 3-Point Line (Simplified Arc)
        const pathData = `M 50 0 C 50 300, 750 300, 750 0`; 
        // NOTE: A real court is more complex, this is a placeholder visual
        courtObjects.push(new fabric.Path(pathData, {
            fill: 'transparent', stroke: strokeColor, strokeWidth: strokeWidth,
            selectable: false, evented: false
        }));

        // 4. Paint / Key
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

        // Add all to canvas as a background group or individual items
        // We use individual items marked as 'court-line' in custom properties
        courtObjects.forEach(obj => {
            obj.toObject = (function(toObject) {
                return function() {
                    return fabric.util.object.extend(toObject.call(this), {
                        custom: { kind: 'court-line' }
                    });
                };
            })(obj.toObject);
            obj.custom = { kind: 'court-line' }; // Tag for serializer to ignore
            this.canvas.add(obj);
        });
        
        // Ensure they are at the bottom
        this.canvas.sendToBack(courtObjects[0]);
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
    }

    /**
     * Switch the active tool.
     * @param {string} toolId 
     */
    selectTool(toolId) {
        console.log(`Selecting tool: ${toolId}`);
        
        // 1. UI Update
        document.querySelectorAll("#tool-select, #tool-player, #tool-arrow, #tool-text").forEach(el => {
            el.classList.remove("active");
        });
        const btn = document.getElementById(`tool-${toolId}`);
        if (btn) btn.classList.add("active");

        // 2. Logic Update (Phase 2 will implement activate/deactivate)
        // Placeholder logic for now:
        if (toolId === 'select') {
            this.canvas.selection = true;
            this.canvas.forEachObject(o => {
                if(o.custom?.kind !== 'court-line') o.selectable = true;
            });
        } else {
            this.canvas.selection = false;
            this.canvas.forEachObject(o => o.selectable = false);
        }
    }

    /**
     * Save current play state to backend.
     */
    async savePlay() {
        const statusSpan = document.getElementById("status-bar");
        statusSpan.innerText = "Saving...";

        // 1. Gather Metadata
        const name = document.getElementById("meta-name").value;
        const type = document.getElementById("meta-type").value;
        const tags = document.getElementById("meta-tags").value;

        if (!name) {
            alert("Please enter a Play Name.");
            statusSpan.innerText = "Error: Name required";
            return;
        }

        // 2. Serialize Canvas
        // We exclude court lines usually, but for MVP let's just save everything 
        // or filter if we want clean data. 
        // Fabric's toJSON automatically includes everything.
        // We include 'custom' property to persist our tags.
        const canvasJson = this.canvas.toJSON(['custom']);

        // 3. Send API Request
        const payload = {
            play_id: this.config.playId ? parseInt(this.config.playId) : null,
            metadata: {
                name: name,
                play_type: type,
                tags: tags,
                // description: ... (add later)
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
                // Update URL if new play
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

    /**
     * Load a play from backend.
     * @param {number} playId 
     */
    async loadPlay(playId) {
        const statusSpan = document.getElementById("status-bar");
        statusSpan.innerText = "Loading...";

        try {
            const res = await fetch(`${this.config.apiBase}/plays/api/load-canvas/${playId}`);
            const data = await res.json();

            if (data.success) {
                // Restore Metadata
                if (data.metadata) {
                    document.getElementById("meta-name").value = data.metadata.name || "";
                    document.getElementById("meta-type").value = data.metadata.play_type || "Offense";
                    document.getElementById("meta-tags").value = data.metadata.tags || "";
                }

                // Restore Canvas
                if (data.canvas_json) {
                    this.canvas.loadFromJSON(data.canvas_json, () => {
                        this.canvas.renderAll();
                        statusSpan.innerText = "Ready";
                    });
                } else {
                    statusSpan.innerText = "Ready (Empty)";
                }
            } else {
                statusSpan.innerText = "Error loading play";
            }
        } catch (err) {
            console.error(err);
            statusSpan.innerText = "Error loading play";
        }
    }

    clearCanvas() {
        if(confirm("Clear all objects?")) {
            // Remove everything except court lines
            const objects = this.canvas.getObjects();
            // We iterate backwards when removing
            for (let i = objects.length - 1; i >= 0; i--) {
                const o = objects[i];
                if (o.custom?.kind !== 'court-line') {
                    this.canvas.remove(o);
                }
            }
        }
    }
    
    undo() { console.log("Undo not implemented yet"); }
    redo() { console.log("Redo not implemented yet"); }
    refreshLayers() { console.log("Refresh layers not implemented yet"); }
}

// Initialize on load
document.addEventListener("DOMContentLoaded", () => {
    window.app = new PlayBuilder("playCanvas");
});
