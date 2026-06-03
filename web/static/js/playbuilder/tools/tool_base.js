/**
 * Base class for all PlayBuilder tools.
 * Manages lifecycle and common event handlers.
 */
class ToolBase {
    constructor(canvas) {
        this.canvas = canvas;
        this.active = false;
    }

    /**
     * Called when the tool is selected.
     * Should set up specific canvas state (cursor, selection mode).
     */
    activate() {
        this.active = true;
        console.log(`${this.constructor.name} activated`);
    }

    /**
     * Called when the tool is deselected.
     * Should clean up listeners or temporary objects.
     */
    deactivate() {
        this.active = false;
    }

    // Default event handlers (can be overridden)
    onMouseDown(o) {}
    onMouseMove(o) {}
    onMouseUp(o) {}
}
