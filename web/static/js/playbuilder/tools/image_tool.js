/**
 * Image Tool
 * Handles uploading and placing images on the canvas.
 */
class ImageTool extends ToolBase {
    constructor(canvas) {
        super(canvas);
        this.fileInput = null;
        this.initInput();
    }

    initInput() {
        // Create hidden file input
        this.fileInput = document.createElement('input');
        this.fileInput.type = 'file';
        this.fileInput.accept = 'image/*';
        this.fileInput.style.display = 'none';
        document.body.appendChild(this.fileInput);

        // Bind change event
        this.fileInput.addEventListener('change', (e) => {
            this.handleFileSelect(e);
        });
    }

    activate() {
        super.activate();
        // Trigger upload immediately when tool is selected
        // Then switch back to select tool because Image tool doesn't have a "drawing" state
        this.triggerUpload();
        if (window.app) {
            window.app.selectTool('select');
        }
    }

    triggerUpload() {
        if (this.fileInput) {
            this.fileInput.click();
        }
    }

    handleFileSelect(e) {
        const file = e.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (f) => {
            const data = f.target.result;
            fabric.Image.fromURL(data, (img) => {
                // Scale down if too big
                const maxWidth = 200;
                if (img.width > maxWidth) {
                    img.scaleToWidth(maxWidth);
                }

                img.set({
                    left: 400, // Center of canvas (approx)
                    top: 250,
                    originX: 'center',
                    originY: 'center'
                });

                // Custom property
                img.toObject = (function(toObject) {
                    return function() {
                        return fabric.util.object.extend(toObject.call(this), {
                            custom: { kind: 'image' }
                        });
                    };
                })(img.toObject);
                img.custom = { kind: 'image' };

                this.canvas.add(img);
                this.canvas.setActiveObject(img);
                this.canvas.requestRenderAll();
                
                // Reset input value so same file can be selected again
                this.fileInput.value = '';
            });
        };
        reader.readAsDataURL(file);
    }
}
