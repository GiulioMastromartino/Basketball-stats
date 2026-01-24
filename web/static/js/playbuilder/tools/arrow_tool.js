/**
 * ArrowTool - Handles drawing of movement lines (Cut, Pass, Dribble, Screen, etc.)
 */
class ArrowTool extends ToolBase {
    constructor(canvas) {
        super(canvas);
        this.isDrawing = false;
        this.line = null;
        this.arrowHead = null;
        this.startPoint = null;
        
        // Default line type
        this.currentType = 'pass'; // default
        
        // Configuration for different arrow types
        this.typeConfig = {
            'dribble': { 
                strokeDashArray: [5, 5], 
                stroke: '#000000', 
                wave: true,          // Zig-zag/wavy line (simulated)
                arrow: true 
            },
            'pass': { 
                strokeDashArray: [10, 5], 
                stroke: '#000000', 
                wave: false, 
                arrow: true 
            },
            'cut': { 
                strokeDashArray: null, // Solid line
                stroke: '#000000', 
                wave: false, 
                arrow: true 
            },
            'screen': { 
                strokeDashArray: null, 
                stroke: '#000000', 
                wave: false, 
                arrow: false,
                endCap: 'T'          // Perpendicular line at end
            },
            'shot': { 
                strokeDashArray: [2, 4], // Fine dots
                stroke: '#000000', 
                wave: false, 
                arrow: true,
                target: true         // Ends with target symbol
            },
            'handoff': { 
                strokeDashArray: null, 
                stroke: '#000000', 
                wave: false, 
                arrow: false,
                symbol: 'H'          // Plus/Handoff symbol
            }
        };
    }

    activate() {
        super.activate();
        this.canvas.selection = false;
        this.canvas.defaultCursor = 'crosshair';
        this.canvas.forEachObject(o => o.selectable = false);
        console.log("Arrow tool activated. Type:", this.currentType);
    }

    deactivate() {
        super.deactivate();
        this.canvas.selection = false;
        this.canvas.defaultCursor = 'default';
        this.canvas.forEachObject(o => o.selectable = true);
    }
    
    // Method to set the current arrow type from UI
    setType(type) {
        if (this.typeConfig[type]) {
            this.currentType = type;
            console.log("Arrow type set to:", type);
        }
    }

    onMouseDown(opt) {
        this.isDrawing = true;
        const pointer = this.canvas.getPointer(opt.e);
        this.startPoint = { x: pointer.x, y: pointer.y };
        
        const config = this.typeConfig[this.currentType];

        // Create the line object
        // Note: For 'wave' (dribble), ideal is a Path or Polyline, but using simple Line for prototype consistency
        this.line = new fabric.Line([pointer.x, pointer.y, pointer.x, pointer.y], {
            stroke: config.stroke,
            strokeWidth: 2,
            strokeDashArray: config.strokeDashArray,
            selectable: false,
            evented: false,
            originX: 'center',
            originY: 'center',
            type: 'arrowLine'
        });

        this.canvas.add(this.line);

        // Create arrow head if needed
        if (config.arrow) {
            this.arrowHead = new fabric.Triangle({
                left: pointer.x,
                top: pointer.y,
                originX: 'center',
                originY: 'center',
                width: 10,
                height: 10,
                fill: config.stroke,
                selectable: false,
                evented: false,
                angle: 90
            });
            this.canvas.add(this.arrowHead);
        }
        
        // Create screen cap (T-shape)
        if (config.endCap === 'T') {
             this.arrowHead = new fabric.Line([0, -10, 0, 10], {
                stroke: config.stroke,
                strokeWidth: 2,
                left: pointer.x,
                top: pointer.y,
                originX: 'center',
                originY: 'center',
                selectable: false,
                evented: false
            });
            this.canvas.add(this.arrowHead);
        }
    }

    onMouseMove(opt) {
        if (!this.isDrawing) return;
        const pointer = this.canvas.getPointer(opt.e);

        if (this.line) {
            this.line.set({ x2: pointer.x, y2: pointer.y });
        }

        if (this.arrowHead) {
            this.arrowHead.set({ left: pointer.x, top: pointer.y });
            
            // Calculate angle for rotation
            if (this.startPoint) {
                const dx = pointer.x - this.startPoint.x;
                const dy = pointer.y - this.startPoint.y;
                let angle = Math.atan2(dy, dx) * 180 / Math.PI;
                
                // Adjust angle based on marker type
                if (this.typeConfig[this.currentType].arrow) {
                    angle += 90; // Triangles point up by default
                }
                // For Screen (T-shape), line should be perpendicular to movement
                if (this.typeConfig[this.currentType].endCap === 'T') {
                    angle += 90; 
                }
                
                this.arrowHead.set({ angle: angle });
            }
        }

        this.canvas.renderAll();
    }

    onMouseUp(opt) {
        this.isDrawing = false;
        
        // Group line and arrow head together
        if (this.line && this.arrowHead) {
            const group = new fabric.Group([this.line, this.arrowHead], {
                selectable: true,
                evented: true,
                hasControls: true,
                hasBorders: true
            });
            
            // Add custom property for serialization
            group.toObject = (function(toObject) {
                return function() {
                    return fabric.util.object.extend(toObject.call(this), {
                        custom: { kind: 'arrow', type: this.custom?.type || 'unknown' }
                    });
                };
            })(group.toObject);
            group.custom = { kind: 'arrow', type: this.currentType };
            
            this.canvas.remove(this.line);
            this.canvas.remove(this.arrowHead);
            this.canvas.add(group);
            this.canvas.setActiveObject(group);
        } else if (this.line) {
             this.line.set({ selectable: true, evented: true });
        }
        
        this.line = null;
        this.arrowHead = null;
        this.startPoint = null;
        
        this.canvas.renderAll();
        // Trigger history save
        this.canvas.fire('object:added', { target: this.line });
    }
}
