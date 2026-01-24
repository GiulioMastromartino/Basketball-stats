/**
 * Player Tool
 * Places player tokens (offense/defense) on the canvas.
 */
class PlayerTool extends ToolBase {
    constructor(canvas) {
        super(canvas);
        this.currentProps = {
            label: '1',
            team: 'offense', // offense | defense
            style: 'circle'  // circle | square | text | dark-circle
        };
    }

    activate() {
        super.activate();
        this.canvas.defaultCursor = 'crosshair';
        this.canvas.selection = false;
        console.log("Player tool activated:", this.currentProps);
    }
    
    setProps(props) {
        this.currentProps = { ...this.currentProps, ...props };
        console.log("Player props updated:", this.currentProps);
    }

    onMouseDown(opt) {
        // Enforce one-shot: if clicking existing object, switch to select
        if (opt.target) {
            if (window.app) window.app.selectTool('select');
            return;
        }

        const pointer = this.canvas.getPointer(opt.e);
        let playerObj;
        
        const commonProps = {
            left: pointer.x,
            top: pointer.y,
            originX: 'center',
            originY: 'center',
            selectable: true,
            hasControls: true
        };

        if (this.currentProps.style === 'circle') {
            playerObj = new fabric.Group([
                new fabric.Circle({
                    radius: 15, fill: '#ffffff', stroke: '#000000', strokeWidth: 1, originX: 'center', originY: 'center'
                }),
                new fabric.Text(this.currentProps.label, {
                    fontSize: 16, fontFamily: 'Arial', fontWeight: 'bold', originX: 'center', originY: 'center'
                })
            ], commonProps);
        } else if (this.currentProps.style === 'square') {
             playerObj = new fabric.Group([
                new fabric.Rect({
                    width: 30, height: 30, fill: '#ffffff', stroke: '#000000', strokeWidth: 1, originX: 'center', originY: 'center', rx: 4, ry: 4
                }),
                new fabric.Text(this.currentProps.label, {
                    fontSize: 16, fontFamily: 'Arial', fontWeight: 'bold', originX: 'center', originY: 'center'
                })
            ], commonProps);
        } else if (this.currentProps.style === 'text') {
             // Defense 'x' usually
             playerObj = new fabric.Text(this.currentProps.label, {
                ...commonProps,
                fontSize: 24, fontFamily: 'monospace', fontWeight: 'bold', fill: '#333'
             });
        } else if (this.currentProps.style === 'dark-circle') {
             playerObj = new fabric.Group([
                new fabric.Circle({
                    radius: 15, fill: '#333333', stroke: '#000000', strokeWidth: 1, originX: 'center', originY: 'center'
                }),
                new fabric.Text(this.currentProps.label, {
                    fontSize: 16, fontFamily: 'Arial', fontWeight: 'bold', fill: '#ffffff', originX: 'center', originY: 'center'
                })
            ], commonProps);
        }
        
        if (playerObj) {
            // Custom serialization
            playerObj.toObject = (function(toObject) {
                return function() {
                    return fabric.util.object.extend(toObject.call(this), {
                        custom: { kind: 'player-token', ...this.custom }
                    });
                };
            })(playerObj.toObject);
            
            playerObj.custom = { 
                kind: 'player-token', 
                team: this.currentProps.team,
                label: this.currentProps.label
            };
            
            this.canvas.add(playerObj);
            this.canvas.setActiveObject(playerObj);
            this.canvas.requestRenderAll();
        }
        
        // Auto-switch to Select tool (One-Shot)
        if (window.app) {
            window.app.selectTool('select');
        }
    }
}
