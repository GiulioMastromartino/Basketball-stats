/**
 * ArrowTool - Handles drawing of movement lines (Cut, Pass, Dribble, Screen, etc.)
 *
 * NOTE:
 * - All tools are one-shot: after creating an action we immediately switch back to Select.
 * - Action visuals must match the sidebar icons (dribble=wavy, pass=dashed, cut=solid, etc.).
 */
class ArrowTool extends ToolBase {
    constructor(canvas) {
        super(canvas);
        this.isDrawing = false;
        this.line = null; // preview path
        this.arrowHead = null; // preview end-cap

        this.startPoint = null;
        this.curveControl = null; // control point (for quadratic curve)

        this.currentType = 'pass';

        this.typeConfig = {
            dribble: {
                stroke: '#000000',
                wave: true,
                arrow: true,
                strokeDashArray: null,
            },
            pass: {
                stroke: '#000000',
                wave: false,
                arrow: true,
                strokeDashArray: [10, 5],
            },
            cut: {
                stroke: '#000000',
                wave: false,
                arrow: true,
                strokeDashArray: null,
            },
            screen: {
                stroke: '#000000',
                wave: false,
                arrow: false,
                endCap: 'T',
                strokeDashArray: null,
            },
            shot: {
                stroke: '#000000',
                wave: false,
                arrow: false,
                endCap: 'target',
                strokeDashArray: [4, 4],
            },
            handoff: {
                stroke: '#000000',
                wave: false,
                arrow: false,
                endCap: 'handoff',
                strokeDashArray: null,
            },
        };

        // Always-on listeners for curve controls (available when selecting an action)
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
        // Do not hide curve controls here: those are useful in select mode too.
        // (They are removed via selection:cleared)
    }

    setType(type) {
        if (this.typeConfig[type]) this.currentType = type;
    }

    // --- Snapping ---
    getSnapPoint(pointer) {
        const snapDist = 40;
        let closestPoint = { x: pointer.x, y: pointer.y };
        let minDist = snapDist;
        let foundTarget = null;

        this.canvas.getObjects().forEach(obj => {
            if (obj.custom && obj.custom.kind === 'player-token' && obj.visible) {
                const center = obj.getCenterPoint();
                const dist = Math.hypot(center.x - pointer.x, center.y - pointer.y);
                if (dist < minDist) {
                    minDist = dist;
                    closestPoint = { x: center.x, y: center.y };
                    foundTarget = obj;
                }
            }
        });

        return { point: closestPoint, target: foundTarget };
    }

    // --- Mouse lifecycle (one-shot) ---
    onMouseDown(opt) {
        // One-shot rule: if user clicks an existing object, exit to select.
        if (opt.target) {
            if (window.app) window.app.selectTool('select');
            return;
        }

        this.isDrawing = true;

        const pointer = this.canvas.getPointer(opt.e);
        const snap = this.getSnapPoint(pointer);
        this.startPoint = snap.point;

        // Start with control point at start, then update on move.
        this.curveControl = { x: this.startPoint.x, y: this.startPoint.y };

        this.updateVisuals(this.startPoint, this.curveControl);
    }

    onMouseMove(opt) {
        if (!this.isDrawing) return;

        const pointer = this.canvas.getPointer(opt.e);
        const snap = this.getSnapPoint(pointer);
        const endPoint = snap.point;

        // default curve control = midpoint (user can edit after creation)
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
            const snap = this.getSnapPoint(pointer);
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

        // ALWAYS one-shot
        if (window.app) window.app.selectTool('select');
    }

    // --- Geometry helpers ---
    quadPoint(start, cp, end, t) {
        const u = 1 - t;
        return {
            x: u * u * start.x + 2 * u * t * cp.x + t * t * end.x,
            y: u * u * start.y + 2 * u * t * cp.y + t * t * end.y,
        };
    }

    quadTangent(start, cp, end, t) {
        // derivative of quadratic bezier
        return {
            x: 2 * (1 - t) * (cp.x - start.x) + 2 * t * (end.x - cp.x),
            y: 2 * (1 - t) * (cp.y - start.y) + 2 * t * (end.y - cp.y),
        };
    }

    angleFromVector(v) {
        return Math.atan2(v.y, v.x) * 180 / Math.PI;
    }

    endAngle(start, cp, end) {
        const tan = this.quadTangent(start, cp, end, 1);
        return this.angleFromVector(tan);
    }

    // Build a wavy polyline that follows the quadratic curve.
    // This keeps Dribble matching the wavy icon even when the action is curved.
    buildWavyQuadPath(start, cp, end, amplitude = 5, wavelength = 18) {
        // sample curve and build cumulative length
        const samples = 60;
        const pts = [];
        let totalLen = 0;
        let prev = this.quadPoint(start, cp, end, 0);
        pts.push({ t: 0, p: prev, s: 0 });

        for (let i = 1; i <= samples; i++) {
            const t = i / samples;
            const p = this.quadPoint(start, cp, end, t);
            totalLen += Math.hypot(p.x - prev.x, p.y - prev.y);
            pts.push({ t, p, s: totalLen });
            prev = p;
        }

        // Build wavy offset points
        let path = '';
        for (let i = 0; i < pts.length; i++) {
            const { t, p, s } = pts[i];
            const tan = this.quadTangent(start, cp, end, t);
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

    getPathDataForCurrentType(start, end, cp) {
        const config = this.typeConfig[this.currentType];
        if (config.wave) {
            return this.buildWavyQuadPath(start, cp, end);
        }
        return `M ${start.x} ${start.y} Q ${cp.x} ${cp.y} ${end.x} ${end.y}`;
    }

    // --- Rendering ---
    createArrowGroup(start, end, control) {
        const config = this.typeConfig[this.currentType];

        const pathData = this.getPathDataForCurrentType(start, end, control);
        const path = new fabric.Path(pathData, {
            stroke: config.stroke,
            strokeWidth: 2,
            strokeDashArray: config.strokeDashArray,
            fill: 'transparent',
            originX: 'center',
            originY: 'center',
        });

        const angle = this.endAngle(start, control, end);
        let head;

        if (config.arrow) {
            head = new fabric.Triangle({
                width: 12,
                height: 12,
                fill: config.stroke,
                originX: 'center',
                originY: 'center',
                angle: angle + 90,
            });
        } else if (config.endCap === 'T') {
            head = new fabric.Line([0, -15, 0, 15], {
                stroke: config.stroke,
                strokeWidth: 3,
                originX: 'center',
                originY: 'center',
                angle: angle + 90,
            });
        } else if (config.endCap === 'target') {
            const c = new fabric.Circle({ radius: 8, fill: 'transparent', stroke: config.stroke, strokeWidth: 2, originX: 'center', originY: 'center' });
            const l1 = new fabric.Line([0, -8, 0, 8], { stroke: config.stroke, strokeWidth: 1, originX: 'center', originY: 'center' });
            const l2 = new fabric.Line([-8, 0, 8, 0], { stroke: config.stroke, strokeWidth: 1, originX: 'center', originY: 'center' });
            head = new fabric.Group([c, l1, l2], { originX: 'center', originY: 'center', angle: angle });
        } else if (config.endCap === 'handoff') {
            head = new fabric.Text('H', {
                fontSize: 16,
                fontFamily: 'Arial',
                fontWeight: 'bold',
                fill: config.stroke,
                originX: 'center',
                originY: 'center',
                angle: angle,
            });
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
            lockScalingX: true,
            lockScalingY: true,
            lockRotation: true,
        });

        group.custom = {
            kind: 'arrow',
            type: this.currentType,
            start,
            end,
            control,
        };

        return group;
    }

    updateVisuals(endPoint, controlPoint) {
        const config = this.typeConfig[this.currentType];

        if (this.line) this.canvas.remove(this.line);
        if (this.arrowHead) this.canvas.remove(this.arrowHead);

        const pathData = this.getPathDataForCurrentType(this.startPoint, endPoint, controlPoint);

        this.line = new fabric.Path(pathData, {
            stroke: config.stroke,
            strokeWidth: 2,
            strokeDashArray: config.strokeDashArray,
            fill: 'transparent',
            selectable: false,
            evented: false,
        });
        this.canvas.add(this.line);

        const angle = this.endAngle(this.startPoint, controlPoint, endPoint);

        if (config.arrow) {
            this.arrowHead = new fabric.Triangle({
                width: 12,
                height: 12,
                fill: config.stroke,
                left: endPoint.x,
                top: endPoint.y,
                originX: 'center',
                originY: 'center',
                angle: angle + 90,
                selectable: false,
                evented: false,
            });
            this.canvas.add(this.arrowHead);
        } else if (config.endCap === 'T') {
            this.arrowHead = new fabric.Line([0, -15, 0, 15], {
                stroke: config.stroke,
                strokeWidth: 3,
                left: endPoint.x,
                top: endPoint.y,
                originX: 'center',
                originY: 'center',
                angle: angle + 90,
                selectable: false,
                evented: false,
            });
            this.canvas.add(this.arrowHead);
        } else if (config.endCap === 'target') {
            const c = new fabric.Circle({ radius: 8, fill: 'transparent', stroke: config.stroke, strokeWidth: 2, originX: 'center', originY: 'center' });
            const l1 = new fabric.Line([0, -8, 0, 8], { stroke: config.stroke, strokeWidth: 1, originX: 'center', originY: 'center' });
            const l2 = new fabric.Line([-8, 0, 8, 0], { stroke: config.stroke, strokeWidth: 1, originX: 'center', originY: 'center' });
            this.arrowHead = new fabric.Group([c, l1, l2], {
                left: endPoint.x,
                top: endPoint.y,
                originX: 'center',
                originY: 'center',
                angle: angle,
                selectable: false,
                evented: false,
            });
            this.canvas.add(this.arrowHead);
        } else if (config.endCap === 'handoff') {
            this.arrowHead = new fabric.Text('H', {
                fontSize: 16,
                fontFamily: 'Arial',
                fontWeight: 'bold',
                fill: config.stroke,
                left: endPoint.x,
                top: endPoint.y,
                originX: 'center',
                originY: 'center',
                angle: angle,
                selectable: false,
                evented: false,
            });
            this.canvas.add(this.arrowHead);
        }

        this.canvas.requestRenderAll();
    }

    // --- Curve controls ---
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
            evented: true,
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
            this.canvas.requestRenderAll();
        }
    }

    onObjectMove(e) {
        const obj = e.target;
        if (obj?.custom?.isControlPoint) {
            const arrowGroup = obj.arrowRef;
            if (arrowGroup) this.updateArrowShape(arrowGroup, obj);
        }
    }

    updateArrowShape(group, controlPointObj) {
        const data = group.custom;
        const newControl = { x: controlPointObj.left, y: controlPointObj.top };

        const newGroup = this.createArrowGroup(data.start, data.end, newControl);

        this.canvas.remove(group);
        this.canvas.add(newGroup);

        controlPointObj.arrowRef = newGroup;
        newGroup.custom.control = newControl;

        this.canvas.requestRenderAll();
    }
}
