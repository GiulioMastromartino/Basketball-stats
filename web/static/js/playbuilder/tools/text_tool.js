/**
 * Text Tool
 * Adds text objects to the canvas.
 */
class TextTool extends ToolBase {
    constructor(canvas) {
        super(canvas);
    }

    activate() {
        super.activate();
        this.canvas.defaultCursor = 'text';
        this.canvas.selection = false;
    }

    onMouseDown(opt) {
        // Enforce one-shot: if clicking existing object, switch to select
        if (opt.target) {
            if (window.app) window.app.selectTool('select');
            return;
        }

        const pointer = this.canvas.getPointer(opt.e);
        const text = new fabric.IText('Text', {
            left: pointer.x,
            top: pointer.y,
            fontFamily: 'Arial',
            fontSize: 20,
            originX: 'center',
            originY: 'center',
            fill: '#333'
        });

        // Custom serialization
        text.toObject = (function(toObject) {
            return function() {
                return fabric.util.object.extend(toObject.call(this), {
                    custom: { kind: 'text', ...this.custom }
                });
            };
        })(text.toObject);
        text.custom = { kind: 'text' };

        this.canvas.add(text);
        this.canvas.setActiveObject(text);
        text.enterEditing();
        text.selectAll();
        this.canvas.requestRenderAll();
        
        // Auto-switch to Select tool (One-Shot)
        if (window.app) {
            window.app.selectTool('select');
        }
    }
}
