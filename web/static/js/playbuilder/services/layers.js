/**
 * Layers Panel Service
 * Manages the list of objects in the sidebar.
 */
class LayersPanel {
    constructor(canvas, listId) {
        this.canvas = canvas;
        this.listElement = document.getElementById(listId);
    }

    refresh() {
        if (!this.listElement) return;
        this.listElement.innerHTML = '';

        // Get objects in reverse order (top to bottom visually)
        // Fabric stores bottom-to-top in array
        const objects = this.canvas.getObjects().slice().reverse();

        objects.forEach((obj, index) => {
            // Skip court lines and the locked court backdrop
            if (obj.custom?.kind === 'court-line') return;
            if (obj.custom?.kind === 'court-backdrop') return;

            const li = document.createElement('li');
            li.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-center p-2';
            li.style.cursor = 'pointer';
            
            // Determine Label
            let label = "Object";
            let icon = "fa-square";
            
            if (obj.custom?.kind === 'player-token') {
                label = `Player ${obj.custom.label || ''}`;
                icon = "fa-user-circle";
            } else if (obj.custom?.kind === 'arrow') {
                label = `Arrow (${obj.custom.type})`;
                icon = "fa-long-arrow-alt-right";
            } else if (obj.custom?.kind === 'text') {
                label = `Text: "${obj.text?.substring(0, 10)}..."`;
                icon = "fa-font";
            }

            // Active state
            const isActive = this.canvas.getActiveObject() === obj;
            if (isActive) li.classList.add('active');

            // Build row with DOM APIs: label holds user-controlled text
            // (player labels, text objects) so it must go through
            // textContent, never innerHTML (stored XSS otherwise).
            const row = document.createElement('span');
            const glyph = document.createElement('i');
            glyph.className = `fas ${icon} me-2`;
            row.appendChild(glyph);
            row.appendChild(document.createTextNode(label));
            const del = document.createElement('span');
            del.className = 'badge bg-light text-dark rounded-pill action-btn delete-btn';
            del.title = 'Delete';
            del.textContent = '×';
            li.appendChild(row);
            li.appendChild(del);

            // Click to select
            li.addEventListener('click', (e) => {
                // If clicked delete button
                if (e.target.classList.contains('delete-btn')) {
                    this.canvas.remove(obj);
                    this.canvas.requestRenderAll();
                    // App events will trigger refresh via history/app listeners usually,
                    // but we might need to manually trigger history save if not covered.
                    // (App handles object:removed)
                    return;
                }
                
                this.canvas.setActiveObject(obj);
                this.canvas.requestRenderAll();
            });

            this.listElement.appendChild(li);
        });

        if (this.listElement.children.length === 0) {
            this.listElement.innerHTML = '<li class="list-group-item text-muted text-center">No objects</li>';
        }
    }
}
