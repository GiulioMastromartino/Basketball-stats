/**
 * ArrowTool - Handles drawing of movement lines (Cut, Pass, Dribble, Screen, etc.)
 */
class ArrowTool extends ToolBase {
    constructor(canvas) {
        super(canvas);
        this.isDrawing = false;
        this.line = null; // preview path
        this.arrowHead = null; // preview end-cap

        this.startPoint = null;
        this.curveControl = null; // This is now the "Point On Curve" (peak), not the raw Bezier CP

        this.currentType = 'pass';
        this.controlHandles = []; // Array to store active edit handles

        this.typeConfig = {
            dribble: { stroke: '#000000', wave: true, arrow: true, strokeDashArray: null },
            pass: { stroke: '#000000', wave: false, arrow: true, strokeDashArray: [10, 5] },
            cut: { stroke: '#000000', wave: false, arrow: true, strokeDashArray: null },
            screen: { stroke: '#000000', wave: false, arrow: false, endCap: 'T', strokeDashArray: null },
            shot: { stroke: '#000000', wave: false, arrow: false, endCap: 'target', strokeDashArray: [4, 4] },
            handoff: { stroke: '#000000', wave: false, arrow: false, endCap: 'handoff', strokeDashArray: null },
        };

        // Listeners
        this.canvas.on('selection:created', this.onSelect.bind(this));
        this.canvas.on('selection:updated', this.onSelect.bind(this));
        this.canvas.on('selection:cleared', this.onDeselect.bind(this));
        this.canvas.on('object:moving', this.onObjectMove.bind(this));
    }

    activate() {
        super.activate();
        this.canvas.selection = false;
        this.canvas.defaultCursor = 'crosshair';
        this.canvas.forEachObject(o => (o.selectable = false));
    }

    deactivate() {
        super.deactivate();
        this.canvas.selection = true;
        this.canvas.defaultCursor = 'default';
        this.canvas.forEachObject(o => (o.selectable = true));
    }

    setType(type) {
        if (this.typeConfig[type]) this.currentType = type;
    }

    // --- Math Helpers ---
    
    // Convert a "Point on Curve" (t=0.5) to the necessary Quadratic Bezier Control Point
    // B(0.5) = 0.25*P0 + 0.5*P1 + 0.25*P2 = PointOnCurve
    // P1 = 2 * PointOnCurve - 0.5 * P0 - 0.5 * P2
    getBezierControlPoint(start, end, pointOnCurve) {
        return {
            x: 2 * pointOnCurve.x - 0.5 * start.x - 0.5 * end.x,
            y: 2 * pointOnCurve.y - 0.5 * start.y - 0.5 * end.y
        };
    }

    // --- Snapping ---
    // referencePoint: The "other end" of the line. If provided, we snap to the token's BORDER closest to this point.
    // If null, we snap to center (useful for first click).
    getSnapPoint(pointer, referencePoint = null) {
        const snapDist = 40;
        let closestPoint = { x: pointer.x, y: pointer.y };
        let minDist = snapDist;
        let foundTarget = null;

        this.canvas.getObjects().forEach(obj => {
            // Snap to Player Tokens
            if (obj.custom && obj.custom.kind === 'player-token' && obj.visible) {
                const center = obj.getCenterPoint();
                const dist = Math.hypot(center.x - pointer.x, center.y - pointer.y);
                
                if (dist < minDist) {
                    minDist = dist;
                    foundTarget = obj;
                    
                    if (referencePoint) {
                        // Snap to border logic
                        let radius = (obj.width * obj.scaleX) / 2; 
                        if (isNaN(radius) || radius < 1) radius = 15; // fallback
                        
                        const dx = referencePoint.x - center.x;
                        const dy = referencePoint.y - center.y;
                        const len = Math.hypot(dx, dy);
                        
                        if (len > 0) {
                            closestPoint = {
                                x: center.x + (dx / len) * radius,
                                y: center.y + (dy / len) * radius
                            };
                        } else {
                            closestPoint = { x: center.x, y: center.y };
                        }
                    } else {
                        closestPoint = { x: center.x, y: center.y };
                    }
                }
            }
            
            // Snap to Arrow Endpoints (e.g. chaining Cut -> Pass)
            else if (obj.custom && obj.custom.kind === 'arrow' && obj.visible && obj !== this.line) { // Avoid self-snap during draw
                 const start = obj.custom.start;
                 const end = obj.custom.end;
                 
                 // Check Start
                 const distStart = Math.hypot(start.x - pointer.x, start.y - pointer.y);
                 if (distStart < minDist) {
                     minDist = distStart;
                     closestPoint = { x: start.x, y: start.y };
                     foundTarget = obj;
                 }
                 
                 // Check End
                 const distEnd = Math.hypot(end.x - pointer.x, end.y - pointer.y);
                 if (distEnd < minDist) {
                     minDist = distEnd;
                     closestPoint = { x: end.x, y: end.y };
                     foundTarget = obj;
                 }
            }
        });

        return { point: closestPoint, target: foundTarget };
    }

    // --- Drawing Lifecycle ---
    onMouseDown(opt) {
        if (opt.target) {
            // Exception: If we click an ENDPOINT of an existing arrow to start a new one, don't select it.
            // But Fabric's selection logic runs before this? 
            // We set selectable=false in activate(), so opt.target might be null actually?
            // If selectable=false, opt.target is usually undefined on empty space, 
            // but if per-pixel target find is on...
            // Let's rely on getSnapPoint finding it.
            
            // If existing object is clicked, usually we want to select it. 
            // BUT if we are in DRAW mode, we want to draw FROM it.
            // Since we set objects unselectable in activate(), opt.target might be null anyway.
            // So this check is likely fine to remove or ignore if we want to draw on top.
            
            // Let's keep the check but maybe relax it if it's an arrow endpoint? 
            // For now, let's assume 'selectable=false' handles this.
            
            if (window.app && window.app.selectTool && opt.target && opt.target.selectable) {
                 window.app.selectTool('select');
                 return;
            }
        }

        this.isDrawing = true;
        const pointer = this.canvas.getPointer(opt.e);
        // First click: Snap to center usually preferred for start, or border? 
        // Let's snap to center for start, makes it easier to aim FROM a player.
        // actually, user asked for border snap. But without a 2nd point, "border closest to what?" is undefined.
        // We'll snap to center for START point, and border for END point (relative to start).
        const snap = this.getSnapPoint(pointer, null); 
        this.startPoint = snap.point;
        
        this.curveControl = { x: this.startPoint.x, y: this.startPoint.y };
        this.updateVisuals(this.startPoint, this.curveControl);
    }

    onMouseMove(opt) {
        if (!this.isDrawing) return;
        const pointer = this.canvas.getPointer(opt.e);
        
        // Pass startPoint as reference to snap to border facing the start point
        const snap = this.getSnapPoint(pointer, this.startPoint); 
        const endPoint = snap.point;

        // Default curve: Straight line midpoint
        // If we want it to act as "point on curve", midpoint is correct for a straight line (t=0.5)
        this.curveControl = {
            x: (this.startPoint.x + endPoint.x) / 2,
            y: (this.startPoint.y + endPoint.y) / 2,
        };

        this.updateVisuals(endPoint, this.curveControl);
    }

    onMouseUp(opt) {
        if (!this.isDrawing) return;
        this.isDrawing = false;

        if (this.line) {
            const pointer = this.canvas.getPointer(opt.e);
            const snap = this.getSnapPoint(pointer, this.startPoint);
            const endPoint = snap.point;
            
            const group = this.createArrowGroup(this.startPoint, endPoint, this.curveControl);
            
            this.canvas.remove(this.line);
            if (this.arrowHead) this.canvas.remove(this.arrowHead);
            
            this.canvas.add(group);
            this.canvas.setActiveObject(group);
            this.canvas.requestRenderAll();
        }

        this.line = null;
        this.arrowHead = null;
        this.startPoint = null;

        if (window.app) window.app.selectTool('select');
    }

    // --- Visuals & Path ---
    // pointOnCurve is the handle the user drags (t=0.5)
    getPathDataForCurrentType(start, end, pointOnCurve) {
        const config = this.typeConfig[this.currentType];
        
        // Transform user handle -> mathematical Bezier Control Point
        const cp = this.getBezierControlPoint(start, end, pointOnCurve);

        if (config.wave) {
            return this.buildWavyQuadPath(start, cp, end);
        }
        return `M ${start.x} ${start.y} Q ${cp.x} ${cp.y} ${end.x} ${end.y}`;
    }

    buildWavyQuadPath(start, cp, end, amplitude = 5, wavelength = 18) {
        const samples = 60;
        const pts = [];
        let totalLen = 0;
        
        const getPt = (t) => {
             const u = 1 - t;
             return {
                 x: u * u * start.x + 2 * u * t * cp.x + t * t * end.x,
                 y: u * u * start.y + 2 * u * t * cp.y + t * t * end.y
             };
        };

        let prev = getPt(0);
        pts.push({ t: 0, p: prev, s: 0 });

        for (let i = 1; i <= samples; i++) {
            const t = i / samples;
            const p = getPt(t);
            totalLen += Math.hypot(p.x - prev.x, p.y - prev.y);
            pts.push({ t, p, s: totalLen });
            prev = p;
        }
        
        const getTan = (t) => {
            return {
                x: 2 * (1 - t) * (cp.x - start.x) + 2 * t * (end.x - cp.x),
                y: 2 * (1 - t) * (cp.y - start.y) + 2 * t * (end.y - cp.y)
            };
        };

        let path = '';
        for (let i = 0; i < pts.length; i++) {
            const { t, p, s } = pts[i];
            const tan = getTan(t);
            const mag = Math.hypot(tan.x, tan.y) || 1;
            const nx = -tan.y / mag;
            const ny = tan.x / mag;

            const phase = (2 * Math.PI * s) / wavelength;
            const offset = Math.sin(phase) * amplitude;

            const x = p.x + nx * offset;
            const y = p.y + ny * offset;

            if (i === 0) path = `M ${x} ${y}`;
            else path += ` L ${x} ${y}`;
        }
        return path;
    }
    
    endAngle(start, cpRaw, end) {
        // Must use actual bezier CP for tangent calc
        const cp = this.getBezierControlPoint(start, end, cpRaw);

        const tan = {
            x: 2 * (1 - 1) * (cp.x - start.x) + 2 * 1 * (end.x - cp.x), 
            y: 2 * (1 - 1) * (cp.y - start.y) + 2 * 1 * (end.y - cp.y) 
        };
        if (Math.abs(tan.x) < 0.001 && Math.abs(tan.y) < 0.001) {
             return Math.atan2(end.y - start.y, end.x - start.x) * 180 / Math.PI;
        }
        return Math.atan2(tan.y, tan.x) * 180 / Math.PI;
    }

    createArrowGroup(start, end, pointOnCurve) {
        const config = this.typeConfig[this.currentType];
        // Generate path using the pointOnCurve -> BezierCP transformation
        const pathData = this.getPathDataForCurrentType(start, end, pointOnCurve);
        
        const path = new fabric.Path(pathData, {
            stroke: config.stroke, strokeWidth: 2, strokeDashArray: config.strokeDashArray,
            fill: 'transparent', originX: 'center', originY: 'center'
        });

        const angle = this.endAngle(start, pointOnCurve, end);
        let head;

        if (config.arrow) {
            head = new fabric.Triangle({
                width: 12, height: 12, fill: config.stroke,
                originX: 'center', originY: 'center', angle: angle + 90
            });
        } else if (config.endCap === 'T') {
            head = new fabric.Line([0, -15, 0, 15], {
                stroke: config.stroke, strokeWidth: 3, originX: 'center', originY: 'center', angle: angle
            });
        } else if (config.endCap === 'target') {
             const c = new fabric.Circle({ radius: 8, fill: 'transparent', stroke: config.stroke, strokeWidth: 2, originX: 'center', originY: 'center' });
             const l1 = new fabric.Line([0, -8, 0, 8], { stroke: config.stroke, strokeWidth: 1, originX: 'center', originY: 'center' });
             const l2 = new fabric.Line([-8, 0, 8, 0], { stroke: config.stroke, strokeWidth: 1, originX: 'center', originY: 'center' });
             head = new fabric.Group([c, l1, l2], { originX: 'center', originY: 'center', angle: angle });
        } else if (config.endCap === 'handoff') {
             head = new fabric.Text('H', {
                 fontSize: 16, fontFamily: 'Arial', fontWeight: 'bold', fill: config.stroke,
                 originX: 'center', originY: 'center', angle: angle
             });
        }

        const objs = [path];
        if (head) {
            head.left = end.x;
            head.top = end.y;
            objs.push(head);
        }

        const group = new fabric.Group(objs, {
            selectable: true, hasControls: false, hasBorders: true,
            lockScalingX: true, lockScalingY: true, lockRotation: true
        });

        // Store geometric data
        // We store pointOnCurve as 'control' so the handle spawns exactly where the line is
        group.custom = {
            kind: 'arrow',
            type: this.currentType,
            start: start,
            end: end,
            control: pointOnCurve
        };
        return group;
    }
    
    updateVisuals(endPoint, pointOnCurve) {
        const config = this.typeConfig[this.currentType];
        if (this.line) this.canvas.remove(this.line);
        if (this.arrowHead) this.canvas.remove(this.arrowHead);

        const pathData = this.getPathDataForCurrentType(this.startPoint, endPoint, pointOnCurve);
        this.line = new fabric.Path(pathData, {
            stroke: config.stroke, strokeWidth: 2, strokeDashArray: config.strokeDashArray,
            fill: 'transparent', selectable: false, evented: false
        });
        this.canvas.add(this.line);

        const angle = this.endAngle(this.startPoint, pointOnCurve, endPoint);
        // ... Heads ...
        if (config.arrow) {
             this.arrowHead = new fabric.Triangle({
                width: 12, height: 12, fill: config.stroke,
                left: endPoint.x, top: endPoint.y, originX: 'center', originY: 'center', angle: angle + 90, selectable: false, evented: false
            });
        } else if (config.endCap === 'T') {
             this.arrowHead = new fabric.Line([0, -15, 0, 15], {
                stroke: config.stroke, strokeWidth: 3,
                left: endPoint.x, top: endPoint.y, originX: 'center', originY: 'center', angle: angle, selectable: false, evented: false
            });
        } else if (config.endCap === 'target') {
             const c = new fabric.Circle({ radius: 8, fill: 'transparent', stroke: config.stroke, strokeWidth: 2, originX: 'center', originY: 'center' });
             const l1 = new fabric.Line([0, -8, 0, 8], { stroke: config.stroke, strokeWidth: 1, originX: 'center', originY: 'center' });
             const l2 = new fabric.Line([-8, 0, 8, 0], { stroke: config.stroke, strokeWidth: 1, originX: 'center', originY: 'center' });
             this.arrowHead = new fabric.Group([c, l1, l2], { left: endPoint.x, top: endPoint.y, originX: 'center', originY: 'center', angle: angle, selectable: false, evented: false });
        } else if (config.endCap === 'handoff') {
             this.arrowHead = new fabric.Text('H', {
                 fontSize: 16, fontFamily: 'Arial', fontWeight: 'bold', fill: config.stroke,
                 left: endPoint.x, top: endPoint.y, originX: 'center', originY: 'center', angle: angle, selectable: false, evented: false
             });
        }
        
        if (this.arrowHead) this.canvas.add(this.arrowHead);
        this.canvas.requestRenderAll();
    }

    // --- Curve Control Logic ---
    onSelect(e) {
        if (e.selected && e.selected.length === 1) {
            const obj = e.selected[0];
            if (obj.custom && obj.custom.kind === 'arrow') {
                this.showCurveControls(obj);
            }
        }
    }
    
    onDeselect() {
        this.hideCurveControls();
    }

    showCurveControls(arrowGroup) {
        this.hideCurveControls();
        const data = arrowGroup.custom;
        if (!data || !data.control || !data.start || !data.end) return;

        // 1. Point On Curve Handle (White)
        const cp = new fabric.Circle({
            left: data.control.x, top: data.control.y,
            radius: 6, fill: '#ffffff', stroke: '#00a09d', strokeWidth: 2,
            originX: 'center', originY: 'center',
            hasControls: false, hasBorders: false, selectable: true, evented: true
        });
        cp.arrowRef = arrowGroup;
        cp.custom = { isControlPoint: true };
        
        // 2. Start Handle
        const sp = new fabric.Circle({
            left: data.start.x, top: data.start.y,
            radius: 5, fill: '#00a09d', stroke: '#ffffff', strokeWidth: 1,
            originX: 'center', originY: 'center',
            hasControls: false, hasBorders: false, selectable: true, evented: true
        });
        sp.arrowRef = arrowGroup;
        sp.custom = { isStartPoint: true };

        // 3. End Handle
        const ep = new fabric.Circle({
            left: data.end.x, top: data.end.y,
            radius: 5, fill: '#00a09d', stroke: '#ffffff', strokeWidth: 1,
            originX: 'center', originY: 'center',
            hasControls: false, hasBorders: false, selectable: true, evented: true
        });
        ep.arrowRef = arrowGroup;
        ep.custom = { isEndPoint: true };

        this.canvas.add(sp, ep, cp);
        this.controlHandles = [sp, ep, cp]; 
        this.canvas.requestRenderAll();
    }
    
    hideCurveControls() {
        if (this.controlHandles.length > 0) {
            this.controlHandles.forEach(h => this.canvas.remove(h));
            this.controlHandles = [];
            this.canvas.requestRenderAll();
        }
    }
    
    onObjectMove(e) {
        const obj = e.target;
        if (!obj.custom || !obj.arrowRef) return;
        
        const arrowGroup = obj.arrowRef;
        const data = arrowGroup.custom;

        let newStart = data.start;
        let newEnd = data.end;
        let newControl = data.control;

        if (obj.custom.isControlPoint) {
            // Dragging point-on-curve: just update position
            newControl = { x: obj.left, y: obj.top };
        } 
        else if (obj.custom.isStartPoint) {
            // Dragging start: Snap relative to End
            const snap = this.getSnapPoint({ x: obj.left, y: obj.top }, newEnd);
            newStart = snap.point;
            
            obj.left = newStart.x;
            obj.top = newStart.y;
        } 
        else if (obj.custom.isEndPoint) {
            // Dragging end: Snap relative to Start
            const snap = this.getSnapPoint({ x: obj.left, y: obj.top }, newStart);
            newEnd = snap.point;
            
            obj.left = newEnd.x;
            obj.top = newEnd.y;
        } else {
            return;
        }

        const originalType = this.currentType;
        this.currentType = data.type; 

        const newGroup = this.createArrowGroup(newStart, newEnd, newControl);
        this.currentType = originalType; 
        
        this.canvas.remove(arrowGroup);
        this.canvas.add(newGroup);
        this.canvas.sendToBack(newGroup);

        this.controlHandles.forEach(h => h.arrowRef = newGroup);
    }
}
