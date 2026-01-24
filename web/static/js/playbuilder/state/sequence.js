/**
 * Sequence Manager
 * Handles the list of animation frames (key states of the play).
 */
class SequenceManager {
    constructor(app, timelineId) {
        this.app = app;
        this.timelineElement = document.getElementById(timelineId);
        this.indicatorElement = document.getElementById("frame-indicator");
        
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
             this.frames[this.currentIndex].data = json;
        } else {
             this.frames.push(frame);
             this.currentIndex = this.frames.length - 1;
        }
        
        this.renderTimeline();
    }
    
    addFrame() {
        // 1) Ensure current frame is saved with current state (arrows present, tokens at start positions)
        this.updateCurrentFrameData();

        // 2) Clone current state as the starting point for the new frame
        const json = this.app.canvas.toJSON(['custom']);
        const frame = {
            id: Date.now(),
            data: json, // Initially identical to previous
            caption: `Step ${this.frames.length + 1}`
        };
        
        // 3) Push new frame and switch index IMMEDIATELY
        this.frames.push(frame);
        this.currentIndex = this.frames.length - 1;
        
        // 4) NOW apply phase transition rules.
        // Because currentIndex is now the NEW frame, and canvas events trigger updateCurrentFrameData(),
        // the changes (movement, deletion) will be saved to the NEW frame, leaving the OLD frame intact.
        if (this.app?.applyActionsAndClearForNextPhase) {
            this.app.applyActionsAndClearForNextPhase();
        }

        // Force a final update of the new frame data just in case events didn't catch everything
        this.updateCurrentFrameData();
        
        this.renderTimeline();
        
        // Flash status
        const statusSpan = document.getElementById("status-bar");
        if(statusSpan) statusSpan.innerText = `Frame ${this.frames.length} added`;
    }
    
    cloneFrame() {
        this.addFrame(); // Alias for now, as addFrame clones current state
    }

    deleteFrame(index, e) {
        if(e) e.stopPropagation();
        
        // If index not provided, delete current
        const targetIndex = (typeof index === 'number') ? index : this.currentIndex;

        if (this.frames.length <= 1) {
            alert("Cannot delete the only frame.");
            return;
        }
        
        if (confirm("Delete this frame?")) {
            this.frames.splice(targetIndex, 1);
            
            // Adjust current index
            if (this.currentIndex >= this.frames.length) {
                this.currentIndex = this.frames.length - 1;
            }
            
            this.loadFrame(this.currentIndex);
            this.renderTimeline();
        }
    }
    
    nextFrame() {
        if (this.currentIndex < this.frames.length - 1) {
            this.selectFrame(this.currentIndex + 1);
        }
    }
    
    prevFrame() {
        if (this.currentIndex > 0) {
            this.selectFrame(this.currentIndex - 1);
        }
    }

    selectFrame(index) {
        if (index === this.currentIndex) return;
        if (index < 0 || index >= this.frames.length) return;
        
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
        // Update text indicator
        if (this.indicatorElement) {
            this.indicatorElement.innerText = `PHASE ${this.currentIndex + 1}/${this.frames.length}`;
        }
        
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
                return;
            }
            this.selectFrame(i);
            i++;
        }, 1000); 
        this.animationInterval = interval;
    }
    
    stopAnimation() {
        if (this.animationInterval) {
            clearInterval(this.animationInterval);
            this.animationInterval = null;
        }
    }
}
