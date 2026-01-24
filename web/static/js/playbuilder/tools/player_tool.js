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
        this.currentStyle = "circle"; // circle, square, text, dark-circle
    }

    activate() {
        super.activate();
        this.canvas.defaultCursor = 'crosshair';
        this.canvas.selection = false;
    }

    onMouseDown(opt) {
        // Get pointer relative to canvas
        const pointer = this.canvas.getPointer(opt.e);
        
        let visual;
        
        if (this.currentStyle === 'text') {
             // Just text (e.g. Defense x)
             visual = new fabric.Text(this.currentLabel, {
                fontSize: 24,
                fontFamily: 'Arial',
                fill: this.currentColor,
                originX: 'center',
                originY: 'center',
                fontWeight: 'bold'
             });
        } else if (this.currentStyle === 'square') {
             const rect = new fabric.Rect({
                width: 30,
                height: 30,
                fill: this.fillColor,
                stroke: this.currentColor,
                strokeWidth: 2,
                originX: 'center',
                originY: 'center',
                rx: 4, 
                ry: 4
             });
             const text = new fabric.Text(this.currentLabel, {
                fontSize: 16,
                fontFamily: 'Arial',
                fill: this.currentColor,
                originX: 'center',
                originY: 'center',
                fontWeight: 'bold'
             });
             visual = new fabric.Group([rect, text], { originX: 'center', originY: 'center' });
        } else {
             // Circle (default)
             const circle = new fabric.Circle({
                radius: 15,
                fill: this.fillColor,
                stroke: this.currentColor,
                strokeWidth: 2,
                originX: 'center',
                originY: 'center'
             });
             const text = new fabric.Text(this.currentLabel, {
                fontSize: 16,
                fontFamily: 'Arial',
                fill: this.currentStyle === 'dark-circle' ? '#ffffff' : this.currentColor,
                originX: 'center',
                originY: 'center',
                fontWeight: 'bold'
             });
             visual = new fabric.Group([circle, text], { originX: 'center', originY: 'center' });
        }

        // Set group properties
        visual.set({
            left: pointer.x,
            top: pointer.y,
            selectable: true,
            hasControls: false, // Don't allow scaling/rotation for tokens usually
            hasBorders: true
        });

        // Add custom property
        visual.toObject = (function(toObject) {
            return function() {
                return fabric.util.object.extend(toObject.call(this), {
                    custom: { 
                        kind: 'player-token',
                        label: this.custom?.label || '',
                        team: this.custom?.team || 'offense'
                    }
                });
            };
        })(visual.toObject);
        visual.custom = { 
            kind: 'player-token', 
            label: this.currentLabel, 
            team: this.currentColor === '#000000' ? 'offense' : 'defense' // approximate
        };

        this.canvas.add(visual);
        this.canvas.setActiveObject(visual);
        this.canvas.requestRenderAll();
        
        // Auto-switch to Select tool
        if (window.app) {
            window.app.selectTool('select');
        }
    }
    
    setProps(props) {
        if (props.label) this.currentLabel = props.label;
        if (props.team) this.setTeam(props.team);
        if (props.style) this.currentStyle = props.style;
    }
    
    setTeam(team) {
        if (team === 'offense') {
            this.currentColor = '#000000';
            this.fillColor = '#ffffff';
        } else if (team === 'defense') {
            this.currentColor = '#333333'; 
            this.fillColor = '#f0f0f0';
            
            if (this.currentStyle === 'dark-circle') {
                this.fillColor = '#333333';
                this.currentColor = '#ffffff'; // Text color
            }
        }
    }
}
