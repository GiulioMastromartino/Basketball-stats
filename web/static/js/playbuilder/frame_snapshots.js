/**
 * Phase snapshot renderer (shared).
 *
 * Re-renders Fabric frame JSON into standalone SVG stills on an offscreen
 * canvas, so PDF exports can storyboard animations without a canvas
 * runtime server-side. Used by the playbuilder (save time) and by the
 * training page (on-demand backfill for legacy plays at PDF export).
 *
 * window.renderPhaseSnapshots(frames, opts) -> Promise<Array<string|null>>
 *   frames: [{ data: <fabric canvas JSON>, caption: <str> }, ...]
 *   opts: { width, height, court: 'half'|'full', courtSvgInner: <str|null> }
 *     courtSvgInner is inlined for legacy frames whose JSON predates the
 *     locked court-backdrop objects (same asset the builder injects).
 */
(function () {
    'use strict';

    const FULL_FALLBACK =
        '<rect width="800" height="1000" fill="#e8c89b"/>' +
        '<rect x="150" y="30" width="500" height="940" fill="none" stroke="#ffffff" stroke-width="3"/>' +
        '<line x1="150" y1="500" x2="650" y2="500" stroke="#ffffff" stroke-width="3"/>';

    const HALF_FALLBACK =
        '<rect width="800" height="500" fill="#e8c89b"/>' +
        '<rect x="150" y="15" width="500" height="470" fill="none" stroke="#ffffff" stroke-width="3"/>' +
        '<rect x="320" y="15" width="160" height="190" fill="none" stroke="#ffffff" stroke-width="3"/>' +
        '<path d="M 320 205 A 60 60 0 1 1 480 205" fill="none" stroke="#ffffff" stroke-width="3"/>' +
        '<path d="M 320 205 A 60 60 0 0 0 480 205" fill="none" stroke="#ffffff" stroke-width="3" stroke-dasharray="10,10"/>' +
        '<line x1="370" y1="55" x2="430" y2="55" stroke="#ffffff" stroke-width="3"/>' +
        '<circle cx="400" cy="67.5" r="7.5" fill="none" stroke="#333" stroke-width="2"/>' +
        '<path d="M 180 15 L 180 157 A 237.5 237.5 0 0 0 620 157 L 620 15" fill="none" stroke="#ffffff" stroke-width="3"/>' +
        '<path d="M 340 485 A 60 60 0 1 1 460 485" fill="none" stroke="#ffffff" stroke-width="3"/>' +
        '<line x1="150" y1="485" x2="650" y2="485" stroke="#ffffff" stroke-width="3"/>';

    window.renderPhaseSnapshots = async function (frames, opts) {
        opts = opts || {};
        const width = opts.width || 800;
        const height = opts.height || 500;
        const court = opts.court === 'full' ? 'full' : 'half';
        const courtInner = typeof opts.courtSvgInner === 'string' ? opts.courtSvgInner : null;

        if (!Array.isArray(frames) || frames.length === 0) return [];
        if (typeof fabric === 'undefined' || !fabric.StaticCanvas) {
            return frames.map(function () { return null; });
        }

        const courtFor = function (hasBackdrop) {
            if (hasBackdrop) return '';
            if (courtInner && court !== 'full') {
                return `<svg x="150" y="15" width="500" height="470" viewBox="0 0 500 470">${courtInner}</svg>`;
            }
            return court === 'full' ? FULL_FALLBACK : HALF_FALLBACK;
        };

        const snapCanvas = new fabric.StaticCanvas(null, { width: width, height: height });
        const loadSnap = function (data) {
            return new Promise(function (resolve) {
                try {
                    snapCanvas.loadFromJSON(data, function () {
                        snapCanvas.renderAll();
                        resolve(true);
                    });
                } catch (e) { resolve(false); }
            });
        };

        const out = [];
        for (const fr of frames) {
            let snap = null;
            try {
                if (fr && fr.data && await loadSnap(fr.data)) {
                    const objs = Array.isArray(fr.data.objects) ? fr.data.objects : [];
                    const hasBackdrop = objs.some(
                        function (o) { return o && o.custom && o.custom.kind === 'court-backdrop'; }
                    );
                    const rendered = snapCanvas.toSVG({
                        viewBox: { x: 0, y: 0, width: width, height: height },
                        width: width,
                        height: height,
                        suppressPreamble: true
                    });
                    const body = rendered.substring(
                        rendered.indexOf('>') + 1, rendered.lastIndexOf('</svg>'));
                    if (body) {
                        snap = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" preserveAspectRatio="xMidYMid meet">${courtFor(hasBackdrop)}${body}</svg>`;
                    }
                }
            } catch (e) {
                console.warn('Phase snapshot failed, skipping:', e);
            }
            out.push(snap);
        }
        if (snapCanvas.dispose) snapCanvas.dispose();
        return out;
    };
})();
