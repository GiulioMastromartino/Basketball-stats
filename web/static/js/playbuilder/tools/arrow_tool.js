/**
 * Arrow Tool
 * Draws directional lines (solid for cuts, dashed for passes).
 */
class ArrowTool extends ToolBase {
    constructor(canvas) {
        super(canvas);
        this.isDrawing = false;
        this.line = null;
        this.head = null;
        this.start = { x: 0, y: 0 };
        this.arrowType = 'cut'; // 'cut' (solid), 'pass' (dashed)
    }

    activate() {
        super.activate();
        this.canvas.defaultCursor = 'crosshair';
        this.canvas.selection = false;
    }

    onMouseDown(opt) {
        this.isDrawing = true;
        const pointer = this.canvas.getPointer(opt.e);
        this.start = { x: pointer.x, y: pointer.y };

        // Line options
        const lineOpts = {
            fill: 'transparent',
            stroke: '#000',
            strokeWidth: 2,
            selectable: false,
            evented: false,
            originX: 'center',
            originY: 'center'
        };

        if (this.arrowType === 'pass') {
            lineOpts.strokeDashArray = [5, 5];
        }

        this.line = new fabric.Line([pointer.x, pointer.y, pointer.x, pointer.y], lineOpts);

        this.head = new fabric.Triangle({
            width: 10,
            height: 10,
            fill: '#000',
            selectable: false,
            evented: false,
            originX: 'center',
            originY: 'center',
            angle: 90
        });

        this.canvas.add(this.line, this.head);
    }

    onMouseMove(opt) {
        if (!this.isDrawing) return;
        const pointer = this.canvas.getPointer(opt.e);
        
        this.line.set({ x2: pointer.x, y2: pointer.y });
        
        // Update head position
        this.head.set({ left: pointer.x, top: pointer.y });

        // Calculate angle
        const dx = pointer.x - this.start.x;
        const dy = pointer.y - this.start.y;
        let angle = Math.atan2(dy, dx) * 180 / Math.PI;
        this.head.set({ angle: angle + 90 }); // +90 because triangle points up by default

        this.canvas.requestRenderAll();
    }

    onMouseUp(opt) {
        if (!this.isDrawing) return;
        this.isDrawing = false;
        
        // Group them for easier selection later
        // Note: Grouping lines and heads can sometimes be tricky with resizing,
        // but for moving/deleting it's best.
        const group = new fabric.Group([this.line, this.head], {
            selectable: true,
            hasControls: true
        });
        
        // Capture type for serialization
        const type = this.arrowType;

        // Add custom property
        group.toObject = (function(toObject) {
            return function() {
                return fabric.util.object.extend(toObject.call(this), {
                    custom: { 
                        kind: 'arrow',
                        type: type 
                    }
                });
            };
        })(group.toObject);
        group.custom = { kind: 'arrow', type: type };

        this.canvas.remove(this.line, this.head);
        this.canvas.add(group);
        this.canvas.setActiveObject(group);
        this.canvas.requestRenderAll();
    }
    
    setType(type) {
        this.arrowType = type;
    }
}
