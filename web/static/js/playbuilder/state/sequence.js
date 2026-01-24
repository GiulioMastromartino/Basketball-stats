/**
 * Sequence Manager
 * Handles the list of animation frames (key states of the play).
 */
class SequenceManager {
    constructor(app, timelineId) {
        this.app = app;
        this.timelineElement = document.getElementById(timelineId);
        
        // Array of frames. Each frame: { id: <int>, data: <json_obj>, caption: <str> }
        this.frames = []; 
        this.currentIndex = -1;
        
        // Initialize with current state as Frame 1 if empty
        // Delay slightly to let canvas init
        setTimeout(() => {
            if (this.frames.length === 0) {
               this.captureCurrentAsFrame("Start");
            }
        }, 500);
    }

    captureCurrentAsFrame(caption = "Frame") {
        const json = this.app.canvas.toJSON(['custom']);
        const frame = {
            id: Date.now(),
            data: json,
            caption: caption
        };
        
        if (this.currentIndex >= 0 && this.frames[this.currentIndex]) {
             // If we are editing an existing frame, update it?
             // Usually sequence editors work by capturing snapshots.
             // Let's implement "Auto-update current frame on change" strategy?
             // Or explicit "Keyframe" strategy. 
             // For simplicity: explicit "Add Frame" creates NEW frame copy. 
             // Modifying canvas updates CURRENT frame data live.
             this.frames[this.currentIndex].data = json;
        } else {
             this.frames.push(frame);
             this.currentIndex = this.frames.length - 1;
        }
        
        this.renderTimeline();
    }
    
    addFrame() {
        // Clone current state as new frame
        const json = this.app.canvas.toJSON(['custom']);
        const frame = {
            id: Date.now(),
            data: json,
            caption: `Step ${this.frames.length + 1}`
        };
        this.frames.push(frame);
        this.currentIndex = this.frames.length - 1;
        this.renderTimeline();
        
        // Flash status
        const statusSpan = document.getElementById("status-bar");
        if(statusSpan) statusSpan.innerText = `Frame ${this.frames.length} added`;
    }

    deleteFrame(index, e) {
        if(e) e.stopPropagation();
        if (this.frames.length <= 1) {
            alert("Cannot delete the only frame.");
            return;
        }
        
        if (confirm("Delete this frame?")) {
            this.frames.splice(index, 1);
            if (this.currentIndex >= this.frames.length) {
                this.currentIndex = this.frames.length - 1;
            }
            this.loadFrame(this.currentIndex);
            this.renderTimeline();
        }
    }

    selectFrame(index) {
        if (index === this.currentIndex) return;
        
        // Save current before switching? 
        // We assume current frame is always up to date with canvas via listeners.
        // But we need to ensure listeners updated `this.frames[this.currentIndex]`.
        
        this.currentIndex = index;
        this.loadFrame(index);
        this.renderTimeline();
    }

    loadFrame(index) {
        const frame = this.frames[index];
        if (!frame) return;
        
        // Load data to canvas
        // Lock history to prevent undo stack pollution from frame switching
        this.app.isHistoryLocked = true;
        this.app.canvas.loadFromJSON(frame.data, () => {
            this.app.canvas.renderAll();
            this.app.isHistoryLocked = false;
            // Also refresh layers
            if(this.app.layers) this.app.layers.refresh();
        });
    }

    updateCurrentFrameData() {
        if (this.currentIndex >= 0 && this.frames[this.currentIndex]) {
            this.frames[this.currentIndex].data = this.app.canvas.toJSON(['custom']);
        }
    }

    renderTimeline() {
        if (!this.timelineElement) return;
        this.timelineElement.innerHTML = '';

        this.frames.forEach((frame, index) => {
            const el = document.createElement('div');
            el.className = `frame-item bg-light text-dark p-2 mr-2 rounded text-center position-relative ${index === this.currentIndex ? 'border border-primary' : ''}`;
            el.style.width = '100px';
            el.style.cursor = 'pointer';
            if (index === this.currentIndex) el.style.backgroundColor = '#e6f0ff';

            el.innerHTML = `
                <i class="fas fa-image fa-2x mb-1 text-muted"></i><br>
                <small>${frame.caption}</small>
                ${this.frames.length > 1 ? '<span class="delete-frame-btn position-absolute text-danger" style="top:2px; right:5px; cursor:pointer;">&times;</span>' : ''}
            `;
            
            el.addEventListener('click', () => this.selectFrame(index));
            
            const delBtn = el.querySelector('.delete-frame-btn');
            if(delBtn) delBtn.addEventListener('click', (e) => this.deleteFrame(index, e));

            this.timelineElement.appendChild(el);
        });
    }

    playAnimation() {
        let i = 0;
        const interval = setInterval(() => {
            if (i >= this.frames.length) {
                clearInterval(interval);
                // Return to start or stay at end? Stay at end.
                return;
            }
            this.selectFrame(i);
            i++;
        }, 1000); // 1 second per frame for preview
    }
}
