/**
 * Select Tool
 * Allows selecting, moving, and transforming objects.
 */
class SelectTool extends ToolBase {
    constructor(canvas) {
        super(canvas);
    }

    activate() {
        super.activate();
        this.canvas.selection = true;
        this.canvas.defaultCursor = 'default';
        
        // Enable selection for all non-locked objects.
        // Court backdrop (and legacy court-line) stays locked: selectable
        // must never be re-enabled or the court becomes draggable.
        this.canvas.getObjects().forEach(obj => {
            if (typeof CourtBackdrop !== 'undefined' && CourtBackdrop.isBackdrop(obj)) {
                CourtBackdrop.lock(obj);
            } else if (obj.custom?.kind !== 'court-line') {
                obj.selectable = true;
                obj.evented = true;
            }
        });
        
        this.canvas.requestRenderAll();
    }

    deactivate() {
        super.deactivate();
        this.canvas.selection = false;
        this.canvas.discardActiveObject();
        
        // Disable selection for everything (court stays locked).
        this.canvas.getObjects().forEach(obj => {
            if (typeof CourtBackdrop !== 'undefined' && CourtBackdrop.isBackdrop(obj)) {
                CourtBackdrop.lock(obj);
                return;
            }
            obj.selectable = false;
            // We keep evented=true usually if we want hover effects, 
            // but for strict tools we might disable it. 
            // For now, let's keep evented=false to prevent drag.
            if (obj.custom?.kind !== 'court-line') {
                obj.evented = false; 
            }
        });
        
        this.canvas.requestRenderAll();
    }
}
