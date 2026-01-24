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
            // Allow selecting existing arrows to edit curve
            if(o.custom && o.custom.kind === 'arrow') {
                 o.selectable = true;
            } else {
                 o.selectable = false;
            }
        });
    }

    deactivate() {
        super.deactivate();
        this.canvas.selection = false;
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
        // If clicking on an existing control point, let Fabric handle it
        if (opt.target && opt.target.custom && opt.target.custom.isControlPoint) return;
        
        // If clicking on existing arrow, select it (handled by Fabric), don't draw new
        if (opt.target && opt.target.custom && opt.target.custom.kind === 'arrow') return;

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
            // We store the control point relative to the group center or as custom property
            // Actually, for editable curves, it's better to NOT group the path yet, 
            // OR use a custom class. 
            // For simplicity, we'll create a group but attach metadata for reconstruction
            
            // Re-find end point from last line state? 
            // Better: use the last pointer.
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
            this.showCurveControls(group);
        }
        
        this.line = null;
        this.arrowHead = null;
        this.startPoint = null;
    }
    
    // Create the persistent object on canvas
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
        
        // If wavy, we need special handling (complex path generation)
        // For now, let's keep wavy simple (straight line sine wave) or curve it?
        // Curving a sine wave is hard. Let's disable curve editing for wavy lines for now,
        // or just apply curve to the base line.
        // Let's stick to standard paths for now.
        
        const angle = this.calculateAngle(control, end); // Angle at end comes from control point
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
        
        // Position head at end point
        // Group logic: Center is (start + end)/2 usually, but with curves it varies.
        // Simplest: Add to canvas as a group
        // We need to store world coordinates for reconstruction
        
        const objs = [path];
        if (head) {
            // Position head relative to path center? 
            // Easier: Group them at 0,0 relative, then set group pos.
            // But Fabric groups are tricky.
            // Alternative: use a custom subclass or just a group with metadata.
            
            // Let's place head correctly relative to path bounding box center?
            // Actually, we can just position the head at 'end' coordinates, path at its center.
            // Then group them.
            head.left = end.x;
            head.top = end.y;
            objs.push(head);
        }
        
        const group = new fabric.Group(objs, {
            selectable: true,
            hasControls: false, // We use custom control point
            hasBorders: true,
            lockScalingX: true, lockScalingY: true, lockRotation: true
        });
        
        // Save metadata for editing
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
        
        // For drawing phase, we draw components directly (not grouped)
        
        if (config.wave) {
             // Wavy line along the curve?
             // Complex. Fallback to straight wavy line for now.
             this.line = this.createWavePath(this.startPoint, endPoint, config);
        } else {
             const pathData = this.getQuadPath(this.startPoint, endPoint, controlPoint);
             this.line = new fabric.Path(pathData, {
                stroke: config.stroke, strokeWidth: 2, strokeDashArray: config.strokeDashArray,
                fill: 'transparent', selectable: false
             });
        }
        this.canvas.add(this.line);

        // Head
        const angle = config.wave ? this.calculateAngle(this.startPoint, endPoint) : this.calculateAngle(controlPoint, endPoint);
        
        if (config.arrow) {
            this.arrowHead = new fabric.Triangle({
                width: 12, height: 12, fill: config.stroke,
                left: endPoint.x, top: endPoint.y, originX: 'center', originY: 'center',
                angle: angle + 90, selectable: false
            });
            this.canvas.add(this.arrowHead);
        }
        // ... (other end caps similar to createArrowGroup) ...
        
        this.canvas.requestRenderAll();
    }
    
    // Generate Quadratic Bezier path string: M startX startY Q cpX cpY endX endY
    getQuadPath(start, end, cp) {
        return `M ${start.x} ${start.y} Q ${cp.x} ${cp.y} ${end.x} ${end.y}`;
    }

    // --- Curve Editing Logic ---
    
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
        this.hideCurveControls(); // Clear old
        
        const data = arrowGroup.custom;
        if (!data || !data.control) return;
        
        // Create a draggable control point
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
        
        // If moving the control point
        if (obj.custom && obj.custom.isControlPoint) {
            const arrowGroup = obj.arrowRef;
            if (arrowGroup) {
                // Update the arrow's shape based on new control point
                this.updateArrowShape(arrowGroup, obj);
            }
        }
        
        // If moving the arrow group itself?
        // We'd need to update stored coordinates (start, end, control) by delta
        // For now, let's just focus on curve editing.
    }
    
    updateArrowShape(group, controlPointObj) {
        // We need to re-generate the path inside the group
        // This is tricky with Fabric groups. 
        // Easiest is to destroy and recreate the group, 
        // OR just update metadata and re-render if we were drawing from scratch.
        
        // Simple approach: Remove old group, create new one with new CP, select it.
        const data = group.custom;
        const newControl = { x: controlPointObj.left, y: controlPointObj.top };
        
        const newGroup = this.createArrowGroup(data.start, data.end, newControl);
        
        // Preserve selection
        this.canvas.remove(group);
        this.canvas.add(newGroup);
        
        // Update reference
        controlPointObj.arrowRef = newGroup;
        
        // We don't want to re-select immediately or it might interrupt drag?
        // Actually, replacing object while dragging another object (cp) is fine.
        // But we shouldn't change selection to newGroup, keep focus on cp.
    }

    calculateAngle(start, end) {
        const dx = end.x - start.x;
        const dy = end.y - start.y;
        return Math.atan2(dy, dx) * 180 / Math.PI;
    }
    
    // ... createWavePath (updated to curve?) ...
    // For now, keep createWavePath as linear to avoid complexity, 
    // or implement simple quad curve for wave baseline.
}
