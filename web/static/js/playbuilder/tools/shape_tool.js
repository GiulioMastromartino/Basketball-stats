/**
 * Shape Tool
 * Places static shapes like cones, boxes, circles, triangles, etc.
 */
class ShapeTool extends ToolBase {
    constructor(canvas) {
        super(canvas);
        this.currentType = 'cone'; // cone, box, circle, triangle, diamond, line
    }

    activate() {
        super.activate();
        this.canvas.defaultCursor = 'crosshair';
        this.canvas.selection = false;
        console.log("Shape tool activated:", this.currentType);
    }

    setType(type) {
        this.currentType = type;
        console.log("Shape type set to:", type);
    }

    onMouseDown(opt) {
        // Enforce one-shot: if clicking existing object, switch to select
        if (opt.target) {
            if (window.app) window.app.selectTool('select');
            return;
        }

        const pointer = this.canvas.getPointer(opt.e);
        const shape = this.createShape(this.currentType, pointer.x, pointer.y);
        if (shape) {
            this.canvas.add(shape);
            this.canvas.setActiveObject(shape);
            this.canvas.requestRenderAll();
        }

        // Auto-switch to Select tool (One-Shot)
        if (window.app) {
            window.app.selectTool('select');
        }
    }

    /**
     * Factory shared by click-to-place and drag-and-drop palette flows.
     * Returns the configured shape (not yet added to the canvas) or null.
     */
    createShape(type, x, y) {
        const commonProps = {
            left: x,
            top: y,
            originX: 'center',
            originY: 'center',
            fill: 'transparent',
            stroke: '#000000',
            strokeWidth: 2,
            selectable: true
        };
        let shape = null;

        if (type === 'cone') {
            // Orange triangle
            shape = new fabric.Triangle({
                ...commonProps,
                width: 20,
                height: 20,
                fill: '#ff8800',
                stroke: '#cc6600',
                strokeWidth: 1
            });
        } else if (type === 'cone-tall') {
            // Taller cone
            shape = new fabric.Triangle({
                ...commonProps,
                width: 15,
                height: 30,
                fill: '#ff8800',
                stroke: '#cc6600',
                strokeWidth: 1
            });
        } else if (type === 'box') {
             shape = new fabric.Rect({
                ...commonProps,
                width: 30,
                height: 30
             });
        } else if (type === 'circle') {
             shape = new fabric.Circle({
                ...commonProps,
                radius: 15
             });
        } else if (type === 'triangle') {
             shape = new fabric.Triangle({
                ...commonProps,
                width: 30,
                height: 30
             });
        } else if (type === 'diamond') {
             shape = new fabric.Rect({
                ...commonProps,
                width: 25,
                height: 25,
                angle: 45
             });
        } else if (type === 'line') {
             shape = new fabric.Line([x - 20, y, x + 20, y], {
                ...commonProps,
                strokeWidth: 3,
                originX: 'center',
                originY: 'center'
             });
        }

        if (shape) {
            // Custom properties
             shape.toObject = (function(toObject) {
                return function() {
                    return fabric.util.object.extend(toObject.call(this), {
                        custom: { kind: 'shape', type: this.custom?.type || 'unknown' }
                    });
                };
            })(shape.toObject);
            shape.custom = { kind: 'shape', type: type };
        }
        return shape;
    }
}
