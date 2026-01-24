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
        let shape;

        const commonProps = {
            left: pointer.x,
            top: pointer.y,
            originX: 'center',
            originY: 'center',
            fill: 'transparent',
            stroke: '#000000',
            strokeWidth: 2,
            selectable: true
        };

        if (this.currentType === 'cone') {
            // Orange triangle
            shape = new fabric.Triangle({
                ...commonProps,
                width: 20,
                height: 20,
                fill: '#ff8800',
                stroke: '#cc6600',
                strokeWidth: 1
            });
        } else if (this.currentType === 'cone-tall') {
            // Taller cone
            shape = new fabric.Triangle({
                ...commonProps,
                width: 15,
                height: 30,
                fill: '#ff8800',
                stroke: '#cc6600',
                strokeWidth: 1
            });
        } else if (this.currentType === 'box') {
             shape = new fabric.Rect({
                ...commonProps,
                width: 30,
                height: 30
             });
        } else if (this.currentType === 'circle') {
             shape = new fabric.Circle({
                ...commonProps,
                radius: 15
             });
        } else if (this.currentType === 'triangle') {
             shape = new fabric.Triangle({
                ...commonProps,
                width: 30,
                height: 30
             });
        } else if (this.currentType === 'diamond') {
             shape = new fabric.Rect({
                ...commonProps,
                width: 25,
                height: 25,
                angle: 45
             });
        } else if (this.currentType === 'line') {
             shape = new fabric.Line([pointer.x - 20, pointer.y, pointer.x + 20, pointer.y], {
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
            shape.custom = { kind: 'shape', type: this.currentType };
            
            this.canvas.add(shape);
            this.canvas.setActiveObject(shape);
            this.canvas.requestRenderAll();
        }
        
        // Auto-switch to Select tool (One-Shot)
        if (window.app) {
            window.app.selectTool('select');
        }
    }
}
