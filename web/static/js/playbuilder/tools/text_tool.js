/**
 * Text Tool
 * Adds editable text labels to the canvas.
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
        const pointer = this.canvas.getPointer(opt.e);
        
        const text = new fabric.IText('Note', {
            left: pointer.x,
            top: pointer.y,
            fontFamily: 'Arial',
            fontSize: 20,
            fill: '#000',
            originX: 'left',
            originY: 'top'
        });

        // Add custom property
        text.toObject = (function(toObject) {
            return function() {
                return fabric.util.object.extend(toObject.call(this), {
                    custom: { kind: 'text' }
                });
            };
        })(text.toObject);
        text.custom = { kind: 'text' };

        this.canvas.add(text);
        this.canvas.setActiveObject(text);
        text.enterEditing();
        text.selectAll();
        this.canvas.requestRenderAll();
        
        // Switch back to select tool after adding text so user can move it or finish editing
        // Alternatively, keep active to add multiple notes. 
        // For text, usually adding one then editing is the flow, so switching to select is often better.
        // But for consistency with other tools, let's keep it active or let app handle it.
        // Let's rely on user manually switching for now, or we can auto-switch.
        // Given `enterEditing` captures focus, we might want to stay in tool but the interactions are tricky.
        // A common pattern: Add text -> Auto-switch to Select tool to avoid creating another text box immediately on next click.
        if (window.app) {
            window.app.selectTool('select');
        }
    }
}
