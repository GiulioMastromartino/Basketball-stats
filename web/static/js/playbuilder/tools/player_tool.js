/**
 * Player Tool
 * Places player tokens (numbered circles) on the canvas.
 */
class PlayerTool extends ToolBase {
    constructor(canvas) {
        super(canvas);
        this.currentLabel = "1";
        this.currentColor = "#000000"; // Black text/stroke
        this.fillColor = "#ffffff"; // White fill
    }

    activate() {
        super.activate();
        this.canvas.defaultCursor = 'crosshair';
        this.canvas.selection = false;
    }

    onMouseDown(opt) {
        // Get pointer relative to canvas
        const pointer = this.canvas.getPointer(opt.e);
        
        // Create circle
        const circle = new fabric.Circle({
            radius: 15,
            fill: this.fillColor,
            stroke: this.currentColor,
            strokeWidth: 2,
            originX: 'center',
            originY: 'center'
        });

        // Create text
        const text = new fabric.Text(this.currentLabel, {
            fontSize: 16,
            fontFamily: 'Arial',
            fill: this.currentColor,
            originX: 'center',
            originY: 'center',
            fontWeight: 'bold'
        });

        // Group them
        const group = new fabric.Group([circle, text], {
            left: pointer.x,
            top: pointer.y,
            originX: 'center',
            originY: 'center',
            selectable: true,
            hasControls: false, // Don't allow scaling/rotation for tokens usually
            hasBorders: true
        });

        // Add custom property
        group.toObject = (function(toObject) {
            return function() {
                return fabric.util.object.extend(toObject.call(this), {
                    custom: { 
                        kind: 'player-token',
                        label: text.text 
                    }
                });
            };
        })(group.toObject);
        group.custom = { kind: 'player-token', label: this.currentLabel };

        this.canvas.add(group);
        this.canvas.setActiveObject(group);
        this.canvas.requestRenderAll();
    }
    
    setLabel(label) {
        this.currentLabel = label;
    }
    
    setTeam(team) {
        // Example styling for different teams
        if (team === 'offense') {
            this.currentColor = '#000000';
            this.fillColor = '#ffffff';
        } else if (team === 'defense') {
            this.currentColor = '#b30000'; // Dark red
            this.fillColor = '#ffe6e6';
        }
    }
}
