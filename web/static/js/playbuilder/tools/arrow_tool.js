/**
 * ArrowTool - Handles drawing of movement lines (Cut, Pass, Dribble, Screen, etc.)
 */
class ArrowTool extends ToolBase {
    constructor(canvas) {
        super(canvas);
        this.isDrawing = false;
        this.line = null; // The main path object
        this.arrowHead = null;
        this.startPoint = null;
        this.curveControl = null; // Control point for curves
        
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
        
        // Listen for object selection to show curve controls
        this.canvas.on('selection:created', this.onSelect.bind(this));
        this.canvas.on('selection:updated', this.onSelect.bind(this));
        this.canvas.on('selection:cleared', this.onDeselect.bind(this));
        this.canvas.on('object:moving', this.onObjectMove.bind(this));
    }

    activate() {
        super.activate();
        this.canvas.selection = false;
        this.canvas.defaultCursor = 'crosshair';
        this.canvas.forEachObject(o => {
            // Disable selection while drawing new arrows
             o.selectable = false;
        });
    }

    deactivate() {
        super.deactivate();
        this.canvas.selection = true; // Re-enable selection
        this.canvas.defaultCursor = 'default';
        this.canvas.forEachObject(o => o.selectable = true);
        this.hideCurveControls();
    }
    
    setType(type) {
        if (this.typeConfig[type]) {
            this.currentType = type;
        }
    }
    
    getSnapPoint(pointer) {
        const snapDist = 40; 
        let closestPoint = { x: pointer.x, y: pointer.y };
        let minDist = snapDist;
        let foundTarget = null;
        
        this.canvas.getObjects().forEach(obj => {
            if (obj.custom && obj.custom.kind === 'player-token' && obj.visible) {
                const center = obj.getCenterPoint();
                const dist = Math.sqrt(Math.pow(center.x - pointer.x, 2) + Math.pow(center.y - pointer.y, 2));
                
                if (dist < minDist) {
                    minDist = dist;
                    closestPoint = { x: center.x, y: center.y };
                    foundTarget = obj;
                }
            }
        });
        
        return { point: closestPoint, target: foundTarget };
    }

    onMouseDown(opt) {
        // Enforce one-shot: if clicking existing object, switch to select
        if (opt.target) {
            if (window.app) window.app.selectTool('select');
            // We can return here, but better to let select tool handle the selection immediately if possible.
            // But since we just switched tools, the current click might be lost for selection purposes.
            // That's acceptable for "switching modes".
            return;
        }

        this.isDrawing = true;
        this.hideCurveControls(); // Clear any existing controls
        
        const pointer = this.canvas.getPointer(opt.e);
        const snap = this.getSnapPoint(pointer);
        this.startPoint = snap.point;
        
        // Default control point is midpoint
        this.curveControl = { 
            x: this.startPoint.x, 
            y: this.startPoint.y 
        };
        
        this.updateVisuals(this.startPoint, this.startPoint); // End point starts at start
    }

    onMouseMove(opt) {
        if (!this.isDrawing) return;
        const pointer = this.canvas.getPointer(opt.e);
        const snap = this.getSnapPoint(pointer);
        
        // Calculate default curve (straight line initially)
        // Control point is just midpoint for now
        const midX = (this.startPoint.x + snap.point.x) / 2;
        const midY = (this.startPoint.y + snap.point.y) / 2;
        this.curveControl = { x: midX, y: midY };
        
        this.updateVisuals(snap.point, this.curveControl);
    }

    onMouseUp(opt) {
        if (!this.isDrawing) return;
        this.isDrawing = false;
        
        if (this.line) {
            // Finalize arrow group
            const pointer = this.canvas.getPointer(opt.e);
            const snap = this.getSnapPoint(pointer);
            const endPoint = snap.point;

            const group = this.createArrowGroup(this.startPoint, endPoint, this.curveControl);
            
            // Clean up temp objects
            this.canvas.remove(this.line);
            if (this.arrowHead) this.canvas.remove(this.arrowHead);
            
            this.canvas.add(group);
            this.canvas.setActiveObject(group);
            this.canvas.renderAll();
            
            // Show controls for the new curve immediately
            // But wait! We are switching to select tool immediately.
            // The select tool will pick up the selection:created/updated event?
            // Actually, if we switch tools, we deactivate this one.
            // So we rely on SelectTool to handle the selection.
        }
        
        this.line = null;
        this.arrowHead = null;
        this.startPoint = null;
        
        // ALWAYS switch to select tool after drawing
        if (window.app) {
            window.app.selectTool('select');
            
            // If we just created an object and selected it, 
            // the new SelectTool should ideally show the curve controls if applicable.
            // Since we set active object above, SelectTool's activate might need to check selection.
        }
    }
    
    // ... (rest of methods: createArrowGroup, updateVisuals, getQuadPath, onSelect, onDeselect, showCurveControls, hideCurveControls, onObjectMove, updateArrowShape, calculateAngle) ...
    // Note: onSelect/onDeselect will still work even if tool is not active? 
    // No, tools usually unbind events on deactivate. 
    // Wait, the constructor binds them. But deactivate should probably stop listening or 
    // the SelectTool should handle curve logic?
    // Actually, curve editing is a property of the object, but the interaction is tool-specific.
    // If we want to edit curves in "Select Mode", the SelectTool needs to know about it,
    // OR we leave these listeners active globally.
    // For now, let's assume listeners are bound in constructor and stick around.
    // BUT checking `this.canvas.on` in constructor means they are always on.
    // That's fine if we want curve editing to be available whenever an arrow is selected.
    
    createArrowGroup(start, end, control) {
        const config = this.typeConfig[this.currentType];
        
        // Create the path string
        const pathData = this.getQuadPath(start, end, control);
        
        const path = new fabric.Path(pathData, {
            stroke: config.stroke,
            strokeWidth: 2,
            strokeDashArray: config.strokeDashArray,
            fill: 'transparent',
            originX: 'center', originY: 'center'
        });
        
        const angle = this.calculateAngle(control, end); 
        let head;
        
        if (config.arrow) {
             head = new fabric.Triangle({
                width: 12, height: 12, fill: config.stroke,
                originX: 'center', originY: 'center', angle: angle + 90
             });
        } else if (config.endCap === 'T') {
             head = new fabric.Line([0, -15, 0, 15], {
                stroke: config.stroke, strokeWidth: 3, originX: 'center', originY: 'center', angle: angle + 90
             });
        } else if (config.endCap === 'target') {
             const c = new fabric.Circle({ radius: 8, fill: 'transparent', stroke: config.stroke, strokeWidth: 2, originX: 'center', originY: 'center' });
             const l1 = new fabric.Line([0, -8, 0, 8], { stroke: config.stroke, strokeWidth: 1, originX: 'center', originY: 'center' });
             const l2 = new fabric.Line([-8, 0, 8, 0], { stroke: config.stroke, strokeWidth: 1, originX: 'center', originY: 'center' });
             head = new fabric.Group([c, l1, l2], { originX: 'center', originY: 'center', angle: angle });
        } else if (config.endCap === 'handoff') {
             head = new fabric.Text("H", { fontSize: 16, fontFamily: 'Arial', fontWeight: 'bold', fill: config.stroke, originX: 'center', originY: 'center', angle: angle });
        }
        
        const objs = [path];
        if (head) {
            head.left = end.x;
            head.top = end.y;
            objs.push(head);
        }
        
        const group = new fabric.Group(objs, {
            selectable: true,
            hasControls: false, 
            hasBorders: true,
            lockScalingX: true, lockScalingY: true, lockRotation: true
        });
        
        group.custom = {
            kind: 'arrow',
            type: this.currentType,
            start: start,
            end: end,
            control: control
        };
        
        return group;
    }

    updateVisuals(endPoint, controlPoint) {
        const config = this.typeConfig[this.currentType];
        
        if (this.line) this.canvas.remove(this.line);
        if (this.arrowHead) this.canvas.remove(this.arrowHead);
        
        const pathData = this.getQuadPath(this.startPoint, endPoint, controlPoint);
        this.line = new fabric.Path(pathData, {
           stroke: config.stroke, strokeWidth: 2, strokeDashArray: config.strokeDashArray,
           fill: 'transparent', selectable: false
        });
        this.canvas.add(this.line);

        const angle = this.calculateAngle(controlPoint, endPoint);
        
        if (config.arrow) {
            this.arrowHead = new fabric.Triangle({
                width: 12, height: 12, fill: config.stroke,
                left: endPoint.x, top: endPoint.y, originX: 'center', originY: 'center',
                angle: angle + 90, selectable: false
            });
            this.canvas.add(this.arrowHead);
        } else if (config.endCap === 'T') {
             this.arrowHead = new fabric.Line([0, -15, 0, 15], {
                stroke: config.stroke, strokeWidth: 3,
                left: endPoint.x, top: endPoint.y,
                originX: 'center', originY: 'center',
                angle: angle + 90,
                selectable: false
            });
            this.canvas.add(this.arrowHead);
        } else if (config.endCap === 'target') {
             const c = new fabric.Circle({ radius: 8, fill: 'transparent', stroke: config.stroke, strokeWidth: 2, originX: 'center', originY: 'center' });
             const l1 = new fabric.Line([0, -8, 0, 8], { stroke: config.stroke, strokeWidth: 1, originX: 'center', originY: 'center' });
             const l2 = new fabric.Line([-8, 0, 8, 0], { stroke: config.stroke, strokeWidth: 1, originX: 'center', originY: 'center' });
             this.arrowHead = new fabric.Group([c, l1, l2], { 
                 left: endPoint.x, top: endPoint.y, originX: 'center', originY: 'center', angle: angle, selectable: false 
             });
             this.canvas.add(this.arrowHead);
        } else if (config.endCap === 'handoff') {
             this.arrowHead = new fabric.Text("H", { 
                 fontSize: 16, fontFamily: 'Arial', fontWeight: 'bold', fill: config.stroke, 
                 left: endPoint.x, top: endPoint.y, originX: 'center', originY: 'center', angle: angle, selectable: false 
             });
             this.canvas.add(this.arrowHead);
        }
        
        this.canvas.requestRenderAll();
    }
    
    getQuadPath(start, end, cp) {
        return `M ${start.x} ${start.y} Q ${cp.x} ${cp.y} ${end.x} ${end.y}`;
    }

    onSelect(e) {
        if (e.selected && e.selected.length === 1) {
            const obj = e.selected[0];
            if (obj.custom && obj.custom.kind === 'arrow') {
                this.showCurveControls(obj);
            }
        }
    }
    
    onDeselect(e) {
        this.hideCurveControls();
    }
    
    showCurveControls(arrowGroup) {
        this.hideCurveControls(); 
        
        const data = arrowGroup.custom;
        if (!data || !data.control) return;
        
        const cp = new fabric.Circle({
            left: data.control.x,
            top: data.control.y,
            radius: 6,
            fill: '#ffffff',
            stroke: '#00a09d',
            strokeWidth: 2,
            originX: 'center',
            originY: 'center',
            hasControls: false,
            hasBorders: false,
            selectable: true,
            name: 'controlPoint'
        });
        
        cp.arrowRef = arrowGroup;
        cp.custom = { isControlPoint: true };
        
        this.canvas.add(cp);
        this.currentControlPoint = cp;
        this.canvas.requestRenderAll();
    }
    
    hideCurveControls() {
        if (this.currentControlPoint) {
            this.canvas.remove(this.currentControlPoint);
            this.currentControlPoint = null;
        }
        this.canvas.requestRenderAll();
    }
    
    onObjectMove(e) {
        const obj = e.target;
        if (obj.custom && obj.custom.isControlPoint) {
            const arrowGroup = obj.arrowRef;
            if (arrowGroup) {
                this.updateArrowShape(arrowGroup, obj);
            }
        }
    }
    
    updateArrowShape(group, controlPointObj) {
        const data = group.custom;
        const newControl = { x: controlPointObj.left, y: controlPointObj.top };
        
        const newGroup = this.createArrowGroup(data.start, data.end, newControl);
        
        this.canvas.remove(group);
        this.canvas.add(newGroup);
        controlPointObj.arrowRef = newGroup;
    }

    calculateAngle(start, end) {
        const dx = end.x - start.x;
        const dy = end.y - start.y;
        return Math.atan2(dy, dx) * 180 / Math.PI;
    }
    
    createWavePath(start, end, config) {
        // Fallback for visual update during draw if needed, 
        // but we are using curve now. Keep if needed or remove.
        // For now, implementing simple line for wave preview or curve?
        // Let's use getQuadPath logic even for dribble for consistency.
        return null;
    }
}
