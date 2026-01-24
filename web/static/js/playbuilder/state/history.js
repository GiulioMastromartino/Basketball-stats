/**
 * History Manager
 * Handles Undo/Redo functionality for the PlayBuilder.
 */
class HistoryManager {
    constructor(limit = 20) {
        this.stack = [];
        this.index = -1;
        this.limit = limit;
    }

    /**
     * Save a new state to history.
     * @param {string} stateJson - JSON string of canvas state
     */
    pushState(stateJson) {
        // If we are in middle of stack, discard future
        if (this.index < this.stack.length - 1) {
            this.stack = this.stack.slice(0, this.index + 1);
        }

        this.stack.push(stateJson);
        this.index++;

        // Maintain limit
        if (this.stack.length > this.limit) {
            this.stack.shift();
            this.index--;
        }
        
        console.log(`History pushed. Index: ${this.index}, Size: ${this.stack.length}`);
    }

    canUndo() {
        return this.index > 0;
    }

    canRedo() {
        return this.index < this.stack.length - 1;
    }

    undo() {
        if (!this.canUndo()) return null;
        this.index--;
        return this.stack[this.index];
    }

    redo() {
        if (!this.canRedo()) return null;
        this.index++;
        return this.stack[this.index];
    }
    
    /**
     * Get current state (useful for initial save)
     */
    current() {
        return this.stack[this.index];
    }
}
