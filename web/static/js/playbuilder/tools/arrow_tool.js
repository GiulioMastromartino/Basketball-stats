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
        
        this.currentType = 'pass'; 
        
        this.typeConfig = {
            'dribble': { 
                stroke: '#000000', 
                wave: true,          
                arrow: true 
            },
            'pass': { 
                strokeDashArray: [10, 5], 
                stroke: '#000000', 
                wave: false, 
                arrow: true 
            },
            'cut': { 
                strokeDashArray: null, 
                stroke: '#000000', 
                wave: false, 
                arrow: true 
            },
            'screen': { 
                stroke: '#000000', 
                wave: false, 
                arrow: false,
                endCap: 'T'
            },
            'shot': { 
                strokeDashArray: [4, 4], 
                stroke: '#000000', 
                wave: false, 
                arrow: false,
                endCap: 'target'
            },
            'handoff': { 
                strokeDashArray: null, 
                stroke: '#000000', 
                wave: false, 
                arrow: false,
                endCap: 'handoff'
            }
        };
    }

    activate() {
        super.activate();
        this.canvas.selection = false;
        this.canvas.defaultCursor = 'crosshair';
        this.canvas.forEachObject(o => o.selectable = false);
    }

    deactivate() {
        super.deactivate();
        this.canvas.selection = false;
        this.canvas.defaultCursor = 'default';
        this.canvas.forEachObject(o => o.selectable = true);
    }
    
    setType(type) {
        if (this.typeConfig[type]) {
            this.currentType = type;
        }
    }

    onMouseDown(opt) {
        this.isDrawing = true;
        const pointer = this.canvas.getPointer(opt.e);
        this.startPoint = { x: pointer.x, y: pointer.y };
        
        // Initialize drawing
        this.updateVisuals(pointer);
    }

    onMouseMove(opt) {
        if (!this.isDrawing) return;
        const pointer = this.canvas.getPointer(opt.e);
        this.updateVisuals(pointer);
    }

    onMouseUp(opt) {
        this.isDrawing = false;
        
        if (this.line) {
            // Group everything
            const objs = [this.line];
            if (this.arrowHead) objs.push(this.arrowHead);
            
            const group = new fabric.Group(objs, {
                selectable: true,
                evented: true,
                hasControls: true,
                hasBorders: true,
                originX: 'center',
                originY: 'center'
            });
            
            // Custom serialization
            group.toObject = (function(toObject) {
                return function() {
                    return fabric.util.object.extend(toObject.call(this), {
                        custom: { kind: 'arrow', type: this.custom?.type || 'unknown' }
                    });
                };
            })(group.toObject);
            group.custom = { kind: 'arrow', type: this.currentType };
            
            // Remove parts, add group
            this.canvas.remove(this.line);
            if (this.arrowHead) this.canvas.remove(this.arrowHead);
            
            this.canvas.add(group);
            this.canvas.setActiveObject(group);
        }
        
        this.line = null;
        this.arrowHead = null;
        this.startPoint = null;
        this.canvas.renderAll();
        
        if (window.app) window.app.selectTool('select');
    }
    
    updateVisuals(endPoint) {
        const config = this.typeConfig[this.currentType];
        
        // Clean up previous
        if (this.line) this.canvas.remove(this.line);
        if (this.arrowHead) this.canvas.remove(this.arrowHead);
        
        // Draw Line/Path
        if (config.wave) {
            this.line = this.createWavePath(this.startPoint, endPoint, config);
        } else {
            this.line = new fabric.Line([this.startPoint.x, this.startPoint.y, endPoint.x, endPoint.y], {
                stroke: config.stroke,
                strokeWidth: 2,
                strokeDashArray: config.strokeDashArray,
                selectable: false,
                evented: false,
                originX: 'center',
                originY: 'center'
            });
        }
        this.canvas.add(this.line);

        // Draw End Cap (Arrow, Target, T, etc.)
        const angle = this.calculateAngle(this.startPoint, endPoint);
        
        if (config.arrow) {
            this.arrowHead = new fabric.Triangle({
                width: 12, height: 12,
                fill: config.stroke,
                left: endPoint.x, top: endPoint.y,
                originX: 'center', originY: 'center',
                angle: angle + 90,
                selectable: false, evented: false
            });
            this.canvas.add(this.arrowHead);
        } else if (config.endCap === 'T') {
            // Screen
            this.arrowHead = new fabric.Line([0, -15, 0, 15], {
                stroke: config.stroke, strokeWidth: 3,
                left: endPoint.x, top: endPoint.y,
                originX: 'center', originY: 'center',
                angle: angle + 90,
                selectable: false, evented: false
            });
            this.canvas.add(this.arrowHead);
        } else if (config.endCap === 'target') {
            // Shot
            const circle = new fabric.Circle({
                radius: 8, fill: 'transparent', stroke: config.stroke, strokeWidth: 2,
                originX: 'center', originY: 'center'
            });
            const line1 = new fabric.Line([0, -8, 0, 8], { stroke: config.stroke, strokeWidth: 1, originX: 'center', originY: 'center' });
            const line2 = new fabric.Line([-8, 0, 8, 0], { stroke: config.stroke, strokeWidth: 1, originX: 'center', originY: 'center' });
            
            this.arrowHead = new fabric.Group([circle, line1, line2], {
                left: endPoint.x, top: endPoint.y,
                originX: 'center', originY: 'center',
                angle: angle,
                selectable: false
            });
            this.canvas.add(this.arrowHead);
        } else if (config.endCap === 'handoff') {
            // Handoff (H symbol)
             this.arrowHead = new fabric.Text("H", {
                fontSize: 16, fontFamily: 'Arial', fontWeight: 'bold', fill: config.stroke,
                left: endPoint.x, top: endPoint.y,
                originX: 'center', originY: 'center',
                angle: angle, // Rotate with line? Usually text stays upright, but for 'action' symbols rotation is often better.
                selectable: false
             });
             this.canvas.add(this.arrowHead);
        }

        this.canvas.requestRenderAll();
    }

    createWavePath(start, end, config) {
        const dx = end.x - start.x;
        const dy = end.y - start.y;
        const dist = Math.sqrt(dx*dx + dy*dy);
        const angle = Math.atan2(dy, dx);
        
        // Wave params
        const amplitude = 5;
        const frequency = 0.2; // 1 wave per ~30px? 
        // Or fixed wave count based on distance?
        // Let's iterate points
        
        let pathData = `M ${start.x} ${start.y}`;
        
        // Number of steps
        const steps = Math.max(2, Math.floor(dist / 5));
        
        for (let i = 1; i <= steps; i++) {
            const t = i / steps;
            const cx = start.x + dx * t;
            const cy = start.y + dy * t;
            
            // Sine wave offset
            // We need perpendicular vector: (-dy, dx) normalized
            // offset = sin(t * freq * PI * 2) * amp
            // Freq needs to scale so we have complete waves. 
            // Let's say we want a wave every 20px.
            
            const wavePhase = (dist * t) / 10; // Adjust for density
            const offset = Math.sin(wavePhase) * amplitude;
            
            const perpX = -Math.sin(angle) * offset;
            const perpY = Math.cos(angle) * offset;
            
            pathData += ` L ${cx + perpX} ${cy + perpY}`;
        }
        
        return new fabric.Path(pathData, {
            stroke: config.stroke,
            strokeWidth: 2,
            fill: 'transparent',
            selectable: false,
            evented: false,
            originX: 'center', // Important for group
            originY: 'center'
        });
    }

    calculateAngle(start, end) {
        const dx = end.x - start.x;
        const dy = end.y - start.y;
        return Math.atan2(dy, dx) * 180 / Math.PI;
    }
}
