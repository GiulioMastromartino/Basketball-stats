# Plays Builder (Fabric.js) - Feature Plan

Branch: Plays-creation-super-feature

## Goal (vertical slice)
User can open a Play Builder page, draw at least one object on a Fabric canvas, save it to DB as Fabric JSON, reload it, and view the saved play.
Server-side rendering (Node.js + Fabric.js) is used to generate high-fidelity static images (SVG/PNG) from the saved JSON.

## Phases
### Phase 1 — Foundation
- DB: Add Play fields
  - `plays.canvas_data` (JSON, nullable): Fabric canvas JSON (Source of Truth)
  - `plays.diagram_svg` (TEXT, nullable): cached SVG export (generated server-side)
  - `plays.image_filename` (String, nullable): path to generated PNG
  - `plays.difficulty` (string default "Medium")
  - `plays.personnel_required` (TEXT, nullable)
  - `plays.tags` (TEXT, nullable)
- (Optional stub) `play_sequences` table
- Routes
  - GET `/plays/create` → builder page (empty canvas)
  - GET `/plays/<id>/edit-builder` → builder page with play_id
  - API: POST `/plays/api/save-canvas` → create/update play with metadata + canvas_json
  - API: GET `/plays/api/load-canvas/<id>` → return stored canvas_json + metadata

### Phase 2 — Core Tools (client-side)
Architecture
- `PlayBuilder` class: canvas instance, tool state machine, history stack, layers panel
- Tools lifecycle (`activate`/`deactivate`) to prevent event listener leaks.

Tools (MVP)
- **Select tool** (default): selection/transform
- **Player tool**: Circle + Text group, custom props
- **Arrow tool**: Line + Triangle head, quadratic curve support
- **Text tool**: IText for annotations

### Phase 3 — Save/Load + Server-side Export (Option B)
Strategy
- **Source of Truth**: `plays.canvas_data` (Fabric JSON) stored in SQLite/Postgres.
- **Rendering**: Server-side pipeline using Node.js + `fabric` (npm).
  - Flask triggers a render task (sync for MVP, async later).
  - Node script reads JSON, uses `fabric.StaticCanvas` to render, outputs SVG/PNG.
  - Flask updates `plays.diagram_svg` and `plays.image_filename`.

Implementation Steps
1. Install Node.js in environment (update Dockerfile if needed).
2. Create `render_play.js` script (requires `fabric`, `canvas`, `jsdom`).
3. Flask endpoint triggers `subprocess.run(['node', 'render_play.js', play_id])`.

## Folder layout
```
web/templates/plays/
  create.html
web/static/js/playbuilder/
  app.js
  tools/
  services/
  state/
scripts/
  render_play.js (Node script)
  package.json (for fabric dependencies)
```

## Commit-by-commit plan
- 01 docs: add feature_plays.md
- 02 db: migration + Play model fields (canvas_data, diagram_svg, etc)
- 03 backend: builder routes (create/edit) + API skeleton
- 04 backend: save/load API implementation
- 05 frontend: basic builder layout (create.html) + Fabric.js init
- 06 frontend: PlayBuilder architecture (ToolBase, init)
- 07 frontend: SelectTool implementation
- 08 frontend: PlayerTool implementation
- 09 frontend: ArrowTool implementation
- 10 frontend: TextTool implementation
- 11 frontend: History/Undo/Redo
- 12 frontend: LayersPanel
- 13 infra: Add Node.js + package.json for server-side rendering
- 14 backend: Implement server-side rendering trigger (call node script)
- 15 integration: Connect Save button to Save API + Auto-trigger Render
- 16 cleanup: Validation, final manual tests

## Manual test checklist
1. Migration: Upgrade/downgrade works.
2. Builder: Draw objects -> Save -> Reload -> Objects appear identical.
3. Render: Save -> Check server logs -> Verify generated PNG/SVG exists on disk.
4. Tools: Switch tools repeatedly, verify no duplicate event firing.
