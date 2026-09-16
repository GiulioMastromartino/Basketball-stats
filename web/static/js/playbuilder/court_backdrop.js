/**
 * Court Backdrop — the court drawn as real Fabric objects.
 *
 * Same geometry as the live-game shot popup court
 * (static/images/halfcourt.svg): 500x470 halves. 'half' centers one half
 * on the 800x500 builder canvas via COURT_OFFSET; 'full' stacks two halves
 * (500x940) on the 800x1000 canvas. Rendered by canvas 2D like every other
 * object, so it paints identically in every browser — no DOM/SVG/CSS
 * background involved, nothing for blockers or parsers to refuse.
 *
 * Individual locked shapes (not a Group: avoids group-coordinate shifts).
 * Tagged custom.kind === 'court-backdrop': tools, mirror, layers and phase
 * logic skip them; history snapshots and SVG export include them
 * automatically. Added floor-first so z-order is correct on load.
 */
const COURT_OFFSET_X = 150;
const COURT_OFFSET_Y = 15;
// Full court: same 500-wide halves stacked (940 tall) with wider margins.
const FULL_OFFSET_X = 150;
const FULL_OFFSET_Y = 30;

class CourtBackdrop {
    /** Canvas dimensions for a court type ('half' | 'full'). */
    static dims(court) {
        return court === 'full' ? { w: 800, h: 1000 } : { w: 800, h: 500 };
    }

    static shapes(court) {
        if (court === 'full') return CourtBackdrop.fullShapes();
        const X = COURT_OFFSET_X;
        const Y = COURT_OFFSET_Y;
        return [
            CourtBackdrop.floor(X, Y, 500, 470),
            ...CourtBackdrop.halfMarkings(X, Y, +1),
            CourtBackdrop.baseline(X, Y),
        ];
    }

    static fullShapes() {
        const X = FULL_OFFSET_X;
        const Y = FULL_OFFSET_Y;
        const H = 940;
        return [
            CourtBackdrop.floor(X, Y, 500, H),
            ...CourtBackdrop.halfMarkings(X, Y, +1),
            ...CourtBackdrop.halfMarkings(X, Y + H, -1),
            CourtBackdrop.baseline(X, Y),
            CourtBackdrop.baseline(X, Y + H),
            // Halfway line
            CourtBackdrop.tag(new fabric.Line([X, Y + H / 2, X + 500, Y + H / 2], {
                stroke: '#000', strokeWidth: 3,
                ...CourtBackdrop.lockedProps(),
            })),
        ];
    }

    static lockedProps() {
        return {
            selectable: false,
            evented: false,
            hasControls: false,
            hasBorders: false,
            hoverCursor: 'default',
            moveCursor: 'default',
        };
    }

    static tag(obj) {
        obj.custom = { kind: 'court-backdrop' };
        // Persist the tag through save/load (mirrors the tool factories).
        obj.toObject = (function (toObject) {
            return function () {
                return fabric.util.object.extend(toObject.call(this), {
                    custom: { kind: 'court-backdrop' },
                });
            };
        })(obj.toObject);
        return obj;
    }

    static floor(X, Y, w, h) {
        return CourtBackdrop.tag(new fabric.Rect({
            left: X, top: Y, width: w, height: h,
            fill: '#f0e6d2', stroke: 'none',
            originX: 'left', originY: 'top',
            ...CourtBackdrop.lockedProps(),
        }));
    }

    static baseline(X, Y) {
        return CourtBackdrop.tag(new fabric.Line([X, Y, X + 500, Y], {
            stroke: '#000', strokeWidth: 5,
            ...CourtBackdrop.lockedProps(),
        }));
    }

    /**
     * Markings for one half attached to the baseline edge Y.
     * dir=+1: basket at top, court extends downward (Y..Y+470).
     * dir=-1: basket at bottom, court extends upward (Y-470..Y).
     * Court-local coordinates derive from CX so left/right symmetry holds
     * by construction.
     */
    static halfMarkings(X, Y, dir) {
        const tag = (o) => CourtBackdrop.tag(o);
        const locked = CourtBackdrop.lockedProps();
        const W = 500;
        const CX = W / 2; // 250 — basket, key, circle and 3pt arc center
        const CORNER_GAP = 30; // corner-line inset from each sideline
        const ARC_R = (W - CORNER_GAP * 2) / 2; // 220 — arc carved from center
        const CORNER_LEN = 140;
        const KEY_W = 160;
        const FT_R = 60;
        // Offset from the baseline edge along the court direction.
        const yo = (off) => dir === 1 ? Y + off : Y - off;
        // NOTE: for fabric.Path, left/top anchors the path's bounding box
        // (not its 0,0 origin), so both axes must include the bbox min:
        // left needs min-x (CX-ARC_R) and, for the mirrored dir=-1 arc
        // whose apex reaches ARC_R above its chord, top needs min-y too —
        // plain Y-CORNER_LEN would sink the whole arc 220px too low,
        // dipping through the baseline.
        const arc = dir === 1
            ? `M ${CX - ARC_R},0 L ${CX - ARC_R},${CORNER_LEN} ` +
              `A ${ARC_R},${ARC_R} 0 0,0 ${CX + ARC_R},${CORNER_LEN} ` +
              `L ${CX + ARC_R},0`
            : `M ${CX - ARC_R},${CORNER_LEN} L ${CX - ARC_R},0 ` +
              `A ${ARC_R},${ARC_R} 0 0,1 ${CX + ARC_R},0 ` +
              `L ${CX + ARC_R},${CORNER_LEN}`;
        return [
            // 3-point line: corner segments + half-circle arc, mirrored about CX.
            tag(new fabric.Path(arc, {
                left: X + CX - ARC_R,
                top: dir === 1 ? Y : Y - CORNER_LEN - ARC_R,
                fill: '', stroke: '#000', strokeWidth: 3,
                originX: 'left', originY: 'top',
                ...locked,
            })),
            // Key / paint (centered on CX)
            tag(new fabric.Rect({
                left: X + CX - KEY_W / 2, top: dir === 1 ? Y : Y - 190,
                width: KEY_W, height: 190,
                fill: '', stroke: '#000', strokeWidth: 3,
                originX: 'left', originY: 'top',
                ...locked,
            })),
            // Free throw circle (centered on CX)
            tag(new fabric.Circle({
                left: X + CX, top: yo(190), radius: FT_R,
                fill: '', stroke: '#000', strokeWidth: 3,
                originX: 'center', originY: 'center',
                ...locked,
            })),
            // Backboard + hoop (centered on CX)
            tag(new fabric.Line([X + CX - 30, yo(40), X + CX + 30, yo(40)], {
                stroke: '#000', strokeWidth: 3,
                ...locked,
            })),
            tag(new fabric.Circle({
                left: X + CX, top: yo(55), radius: 7.5,
                fill: '', stroke: '#f00', strokeWidth: 2,
                originX: 'center', originY: 'center',
                ...locked,
            })),
        ];
    }

    static isBackdrop(obj) {
        return !!obj && obj.custom && obj.custom.kind === 'court-backdrop';
    }

    /** Force a single object into the locked, non-interactive state. */
    static lock(obj) {
        if (!obj) return obj;
        obj.set({
            selectable: false,
            evented: false,
            hasControls: false,
            hasBorders: false,
            hoverCursor: 'default',
            moveCursor: 'default',
            lockMovementX: true,
            lockMovementY: true,
            lockRotation: true,
            lockScalingX: true,
            lockScalingY: true,
        });
        return obj;
    }

    /** Re-lock every backdrop object on a canvas (e.g. after tool switches
     *  or loadFromJSON, which can restore selectable/evented as true). */
    static lockAll(canvas) {
        if (!canvas) return;
        canvas.getObjects().forEach((o) => {
            if (CourtBackdrop.isBackdrop(o)) CourtBackdrop.lock(o);
        });
    }

    static present(canvas) {
        return canvas.getObjects().some((o) => CourtBackdrop.isBackdrop(o));
    }
}
