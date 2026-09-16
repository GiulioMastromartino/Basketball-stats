/**
 * PlayBuilder Core Application
 * Handles canvas initialization, tool management, and API interactions.
 */

class PlayBuilder {
    constructor(canvasId) {
        // ... (previous constructor code) ...
        // Initialize Canvas
        this.canvas = new fabric.Canvas(canvasId, {
            selection: false, 
            preserveObjectStacking: true,
            enableRetinaScaling: false,
            backgroundColor: 'rgba(0,0,0,0)'  // Transparent to show CSS background
        });

        // Registry for tools
        this.tools = {};
        this.activeTool = null;

        // Managers
        this.history = null;
        this.layers = null;
        this.sequence = null;
        
        this.isHistoryLocked = false; 
        this.currentMode = 'draw'; // 'draw' | 'animate' | 'notes'

        // Configuration
        this.config = window.PlayBuilderConfig || {};
        // Court size: 'half' (800x500) or 'full' (800x1000). Persisted per
        // play as metadata.court_type; the toggle lives in create.html.
        this.court = this.config.court === 'full' ? 'full' : 'half';
        if (typeof CourtBackdrop !== 'undefined') {
            const d = CourtBackdrop.dims(this.court);
            this.canvas.setDimensions({ width: d.w, height: d.h });
        }
        
        // Initialize Tools & Managers
        this.initTools();
        this.initHistory();
        this.initLayers();
        this.initSequence();
        this.initEvents();
        this.initPaletteDrop();
        this.initActionShortcuts();
        // Court backdrop (canvas-drawn: paints identically everywhere).
        this.ensureCourtBackdrop();
        // Initial toolbar state mirrors the default Select tool.
        this.syncActionToolbar('select', null);
        this.syncCourtToggle();

        // Load data if editing
        if (this.config.playId) {
            this.loadPlay(this.config.playId);
        } else {
            console.log("New play initialized");
            this.selectTool('select');
            
            // Initial save state
            setTimeout(() => {
                this.saveStateToHistory(); 
                if (this.sequence && this.sequence.frames.length === 0) {
                     this.sequence.captureCurrentAsFrame("Start");
                }
            }, 200);
        }
    }
    
    // ... (previous methods: initTools, initHistory, initLayers, initSequence, initEvents, deleteSelected, etc.) ...
    initTools() {
        if (typeof SelectTool !== 'undefined') this.tools['select'] = new SelectTool(this.canvas);
        if (typeof PlayerTool !== 'undefined') this.tools['player'] = new PlayerTool(this.canvas);
        if (typeof ArrowTool !== 'undefined') this.tools['arrow'] = new ArrowTool(this.canvas);
        if (typeof TextTool !== 'undefined') this.tools['text'] = new TextTool(this.canvas);
        if (typeof ShapeTool !== 'undefined') this.tools['shape'] = new ShapeTool(this.canvas);
        if (typeof ImageTool !== 'undefined') this.tools['image'] = new ImageTool(this.canvas);
    }

    initHistory() {
        if (typeof HistoryManager !== 'undefined') {
            this.history = new HistoryManager();
        }
    }
    
    initLayers() {
        if (typeof LayersPanel !== 'undefined') {
            this.layers = new LayersPanel(this.canvas, 'layers-list');
        }
    }
    
    initSequence() {
        if (typeof SequenceManager !== 'undefined') {
            this.sequence = new SequenceManager(this, 'timeline-frames');
        }
    }

    initEvents() {
        // Save Button
        const saveBtn = document.getElementById("save-btn");
        if (saveBtn) {
            saveBtn.addEventListener("click", (e) => {
                e.preventDefault();
                this.savePlay();
            });
        }
        
        // Delete key handling
        document.addEventListener('keydown', (e) => {
            if ((e.key === 'Delete' || e.key === 'Backspace') && this.canvas.getActiveObject()) {
                // Prevent backspace from navigating back if not in an input
                const tag = e.target.tagName.toLowerCase();
                if (tag !== 'input' && tag !== 'textarea') {
                    this.deleteSelected();
                }
            }
        });

        // Canvas Events Delegation to Active Tool
        this.canvas.on('mouse:down', (opt) => {
            if (this.activeTool) this.activeTool.onMouseDown(opt);
        });
        this.canvas.on('mouse:move', (opt) => {
            if (this.activeTool) this.activeTool.onMouseMove(opt);
        });
        this.canvas.on('mouse:up', (opt) => {
            if (this.activeTool) this.activeTool.onMouseUp(opt);
        });

        // Object Events (History & Layers & Sequence)
        const updateAll = (e) => {
             this.saveStateToHistory();
             if (this.layers) this.layers.refresh();
             if (this.sequence) this.sequence.updateCurrentFrameData();
        };

        this.canvas.on('object:added', updateAll);
        this.canvas.on('object:modified', updateAll);
        this.canvas.on('object:removed', updateAll);

        // Court backdrop must never become interactive (tools and
        // loadFromJSON can restore selectable/evented as true).
        this.canvas.on('object:added', (e) => {
            const t = e && e.target;
            if (typeof CourtBackdrop !== 'undefined' && CourtBackdrop.isBackdrop(t)) {
                CourtBackdrop.lock(t);
                this.canvas.requestRenderAll();
            }
        });
        
        // Selection events for Layers & UI Overlay
        const onSelectionChange = () => {
             // Never allow the court itself to stay selected (e.g. after
             // a drag-select or a load that unlocked it).
             const active = this.canvas.getActiveObject();
             if (typeof CourtBackdrop !== 'undefined' && active) {
                 const picked = active.type === 'activeSelection'
                     ? active.getObjects().filter((o) => CourtBackdrop.isBackdrop(o))
                     : (CourtBackdrop.isBackdrop(active) ? [active] : []);
                 if (picked.length) {
                     this.canvas.discardActiveObject();
                     this.canvas.requestRenderAll();
                     if (this.layers) this.layers.refresh();
                     this.updateSelectionUI();
                     return;
                 }
             }
             if(this.layers) this.layers.refresh();
             this.updateSelectionUI();
        };

        this.canvas.on('selection:created', onSelectionChange);
        this.canvas.on('selection:updated', onSelectionChange);
        this.canvas.on('selection:cleared', onSelectionChange);
    }

    /**
     * Palette drag-and-drop: drag toolbar items straight onto the court.
     * Reuses each tool's factory (createToken/createShape), so dropped
     * objects are identical to click-placed ones. object:added already
     * fans out to history/layers/sequence — no extra bookkeeping needed.
     * Touch devices (no HTML5 DnD): touchstart on a palette item arms the
     * payload, touchend over the canvas drops it. Palette items carry
     * touch-action:none (see create.html) so the page doesn't scroll instead.
     */
    initPaletteDrop() {
        const readPayload = (el) => {
            try {
                return {
                    kind: el.dataset.pbKind,
                    type: el.dataset.pbType || null,
                    props: el.dataset.pbProps ? JSON.parse(el.dataset.pbProps) : {},
                };
            } catch (_) {
                return null;
            }
        };

        // Desktop: HTML5 drag & drop.
        document.addEventListener('dragstart', (e) => {
            const src = e.target && e.target.closest ? e.target.closest('[data-pb-kind]') : null;
            if (!src || !e.dataTransfer) return;
            const payload = readPayload(src);
            if (!payload) return;
            try {
                e.dataTransfer.setData('application/x-playbuilder', JSON.stringify(payload));
            } catch (_) { /* clipboard types unsupported */ }
            e.dataTransfer.effectAllowed = 'copy';
        });

        const upper = this.canvas.upperCanvasEl || this.canvas.getElement();
        upper.addEventListener('dragover', (e) => {
            e.preventDefault();
            if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
        });
        upper.addEventListener('drop', (e) => {
            e.preventDefault();
            let payload = null;
            try {
                payload = JSON.parse(e.dataTransfer.getData('application/x-playbuilder'));
            } catch (_) { /* foreign drop: ignore */ }
            if (payload) this.spawnFromPalette(payload, e.clientX, e.clientY);
        });

        // Touch fallback (tablets/phones have no HTML5 DnD).
        let touchPayload = null;
        document.addEventListener('touchstart', (e) => {
            const t = e.target && e.target.closest ? e.target.closest('[data-pb-kind]') : null;
            touchPayload = t ? readPayload(t) : null;
        }, { passive: true });
        document.addEventListener('touchend', (e) => {
            const payload = touchPayload;
            touchPayload = null;
            if (!payload || !e.changedTouches || !e.changedTouches.length) return;
            const t = e.changedTouches[0];
            const rect = this.canvas.getElement().getBoundingClientRect();
            const inside = t.clientX >= rect.left && t.clientX <= rect.right
                && t.clientY >= rect.top && t.clientY <= rect.bottom;
            if (inside) this.spawnFromPalette(payload, t.clientX, t.clientY);
        });
    }

    /**
     * Spawn one palette payload at viewport (clientX, clientY) if that
     * point lands on the court. Returns true on drop, false otherwise.
     */
    spawnFromPalette(payload, clientX, clientY) {
        if (!payload || typeof clientX !== 'number' || typeof clientY !== 'number') return false;
        const rect = this.canvas.getElement().getBoundingClientRect();
        if (clientX < rect.left || clientX > rect.right || clientY < rect.top || clientY > rect.bottom) {
            return false;
        }
        // Manual transform (same math as fabric's getPointer): canvas CSS
        // pixels -> court coordinates, honoring canvas zoom and responsive
        // CSS scaling (intrinsic canvas size vs displayed rect) plus
        // viewport translation.
        const vpt = this.canvas.viewportTransform || [1, 0, 0, 1, 0, 0];
        const cssScaleX = this.canvas.getWidth() / rect.width;
        const cssScaleY = this.canvas.getHeight() / rect.height;
        const x = ((clientX - rect.left) * cssScaleX - vpt[4]) / (vpt[0] || 1);
        const y = ((clientY - rect.top) * cssScaleY - vpt[5]) / (vpt[3] || 1);

        let obj = null;
        if (payload.kind === 'player' && this.tools.player && this.tools.player.createToken) {
            obj = this.tools.player.createToken(payload.props || {}, x, y);
        } else if (payload.kind === 'shape' && this.tools.shape && this.tools.shape.createShape) {
            obj = this.tools.shape.createShape(payload.type, x, y);
        }
        if (!obj) return false;
        this.canvas.add(obj);
        this.canvas.setActiveObject(obj);
        this.canvas.requestRenderAll();
        this.selectTool('select');
        return true;
    }

    /**
     * Guarantee the locked court backdrop exists exactly once, at the
     * bottom of the z-order. Canvas-drawn (not DOM/CSS/SVG), so it renders
     * identically in every browser. No-op when already present.
     */
    ensureCourtBackdrop() {
        if (typeof CourtBackdrop === 'undefined' || !this.canvas) return;
        const objs = this.canvas.getObjects();
        const existing = objs.filter((o) => CourtBackdrop.isBackdrop(o));
        if (existing.length === 0) {
            CourtBackdrop.shapes(this.court).forEach((s) => this.canvas.add(s));
        } else {
            // Repair z-order: no drawable may sit below the backdrop.
            const firstDrawable = objs.findIndex((o) => !CourtBackdrop.isBackdrop(o));
            const lastBackdrop = objs.length - 1 - [...objs].reverse().findIndex((o) => CourtBackdrop.isBackdrop(o));
            if (firstDrawable !== -1 && firstDrawable < lastBackdrop) {
                [...existing].reverse().forEach((o) => this.canvas.sendToBack(o));
            }
        }
        // Re-assert the lock: tool switches / JSON loads may have flipped
        // selectable or evented back on.
        CourtBackdrop.lockAll(this.canvas);
        this.canvas.requestRenderAll();
    }

    updateSelectionUI() {
        const overlay = document.getElementById('delete-overlay');
        const activeObj = this.canvas.getActiveObject();
        
        if (activeObj && overlay) {
            overlay.style.display = 'block';
        } else if (overlay) {
            overlay.style.display = 'none';
        }
    }
    
    deleteSelected() {
        const activeObj = this.canvas.getActiveObject();
        if (activeObj) {
            const isBackdrop = (o) => typeof CourtBackdrop !== 'undefined' && CourtBackdrop.isBackdrop(o);
            // The court itself is never deletable.
            if (isBackdrop(activeObj)) {
                this.canvas.discardActiveObject();
                this.canvas.requestRenderAll();
                return;
            }
            // If multiple objects are selected
            if (activeObj.type === 'activeSelection') {
                activeObj.forEachObject(obj => {
                    if (!isBackdrop(obj)) this.canvas.remove(obj);
                });
                this.canvas.discardActiveObject();
            } else {
                this.canvas.remove(activeObj);
            }
            this.canvas.requestRenderAll();
        }
    }

    /**
     * Apply phase rules (multi-action chains resolve in one frame):
     * - Move tokens only when action is connected to a token
     * - Swap Pass Sender -> Square (Number Only)
     * - Swap Pass Receiver -> Circle (Ball Holder)
     * - Handoff = Pass for possession + meet at the ball: the passer comes
     *   to the receiver, so BOTH players end at the handoff line's END
     *   point, placed ADJACENT (shoulder-to-shoulder, never stacked).
     *   A handoff is not a movement action itself.
     * - Chaining: an action starting at another action's end continues with
     *   that token (dribble->dribble, dribble->handoff, handoff->dribble,
     *   cut->pass, pass->dribble, ...). Resolution runs as a worklist to a
     *   fixpoint so a whole drawn sequence applies in a single frame.
     */
    applyActionsAndClearForNextPhase() {
        const objs = this.canvas.getObjects();
        const tokens = objs.filter(o => o.custom?.kind === 'player-token');
        const arrows = objs.filter(o => o.custom?.kind === 'arrow');

        const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
        const near = (a, b, eps) => dist(a, b) <= eps;

        // A line end snaps to tokens/arrows within 40px while drawing
        // (ArrowTool.getSnapPoint), so resolution must accept what snapping
        // produces: a handoff tip snapped to a token border sits ~15px off
        // its center, and a dribble started on that token sits ~15-20px off
        // the handoff tip. Tighter epsilons silently drop such hand-drawn
        // chains (the classic "it isn't working"). Nearest-within-eps wins,
        // so wider windows only claim empty-space ends, never steal tokens.
        const TOKEN_ATTACH_EPS = 28;
        const ARROW_CHAIN_EPS = 24;
        // Shoulder-to-shoulder gap for the handoff meet (token diameter 30).
        const HANDOFF_GAP = 32;

        const getTokenCenter = (tok) => tok.getCenterPoint();

        const findConnectedToken = (pt) => {
            let best = null;
            let bestD = TOKEN_ATTACH_EPS;
            for (const tok of tokens) {
                const c = getTokenCenter(tok);
                const d = dist(c, pt);
                if (d <= bestD) {
                    best = tok;
                    bestD = d;
                }
            }
            return best;
        };

        // --- Phase 1: Analyze & Plan Updates ---
        // We map Token -> { pos: {x,y}, style: 'circle'|'square' }
        const updates = new Map();

        const getUpdate = (tok) => {
            if (!updates.has(tok)) {
                updates.set(tok, {
                    pos: tok.getCenterPoint(),
                    style: tok.custom?.style || 'circle',
                    label: tok.custom?.label || (tok.text || '1'),
                    team: tok.custom?.team || 'offense'
                });
            }
            return updates.get(tok);
        };

        // Planned position (includes moves resolved earlier this frame).
        const plannedPos = (tok) => updates.has(tok) ? updates.get(tok).pos : getTokenCenter(tok);

        const findPlannedToken = (pt) => {
            let best = null;
            let bestD = TOKEN_ATTACH_EPS;
            for (const tok of tokens) {
                const d = dist(plannedPos(tok), pt);
                if (d <= bestD) {
                    best = tok;
                    bestD = d;
                }
            }
            return best;
        };

        const findByEnds = (pt, ends) => {
            for (const e of ends) {
                if (near(pt, e.end, ARROW_CHAIN_EPS)) return e.token;
            }
            return null;
        };

        // Shoulder-to-shoulder spot next to the handoff end point:
        // perpendicular to the handoff direction so the pair never stacks.
        const handoffPartnerPos = (startPt, endPt) => {
            const dx = endPt.x - startPt.x;
            const dy = endPt.y - startPt.y;
            const len = Math.hypot(dx, dy);
            let px;
            let py;
            if (len < 1e-6) {
                px = 1;
                py = 0;
            } else {
                px = -dy / len;
                py = dx / len;
            }
            return { x: endPt.x + px * HANDOFF_GAP, y: endPt.y + py * HANDOFF_GAP };
        };

        // Resolved action ends for chaining (movement ends + ball ends).
        const cutEnds = [];
        const ballEnds = [];

        const moveArrows = arrows.filter(a => a.custom?.type === 'cut' || a.custom?.type === 'dribble');
        const possArrows = arrows.filter(a => a.custom?.type === 'pass' || a.custom?.type === 'handoff');
        const doneMove = new Set();
        const donePoss = new Set();

        const resolveMove = (a) => {
            const startPt = a.custom.start;
            const endPt = a.custom.end;
            // Direct (original or already-planned position) or chained off
            // another action's end (cut/dribble end, or a pass/handoff ball).
            const tok = findConnectedToken(startPt)
                || findPlannedToken(startPt)
                || findByEnds(startPt, cutEnds)
                || findByEnds(startPt, ballEnds);
            if (!tok) return false;
            getUpdate(tok).pos = { x: endPt.x, y: endPt.y };
            cutEnds.push({ end: endPt, token: tok, type: a.custom?.type });
            return true;
        };

        const resolvePossession = (a) => {
            const type = a.custom?.type;
            const startPt = a.custom.start;
            const endPt = a.custom.end;
            const converge = type === 'handoff';

            // SENDER: token at the start (original layout) or chained off a
            // movement end / an earlier ball (dribble->handoff, handoff->... ).
            let sender = findConnectedToken(startPt)
                || findByEnds(startPt, cutEnds)
                || findByEnds(startPt, ballEnds);

            // RECEIVER: token at the end (original layout) or cutting there.
            let receiver = findConnectedToken(endPt)
                || findByEnds(endPt, cutEnds);

            if (!sender && !receiver) return false;

            // The passer comes to the receiver: both meet ADJACENT at the
            // handoff end (receiver on the spot, passer shoulder-to-shoulder).
            const meetPos = converge ? handoffPartnerPos(startPt, endPt) : null;

            // If we found a sender, they lose the ball -> Square
            if (sender) {
                const up = getUpdate(sender);
                // Only change if it's currently a ball-holder (circle)
                if (up.style === 'circle' || up.style === 'dark-circle') {
                    up.style = 'square';
                }
                if (converge) {
                    up.pos = meetPos;
                }
            }

            if (receiver) {
                const up = getUpdate(receiver);
                up.style = 'circle';
                if (converge) {
                    up.pos = { x: endPt.x, y: endPt.y };
                }
                // The ball is now with the receiver here: later actions in
                // the same frame (e.g. dribbles away) continue from it.
                ballEnds.push({ end: endPt, token: receiver });
            }
            return true;
        };

        // Worklist to a fixpoint: each round resolves whatever is now
        // connected, so handoff->dribble->dribble etc. apply in one frame.
        // Movement runs before possession each round (preserves the legacy
        // cut-then-pass ordering for single-action frames), EXCEPT movement
        // drawn away from a pass/handoff end: that continues AFTER the ball
        // arrives, so it resolves in a second wave. Without the split, a
        // dribble starting where the receiver already stands would steal
        // the token before the handoff places (and swaps) it.
        const possEnds = possArrows.map(a => a.custom.end);
        const upstreamMoves = moveArrows.filter(
            a => !possEnds.some(e => near(a.custom.start, e, ARROW_CHAIN_EPS)));
        const runWorklist = (moves, possessions) => {
            let progress = true;
            while (progress) {
                progress = false;
                for (const a of moves) {
                    if (!doneMove.has(a) && resolveMove(a)) {
                        doneMove.add(a);
                        progress = true;
                    }
                }
                for (const a of possessions) {
                    if (!donePoss.has(a) && resolvePossession(a)) {
                        donePoss.add(a);
                        progress = true;
                    }
                }
            }
        };
        // Upstream movement (dribble leading into a handoff) + all
        // possession first...
        runWorklist(upstreamMoves, possArrows);
        // ...then everything still unresolved (handoff->dribble,
        // dribble->dribble continuing from it, pass at a dribble end, ...).
        runWorklist(moveArrows, possArrows);

        // Diagnostics: one line per arrow so a dropped hand-drawn chain
        // ("it isn't working") is visible in the console with coordinates.
        try {
            const tag = (t) => t ? `#${t.custom?.label ?? '?'}@${Math.round(plannedPos(t).x)},${Math.round(plannedPos(t).y)}` : '—';
            for (const a of moveArrows) {
                const st = doneMove.has(a) ? 'ok' : 'DROPPED (no token at start)';
                console.log(`[phase] ${a.custom?.type} ${JSON.stringify(a.custom.start)}->${JSON.stringify(a.custom.end)} ${st}`);
            }
            for (const a of possArrows) {
                const st = donePoss.has(a) ? 'ok' : 'DROPPED (no sender nor receiver)';
                console.log(`[phase] ${a.custom?.type} ${JSON.stringify(a.custom.start)}->${JSON.stringify(a.custom.end)} ${st}`);
            }
            for (const [tok, u] of updates) {
                const c = getTokenCenter(tok);
                console.log(`[phase] token ${tag(tok)} from@${Math.round(c.x)},${Math.round(c.y)} style=${u.style}`);
            }
        } catch (e) { /* logging must never break the phase */ }
        // --- Phase 2: Execute Updates ---
        
        updates.forEach((data, tok) => {
            // Check if we need to replace the object (style change)
            // or just move it.
            const needsReplacement = (data.style !== (tok.custom?.style));
            
            if (needsReplacement) {
                // Remove old, Create new
                let newTok;
                const commonProps = {
                    left: data.pos.x,
                    top: data.pos.y,
                    originX: 'center',
                    originY: 'center',
                    selectable: true,
                    hasControls: true
                };

                if (data.style === 'circle') {
                    newTok = new fabric.Group([
                        new fabric.Circle({
                            radius: 15, fill: '#ffffff', stroke: '#000000', strokeWidth: 1, originX: 'center', originY: 'center'
                        }),
                        new fabric.Text(data.label, {
                            fontSize: 16, fontFamily: 'Arial', fontWeight: 'bold', originX: 'center', originY: 'center'
                        })
                    ], commonProps);
                } else if (data.style === 'square') {
                    newTok = new fabric.Text(data.label, {
                        ...commonProps,
                        fontSize: 20, fontFamily: 'Arial', fontWeight: 'bold', fill: '#000000'
                    });
                } else {
                     return; 
                }

                // Restore Metadata
                newTok.custom = {
                    kind: 'player-token',
                    team: data.team,
                    label: data.label,
                    style: data.style
                };

                newTok.toObject = (function(toObject) {
                    return function() {
                        return fabric.util.object.extend(toObject.call(this), {
                            custom: { kind: 'player-token', ...this.custom }
                        });
                    };
                })(newTok.toObject);

                this.canvas.remove(tok);
                this.canvas.add(newTok);
                newTok.setCoords();

            } else {
                // Just Move
                tok.set({ left: data.pos.x, top: data.pos.y });
                tok.setCoords();
            }
        });

        // --- Phase 3: Cleanup ---
        arrows.forEach(a => this.canvas.remove(a));
        this.canvas.discardActiveObject();
        this.canvas.requestRenderAll();
    }

    // ... (rest of the methods: setMode, saveStateToHistory, selectTool, clearCanvas, mirror, undo, redo, savePlay, loadPlay) ...
    setMode(mode) {
        this.currentMode = mode;
        
        // Update UI Tabs
        document.querySelectorAll('.nav-tab-item').forEach(el => {
            el.classList.remove('active');
        });
        
        const activeTab = document.getElementById(`tab-${mode}`);
        if(activeTab) activeTab.classList.add('active');
        
        // Handle UI Panels
        const notesPanel = document.getElementById('notes-panel');
        if (notesPanel) {
            notesPanel.style.display = (mode === 'notes') ? 'block' : 'none';
        }
        
        console.log(`Switched to ${mode} mode`);
        
        if (mode === 'animate') {
             if (this.sequence) this.sequence.playAnimation(); 
        } else {
             if (this.sequence) this.sequence.stopAnimation();
        }
    }

    saveStateToHistory() {
        if (this.isHistoryLocked || !this.history) return;
        
        const json = JSON.stringify(this.canvas.toJSON(['custom']));
        this.history.pushState(json);
    }

    /**
     * Apply canvas dimensions for a court type without touching objects.
     * Callers load JSON / rebuild the backdrop afterwards.
     */
    applyCourtDims(court) {
        this.court = court === 'full' ? 'full' : 'half';
        if (typeof CourtBackdrop !== 'undefined') {
            const d = CourtBackdrop.dims(this.court);
            this.canvas.setDimensions({ width: d.w, height: d.h });
            this.canvas.setViewportTransform([1, 0, 0, 1, 0, 0]);
            this.canvas.requestRenderAll();
        }
        this.syncCourtToggle();
    }

    syncCourtToggle() {
        document.querySelectorAll('#court-toggle [data-court]').forEach(b => {
            const on = b.dataset.court === this.court;
            b.classList.toggle('active', on);
            b.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
    }

    /**
     * Switch half/full court. The drawing cannot survive a resize (frames
     * belong to one geometry), so a non-empty canvas asks for confirmation
     * and starts fresh on the new court.
     */
    setCourtType(court) {
        court = court === 'full' ? 'full' : 'half';
        if (court === this.court) return;
        const hasDrawing = this.canvas.getObjects().some(
            (o) => !(typeof CourtBackdrop !== 'undefined' && CourtBackdrop.isBackdrop(o)));
        if (hasDrawing && !confirm(`Switch to ${court} court? The current drawing will be cleared.`)) {
            this.syncCourtToggle();
            return;
        }
        this.isHistoryLocked = true;
        this.canvas.clear();
        this.canvas.backgroundColor = 'rgba(0,0,0,0)';
        this.applyCourtDims(court);
        this.isHistoryLocked = false;
        this.ensureCourtBackdrop();
        this.selectTool('select');
        this.saveStateToHistory();
        if (this.layers) this.layers.refresh();
        if (this.sequence) {
            this.sequence.frames = [];
            this.sequence.currentIndex = -1;
            this.sequence.captureCurrentAsFrame('Start');
        }
    }

    selectTool(toolId, el) {
        if (!this.tools[toolId]) {
            console.warn(`Tool ${toolId} not found`);
            return;
        }

        if (this.activeTool) {
            this.activeTool.deactivate();
        }

        // UI Update (legacy toolbar ids, kept for compatibility)
        document.querySelectorAll("#tool-select, #tool-player, #tool-arrow, #tool-text").forEach(el => {
            el.classList.remove("active");
        });
        const btn = document.getElementById(`tool-${toolId}`);
        if (btn) btn.classList.add("active");

        // UI Update (play-builder sidebar buttons)
        const trigger = el instanceof HTMLElement ? el
            : (typeof event !== 'undefined' && event && event.currentTarget instanceof HTMLElement
                ? event.currentTarget : null);
        document.querySelectorAll(".btn-action.active, .btn-misc.active").forEach(b => {
            if (b !== trigger) {
                b.classList.remove("active");
                b.setAttribute('aria-pressed', 'false');
            }
        });
        if (trigger) {
            trigger.classList.add("active");
            trigger.setAttribute('aria-pressed', 'true');
        }
        // Keep the action toolbar in sync when the tool changes
        // programmatically (e.g. one-shot tools auto-switch to select).
        this.syncActionToolbar(toolId, trigger);

        // Activate new tool
        this.activeTool = this.tools[toolId];
        this.activeTool.activate();
    }

    /**
     * Action toolbar entry point: pick an arrow subtype (dribble/pass/cut/
     * screen/shot/handoff) and activate the arrow tool in one call.
     * Single source for clicks AND keyboard shortcuts so the active hint,
     * aria-pressed and highlight can never drift apart.
     */
    setAction(type, el) {
        const known = ['dribble', 'pass', 'cut', 'screen', 'shot', 'handoff'];
        if (!known.includes(type)) return;
        if (this.tools['arrow'] && this.tools['arrow'].setType) {
            this.tools['arrow'].setType(type);
        }
        this.selectTool('arrow', el || document.querySelector(`.btn-action[data-action="${type}"]`));
        this.updateActionHint(type);
    }

    /** Action metadata: label + one-line how-to shown under the toolbar. */
    static actionHint(type) {
        const hints = {
            select: '<strong>Select</strong> — click a player, line or shape to move / edit it. Court lines stay locked.',
            dribble: '<strong>Dribble</strong> — drag from the ball-handler along the dribble path.',
            pass: '<strong>Pass</strong> — drag from passer to receiver (snaps to players).',
            cut: '<strong>Cut</strong> — drag from a player to where they run.',
            screen: '<strong>Screen</strong> — drag to place the screener wall (T-end).',
            shot: '<strong>Shot</strong> — drag from shooter toward the hoop (snaps to rim).',
            handoff: '<strong>Handoff</strong> — drag between the two players involved.',
        };
        return hints[type] || hints.select;
    }

    updateActionHint(type) {
        const hint = document.getElementById('action-hint');
        if (hint) hint.innerHTML = PlayBuilder.actionHint(type);
    }

    syncActionToolbar(toolId, trigger) {
        const toolbar = document.getElementById('action-toolbar');
        if (!toolbar) return;
        // If the change came from a toolbar button, the hint is already set
        // by setAction(); otherwise reflect the new tool state.
        if (trigger && toolbar.contains(trigger)) return;
        const hintType = toolId === 'arrow'
            ? (this.tools['arrow'] ? this.tools['arrow'].currentType : 'pass')
            : 'select';
        toolbar.querySelectorAll('.btn-action').forEach(b => {
            const on = (toolId === 'select' && b.dataset.tool === 'select')
                || (toolId === 'arrow' && b.dataset.action === hintType);
            b.classList.toggle('active', !!on);
            b.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
        this.updateActionHint(toolId === 'arrow' ? hintType : 'select');
    }

    initActionShortcuts() {
        // Single-key shortcuts (V/D/P/C/T/S/H), ignored while typing.
        // Mirrors the tactics-board convention of one key per action.
        document.addEventListener('keydown', (e) => {
            if (e.metaKey || e.ctrlKey || e.altKey) return;
            const tag = (e.target && e.target.tagName || '').toLowerCase();
            if (tag === 'input' || tag === 'textarea' || tag === 'select'
                || (e.target && e.target.isContentEditable)) return;
            // Delete-key handling lives in initEvents; don't double-handle.
            if (e.key === 'Delete' || e.key === 'Backspace') return;
            const k = (e.key || '').toLowerCase();
            const map = { v: 'select', d: 'dribble', p: 'pass', c: 'cut', t: 'screen', s: 'shot', h: 'handoff' };
            if (!map[k]) return;
            e.preventDefault();
            if (map[k] === 'select') this.selectTool('select');
            else this.setAction(map[k]);
        });
    }
    
    clearCanvas() {
        if(confirm("Clear all objects?")) {
            this.isHistoryLocked = true;
            this.canvas.clear();
            this.canvas.backgroundColor = 'rgba(0,0,0,0)'; 
            
            this.isHistoryLocked = false;
            this.ensureCourtBackdrop();
            this.saveStateToHistory();
            if(this.layers) this.layers.refresh();
        }
    }
    
    mirror() {
        if (!this.canvas) return;
        
        const width = this.canvas.getWidth();
        const center = width / 2;
        
        // Save state before modification
        this.saveStateToHistory();

        this.canvas.getObjects().forEach(obj => {
            // Court backdrop orientation is fixed: never mirror it.
            if (typeof CourtBackdrop !== 'undefined' && CourtBackdrop.isBackdrop(obj)) return;
            // Calculate new left position for originX=center
            if (obj.originX === 'center') {
                obj.set('left', width - obj.left);
            } else {
                // If originX is left
                obj.set('left', width - (obj.left + obj.getScaledWidth()));
            }

            // Mirror angle
            if (obj.angle !== 0) {
                obj.set('angle', -obj.angle);
            }
            
            obj.setCoords();
        });
        
        this.canvas.renderAll();
        // Trigger updates manually since we modified existing objects in batch
        // and we might be inside a bulk operation
        this.saveStateToHistory();
        if(this.layers) this.layers.refresh();
        if(this.sequence) this.sequence.updateCurrentFrameData();
    }

    undo() {
        if (!this.history || !this.history.canUndo()) return;
        
        const prevState = this.history.undo();
        if (prevState) {
            this.isHistoryLocked = true;
            this.canvas.loadFromJSON(prevState, () => {
                if (typeof CourtBackdrop !== 'undefined') CourtBackdrop.lockAll(this.canvas);
                this.canvas.renderAll();
                this.isHistoryLocked = false;
                if(this.layers) this.layers.refresh();
                if(this.sequence) this.sequence.updateCurrentFrameData();
            });
        }
    }

    redo() {
        if (!this.history || !this.history.canRedo()) return;

        const nextState = this.history.redo();
        if (nextState) {
            this.isHistoryLocked = true;
            this.canvas.loadFromJSON(nextState, () => {
                if (typeof CourtBackdrop !== 'undefined') CourtBackdrop.lockAll(this.canvas);
                this.canvas.renderAll();
                this.isHistoryLocked = false;
                if(this.layers) this.layers.refresh();
                if(this.sequence) this.sequence.updateCurrentFrameData();
            });
        }
    }

    async savePlay() {
        const statusSpan = document.getElementById("status-bar");
        if(statusSpan) statusSpan.innerText = "Saving...";

        const nameInput = document.getElementById("meta-name");
        const typeInput = document.getElementById("meta-type");
        const descInput = document.getElementById("meta-description");
        const tagsInput = document.getElementById("meta-tags");
        
        const name = nameInput ? nameInput.value : "Untitled Play";
        const type = typeInput ? typeInput.value : "Offense";
        const desc = descInput ? descInput.value : "";
        const tags = tagsInput ? tagsInput.value : "";

        if (!name) {
            alert("Please enter a Play Name.");
            if(statusSpan) statusSpan.innerText = "Error: Name required";
            return;
        }

        // Current canvas state
        const canvasJson = this.canvas.toJSON(['custom']);
        
        // --- SVG Generation with Background ---
        // The court travels with the canvas as locked backdrop objects, so
        // toSVG() already contains it. Only legacy saves (no backdrop)
        // need the injected shared halfcourt, nested centered.
        const CW = this.canvas.getWidth();
        const CH = this.canvas.getHeight();
        const hasBackdrop = this.canvas.getObjects().some(
            (o) => o.custom && o.custom.kind === 'court-backdrop'
        );
        const sharedCourt = (typeof window !== 'undefined' && window.COURT_SVG_INNER && this.court !== 'full')
            ? `<svg x="150" y="15" width="500" height="470" viewBox="0 0 500 470">${window.COURT_SVG_INNER}</svg>`
            : '';
        const fullFallback = `<rect width="800" height="1000" fill="#e8c89b"/>` +
            `<rect x="150" y="30" width="500" height="940" fill="none" stroke="#ffffff" stroke-width="3"/>` +
            `<line x1="150" y1="500" x2="650" y2="500" stroke="#ffffff" stroke-width="3"/>`;
        const courtSvgContent = hasBackdrop
            ? ''
            : (sharedCourt
            || (this.court === 'full' ? fullFallback
            : '<rect width="800" height="500" fill="#e8c89b"/><rect x="150" y="15" width="500" height="470" fill="none" stroke="#ffffff" stroke-width="3"/><rect x="320" y="15" width="160" height="190" fill="none" stroke="#ffffff" stroke-width="3"/><path d="M 320 205 A 60 60 0 1 1 480 205" fill="none" stroke="#ffffff" stroke-width="3"/><path d="M 320 205 A 60 60 0 0 0 480 205" fill="none" stroke="#ffffff" stroke-width="3" stroke-dasharray="10,10"/><line x1="370" y1="55" x2="430" y2="55" stroke="#ffffff" stroke-width="3"/><circle cx="400" cy="67.5" r="7.5" fill="none" stroke="#333" stroke-width="2"/><path d="M 180 15 L 180 157 A 237.5 237.5 0 0 0 620 157 L 620 15" fill="none" stroke="#ffffff" stroke-width="3"/><path d="M 340 485 A 60 60 0 1 1 460 485" fill="none" stroke="#ffffff" stroke-width="3"/><line x1="150" y1="485" x2="650" y2="485" stroke="#ffffff" stroke-width="3"/>'));
        
        // Get the canvas objects SVG
        let objectsSvg = this.canvas.toSVG({
            viewBox: { x: 0, y: 0, width: CW, height: CH },
            width: CW,
            height: CH,
            suppressPreamble: true // Don't include <?xml ... ?> header
        });
        
        // Manually construct the final SVG
        // 1. Extract the content inside the <svg> tags from Fabric's output
        const svgBody = objectsSvg.substring(objectsSvg.indexOf('>') + 1, objectsSvg.lastIndexOf('</svg>'));
        
        // 2. Combine: Header + Court + Canvas Objects + Footer
        const diagramSvg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${CW} ${CH}" width="${CW}" height="${CH}" preserveAspectRatio="xMidYMid meet">${courtSvgContent}${svgBody}</svg>`;
        
        // ----------------------------------------
        
        // Frames data
        const frames = this.sequence ? this.sequence.frames : [];

        const payload = {
            play_id: this.config.playId ? parseInt(this.config.playId) : null,
            metadata: {
                name: name,
                play_type: type,
                description: desc,
                tags: tags,
                court_type: this.court
            },
            canvas_json: canvasJson,
            diagram_svg: diagramSvg,
            frames: frames 
        };
        
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');

        try {
            const res = await fetch(`${this.config.apiBase}/plays/api/save-canvas`, {
                method: "POST",
                headers: { 
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken
                },
                body: JSON.stringify(payload)
            });
            
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            
            const data = await res.json();

            if (data.success) {
                if(statusSpan) statusSpan.innerText = "Saved!";
                if (!this.config.playId && data.play_id) {
                    window.history.pushState({}, "", `/plays/${data.play_id}/edit-builder`);
                    this.config.playId = data.play_id;
                }
            } else {
                if(statusSpan) statusSpan.innerText = "Error: " + data.error;
                alert("Save failed: " + data.error);
            }
        } catch (err) {
            console.error(err);
            if(statusSpan) statusSpan.innerText = "Network Error";
            alert("Save failed. Check console for details.");
        }
    }

    async loadPlay(playId) {
        const statusSpan = document.getElementById("status-bar");
        if(statusSpan) statusSpan.innerText = "Loading...";
        
        this.isHistoryLocked = true;

        try {
            const res = await fetch(`${this.config.apiBase}/plays/api/load-canvas/${playId}`);
            const data = await res.json();

            if (data.success) {
                // Apply the saved court size BEFORE loading objects, so the
                // backdrop rebuilt afterwards matches the save geometry.
                if (data.metadata && data.metadata.court_type) {
                    this.applyCourtDims(data.metadata.court_type);
                }
                if (data.metadata) {
                    const nameInput = document.getElementById("meta-name");
                    const typeInput = document.getElementById("meta-type");
                    const descInput = document.getElementById("meta-description");
                    const tagsInput = document.getElementById("meta-tags");
                    
                    if(nameInput) nameInput.value = data.metadata.name || "";
                    if(typeInput) typeInput.value = data.metadata.play_type || "Offense";
                    if(descInput) descInput.value = data.metadata.description || "";
                    if(tagsInput) tagsInput.value = data.metadata.tags || "";
                }

                if (data.canvas_json) {
                    this.canvas.loadFromJSON(data.canvas_json, () => {
                        if (typeof CourtBackdrop !== 'undefined') CourtBackdrop.lockAll(this.canvas);
                        this.canvas.renderAll();
                        // Legacy saves predate the canvas-drawn backdrop.
                        this.ensureCourtBackdrop();
                        if(statusSpan) statusSpan.innerText = "Ready";
                        this.selectTool('select');
                        
                        this.isHistoryLocked = false;
                        this.saveStateToHistory(); 
                        if(this.layers) this.layers.refresh();
                        
                        if (data.frames && data.frames.length > 0 && this.sequence) {
                             this.sequence.frames = data.frames;
                             this.sequence.currentIndex = 0;
                             this.sequence.renderTimeline();
                        } else if (this.sequence) {
                             this.sequence.captureCurrentAsFrame("Start");
                        }
                    });
                } else {
                    if(statusSpan) statusSpan.innerText = "Ready (Empty)";
                    this.selectTool('select');
                    this.isHistoryLocked = false;
                    this.saveStateToHistory();
                    if(this.layers) this.layers.refresh();
                    if (this.sequence) this.sequence.captureCurrentAsFrame("Start");
                }
            } else {
                if(statusSpan) statusSpan.innerText = "Error loading play";
                this.isHistoryLocked = false;
            }
        } catch (err) {
            console.error(err);
            if(statusSpan) statusSpan.innerText = "Error loading play";
            this.isHistoryLocked = false;
        }
    }
}

document.addEventListener("DOMContentLoaded", () => {
    window.app = new PlayBuilder("playCanvas");
});
