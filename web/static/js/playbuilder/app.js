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
        this.currentMode = 'draw'; // 'draw' | 'animate'

        // Configuration
        this.config = window.PlayBuilderConfig || {};
        
        // Initialize Tools & Managers
        this.initTools();
        this.initHistory();
        this.initLayers();
        this.initSequence();
        this.initEvents();

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

    /**
     * Apply phase rules:
     * - Move tokens only when action is connected to a token
     * - For passes: swap "number-only" token into circled-number token at the end
     * - If pass starts from end of a cut, treat it as the cut continuation (pass start becomes cut start)
     * - Delete all action arrows after applying (clean next phase)
     */
    applyActionsAndClearForNextPhase() {
        const objs = this.canvas.getObjects();

        // Collect tokens and arrows
        const tokens = objs.filter(o => o.custom?.kind === 'player-token');
        const arrows = objs.filter(o => o.custom?.kind === 'arrow');

        const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
        const near = (a, b, eps) => dist(a, b) <= eps;

        const TOKEN_ATTACH_EPS = 22; // how close must a line endpoint be to count as "connected" to a token
        const ARROW_CHAIN_EPS = 10;  // how close to chain pass start to cut end

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

        // 1) Build quick index of cut ends (for pass chaining)
        const cutEnds = arrows
            .filter(a => a.custom?.type === 'cut')
            .map(a => ({ arrow: a, end: a.custom.end, start: a.custom.start }));

        // 2) Apply movement actions (cut/dribble) ONLY if connected to a token
        for (const a of arrows) {
            const type = a.custom?.type;
            if (type !== 'cut' && type !== 'dribble') continue;

            const startPt = a.custom.start;
            const endPt = a.custom.end;

            const tok = findConnectedToken(startPt);
            if (!tok) continue; // safer: only move if action is connected

            tok.set({ left: endPt.x, top: endPt.y });
            tok.setCoords();
        }

        // 3) Apply pass visuals rule: at end of pass, swap number-only token -> circled token
        // Also: if pass starts from end of a cut, treat it as cut continuation (pass start = cut start)
        for (const a of arrows) {
            if (a.custom?.type !== 'pass') continue;

            let passStart = a.custom.start;
            const passEnd = a.custom.end;

            // If pass starts at cut end, use cut start for "connection" evaluation (combine)
            for (const ce of cutEnds) {
                if (near(passStart, ce.end, ARROW_CHAIN_EPS)) {
                    passStart = ce.start;
                    break;
                }
            }

            // Find the receiver token connected to pass end
            const receiver = findConnectedToken(passEnd);
            if (!receiver) continue;

            // Swap number-only (square style) -> circled number
            // We persist style now in token.custom.style.
            if (receiver.custom?.style === 'square' && receiver.type === 'text') {
                const label = receiver.text || receiver.custom?.label || '';
                const center = receiver.getCenterPoint();

                const newTok = new fabric.Group([
                    new fabric.Circle({
                        radius: 15, fill: '#ffffff', stroke: '#000000', strokeWidth: 1, originX: 'center', originY: 'center'
                    }),
                    new fabric.Text(label, {
                        fontSize: 16, fontFamily: 'Arial', fontWeight: 'bold', originX: 'center', originY: 'center'
                    })
                ], {
                    left: center.x,
                    top: center.y,
                    originX: 'center',
                    originY: 'center',
                    selectable: true,
                    hasControls: true
                });

                // Preserve custom metadata
                newTok.custom = {
                    kind: 'player-token',
                    team: receiver.custom?.team,
                    label: receiver.custom?.label || label,
                    style: 'circle'
                };

                // Preserve serialization of custom
                newTok.toObject = (function(toObject) {
                    return function() {
                        return fabric.util.object.extend(toObject.call(this), {
                            custom: { kind: 'player-token', ...this.custom }
                        });
                    };
                })(newTok.toObject);

                this.canvas.remove(receiver);
                this.canvas.add(newTok);
                newTok.setCoords();
            }
        }

        // 4) Delete all actions (arrows) for the next phase
        arrows.forEach(a => this.canvas.remove(a));

        // NOTE: if curve edit handles were left around, they should be removed by deselection.
        this.canvas.discardActiveObject();
        this.canvas.requestRenderAll();
    }
}

document.addEventListener("DOMContentLoaded", () => {
    window.app = new PlayBuilder("playCanvas");
});
