/**
 * Advanced Mindmap Visualization - NotebookLM Style
 * Interactive, animated mindmap with smooth transitions
 */

class MindmapVisualization {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            console.error(`Mindmap container #${containerId} not found in DOM`);
            throw new Error(`Container element #${containerId} not found`);
        }
        this.svg = null;
        this.nodes = new Map();
        this.connections = new Map();
        this.zoomLevel = 1;
        this.panX = 0;
        this.panY = 0;
        this.isDragging = false;
        this.dragStartX = 0;
        this.dragStartY = 0;
        
        this.colors = {
            central: '#1e40af',
            main: '#3b82f6',
            subtopic: '#10b981',
            detail: '#f59e0b'
        };
        
        this.init();
    }
    
    init() {
        this.createSVG();
        this.setupEventListeners();
    }
    
    createSVG() {
        // Clear existing content
        this.container.innerHTML = '';
        
        // Create main SVG
        this.svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        this.svg.setAttribute('width', '100%');
        this.svg.setAttribute('height', '100%');
        this.svg.setAttribute('viewBox', '0 0 1000 600');
        this.svg.style.cursor = 'grab';
        
        // Create definitions for filters
        const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
        
        // Create drop shadow filter
        const filter = document.createElementNS('http://www.w3.org/2000/svg', 'filter');
        filter.setAttribute('id', 'dropShadow');
        filter.setAttribute('x', '-50%');
        filter.setAttribute('y', '-50%');
        filter.setAttribute('width', '200%');
        filter.setAttribute('height', '200%');
        
        const blur = document.createElementNS('http://www.w3.org/2000/svg', 'feGaussianBlur');
        blur.setAttribute('in', 'SourceAlpha');
        blur.setAttribute('stdDeviation', '3');
        
        const offset = document.createElementNS('http://www.w3.org/2000/svg', 'feOffset');
        offset.setAttribute('dx', '2');
        offset.setAttribute('dy', '2');
        
        const merge = document.createElementNS('http://www.w3.org/2000/svg', 'feMerge');
        const mergeNode1 = document.createElementNS('http://www.w3.org/2000/svg', 'feMergeNode');
        const mergeNode2 = document.createElementNS('http://www.w3.org/2000/svg', 'feMergeNode');
        mergeNode2.setAttribute('in', 'SourceGraphic');
        
        merge.appendChild(mergeNode1);
        merge.appendChild(mergeNode2);
        filter.appendChild(blur);
        filter.appendChild(offset);
        filter.appendChild(merge);
        defs.appendChild(filter);
        
        // Create main group for transformations
        this.mainGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        
        this.svg.appendChild(defs);
        this.svg.appendChild(this.mainGroup);
        this.container.appendChild(this.svg);
    }
    
    setupEventListeners() {
        // Mouse wheel zoom
        this.container.addEventListener('wheel', (e) => {
            e.preventDefault();
            const delta = e.deltaY > 0 ? 0.9 : 1.1;
            this.zoom(delta);
        });
        
        // Mouse drag for panning
        this.svg.addEventListener('mousedown', (e) => {
            this.isDragging = true;
            this.dragStartX = e.clientX - this.panX;
            this.dragStartY = e.clientY - this.panY;
            this.svg.style.cursor = 'grabbing';
        });
        
        document.addEventListener('mousemove', (e) => {
            if (this.isDragging) {
                this.panX = e.clientX - this.dragStartX;
                this.panY = e.clientY - this.dragStartY;
                this.updateTransform();
            }
        });
        
        document.addEventListener('mouseup', () => {
            this.isDragging = false;
            this.svg.style.cursor = 'grab';
        });
    }
    
    renderMindmap(mindmapData) {
        try {
            this.clear();
            
            // Validate input data
            if (!mindmapData) {
                console.error('No mindmap data provided');
                throw new Error('Invalid mindmap data');
            }
            
            // Ensure central_topic exists
            if (!mindmapData.central_topic) {
                mindmapData.central_topic = { text: 'Main Topic', color: '#1e40af' };
            }
            
            // Ensure branches exist and is an array
            if (!mindmapData.branches || !Array.isArray(mindmapData.branches)) {
                mindmapData.branches = [];
            }
            
            // Filter out invalid branches
            mindmapData.branches = mindmapData.branches.filter(branch => branch && typeof branch === 'object');
            
            const centerX = 500;
            const centerY = 300;
            
            // Create central node
            this.createNode(centerX, centerY, mindmapData.central_topic.text || 'Main Topic', this.colors.central, true, 'central', 0);
            
            // Create branches
            if (mindmapData.branches.length === 0) {
                console.warn('No branches in mindmap data');
                // Create a placeholder branch
                mindmapData.branches = [{ id: 'placeholder', text: 'No content available', children: [] }];
            }
            
            mindmapData.branches.forEach((branch, index) => {
                const angle = (Math.PI * 2 / mindmapData.branches.length) * index;
                const radius = 200;
                const branchX = centerX + Math.cos(angle) * radius;
                const branchY = centerY + Math.sin(angle) * radius;
                
                // Create connection
                this.createConnection(centerX, centerY, branchX, branchY, this.colors.central);
                
                // Create branch node with safe text
                const branchText = branch.text || branch.topic || 'Untitled';
                this.createNode(branchX, branchY, branchText, this.colors.main, false, branch.id || `branch_${index}`, 1);
                
                // Create children if they exist
                if (branch.children && Array.isArray(branch.children) && branch.children.length > 0) {
                    this.createChildren(branch, branchX, branchY, angle, this.colors.main);
                }
            });
            
            // Animate entrance
            this.animateEntrance();
            
        } catch (error) {
            console.error('Error in renderMindmap:', error);
            throw error;
        }
    }
    
    createChildren(parent, parentX, parentY, parentAngle, parentColor) {
        const children = parent.children || [];
        const childAngleStep = Math.PI / 6;
        const radius = 120;
        
        children.forEach((child, index) => {
            const childAngle = parentAngle - Math.PI/4 + (childAngleStep * index);
            const childX = parentX + Math.cos(childAngle) * radius;
            const childY = parentY + Math.sin(childAngle) * radius;
            
            // Create connection
            this.createConnection(parentX, parentY, childX, childY, parentColor);
            
            // Determine color based on depth
            const childColor = child.children && child.children.length > 0 ? this.colors.subtopic : this.colors.detail;
            
            // Create child node
            this.createNode(childX, childY, child.text, childColor, false, child.id, 2);
            
            // Create grandchildren
            if (child.children && child.children.length > 0) {
                this.createGrandchildren(child, childX, childY, childAngle, childColor);
            }
        });
    }
    
    createGrandchildren(parent, parentX, parentY, parentAngle, parentColor) {
        const grandchildren = parent.children || [];
        const grandchildAngleStep = Math.PI / 4;
        const radius = 80;
        
        grandchildren.forEach((grandchild, index) => {
            const grandchildAngle = parentAngle - Math.PI/6 + (grandchildAngleStep * index);
            const grandchildX = parentX + Math.cos(grandchildAngle) * radius;
            const grandchildY = parentY + Math.sin(grandchildAngle) * radius;
            
            // Create connection
            this.createConnection(parentX, parentY, grandchildX, grandchildY, parentColor);
            
            // Create grandchild node
            this.createNode(grandchildX, grandchildY, grandchild.text, this.colors.detail, false, grandchild.id, 3);
        });
    }
    
    createNode(x, y, text, color, isCentral, id, depth = 0) {
        const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        group.setAttribute('transform', `translate(${x}, ${y})`);
        group.setAttribute('data-id', id || 'node-' + Math.random());
        group.setAttribute('data-depth', depth);
        group.style.cursor = 'pointer';
        
        // Determine node size based on depth and text length
        const textLength = text.length;
        let width, height, fontSize, fontWeight, maxWidth;
        
        if (isCentral) {
            width = Math.min(200, Math.max(120, textLength * 8));
            height = 50;
            fontSize = 16;
            fontWeight = '700';
            maxWidth = 25;
            group.classList.add('central-node');
        } else if (depth === 1) {
            width = Math.min(160, Math.max(100, textLength * 7));
            height = 40;
            fontSize = 14;
            fontWeight = '600';
            maxWidth = 20;
            group.classList.add('branch-node');
        } else if (depth === 2) {
            width = Math.min(140, Math.max(80, textLength * 6));
            height = 35;
            fontSize = 12;
            fontWeight = '500';
            maxWidth = 18;
            group.classList.add('child-node');
        } else {
            width = Math.min(120, Math.max(70, textLength * 5));
            height = 30;
            fontSize = 11;
            fontWeight = '400';
            maxWidth = 15;
            group.classList.add('grandchild-node');
        }
        
        // Create rectangle with rounded corners
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        rect.setAttribute('x', -width/2);
        rect.setAttribute('y', -height/2);
        rect.setAttribute('width', width);
        rect.setAttribute('height', height);
        rect.setAttribute('rx', depth === 0 ? 12 : depth === 1 ? 10 : depth === 2 ? 8 : 6);
        rect.setAttribute('fill', color);
        rect.setAttribute('stroke', '#ffffff');
        rect.setAttribute('stroke-width', '2');
        rect.setAttribute('opacity', '0');
        rect.setAttribute('filter', 'url(#dropShadow)');
        
        // Create text with better wrapping
        const textElement = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        textElement.setAttribute('x', 0);
        textElement.setAttribute('y', 0);
        textElement.setAttribute('text-anchor', 'middle');
        textElement.setAttribute('dominant-baseline', 'middle');
        textElement.setAttribute('fill', 'white');
        textElement.setAttribute('font-size', fontSize);
        textElement.setAttribute('font-weight', fontWeight);
        textElement.setAttribute('opacity', '0');
        
        // Handle text wrapping for longer text
        const words = text.split(' ');
        const lines = [];
        let currentLine = '';
        
        words.forEach(word => {
            const testLine = currentLine ? currentLine + ' ' + word : word;
            if (testLine.length <= maxWidth) {
                currentLine = testLine;
            } else {
                if (currentLine) {
                    lines.push(currentLine);
                    currentLine = word;
                } else {
                    lines.push(word);
                }
            }
        });
        
        if (currentLine) {
            lines.push(currentLine);
        }
        
        // Create text spans for each line
        const lineHeight = parseInt(fontSize) * 1.2;
        const startY = -(lines.length - 1) * lineHeight / 2;
        
        lines.forEach((line, index) => {
            const tspan = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
            tspan.setAttribute('x', 0);
            tspan.setAttribute('y', startY + (index * lineHeight));
            tspan.textContent = line;
            textElement.appendChild(tspan);
        });
        
        // Add hover effects
        group.addEventListener('mouseenter', () => {
            rect.setAttribute('opacity', '0.9');
            rect.setAttribute('transform', 'scale(1.08)');
            textElement.setAttribute('opacity', '1');
        });
        
        group.addEventListener('mouseleave', () => {
            rect.setAttribute('opacity', '0.8');
            rect.setAttribute('transform', 'scale(1)');
            textElement.setAttribute('opacity', '0.9');
        });
        
        // Add click event
        group.addEventListener('click', () => {
            this.centerOnNode(group);
        });
        
        group.appendChild(rect);
        group.appendChild(textElement);
        this.mainGroup.appendChild(group);
        
        // Store node reference
        this.nodes.set(id || 'node-' + Math.random(), group);
        
        return group;
    }
    
    createConnection(x1, y1, x2, y2, color) {
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', x1);
        line.setAttribute('y1', y1);
        line.setAttribute('x2', x2);
        line.setAttribute('y2', y2);
        line.setAttribute('stroke', color);
        line.setAttribute('stroke-width', '2');
        line.setAttribute('opacity', '0');
        
        this.mainGroup.insertBefore(line, this.mainGroup.firstChild);
        this.connections.set('connection-' + Math.random(), line);
    }
    
    animateEntrance() {
        // Animate connections first
        this.connections.forEach(line => {
            line.style.transition = 'opacity 0.5s ease-in-out';
            setTimeout(() => {
                line.setAttribute('opacity', '0.6');
            }, 100);
        });
        
        // Then animate nodes
        this.nodes.forEach((node, index) => {
            if (!node.element) {
                console.warn('Node element is undefined, skipping animation for node', index);
                return;
            }
            const rect = node.element.querySelector('rect');
            const text = node.element.querySelector('text');
            
            if (!rect || !text) {
                console.warn('Rect or text element not found for node', index);
                return;
            }
            
            rect.style.transition = 'opacity 0.5s ease-in-out, transform 0.3s ease-in-out';
            text.style.transition = 'opacity 0.5s ease-in-out';
            
            setTimeout(() => {
                rect.setAttribute('opacity', '0.8');
                text.setAttribute('opacity', '1');
            }, 200 + (index * 50));
        });
    }
    
    zoom(factor) {
        this.zoomLevel *= factor;
        this.zoomLevel = Math.max(0.3, Math.min(3, this.zoomLevel));
        this.updateTransform();
    }
    
    updateTransform() {
        this.mainGroup.setAttribute('transform', 
            `translate(${this.panX}, ${this.panY}) scale(${this.zoomLevel})`
        );
    }
    
    reset() {
        this.zoomLevel = 1;
        this.panX = 0;
        this.panY = 0;
        this.updateTransform();
    }
    
    clear() {
        this.nodes.clear();
        this.connections.clear();
        this.mainGroup.innerHTML = '';
    }
    
    exportAsJSON() {
        const data = {
            nodes: Array.from(this.nodes.entries()).map(([id, node]) => ({
                id,
                x: node.x,
                y: node.y,
                text: node.text,
                color: node.color
            })),
            connections: Array.from(this.connections.entries()).map(([id, line]) => ({
                id,
                x1: parseFloat(line.getAttribute('x1')),
                y1: parseFloat(line.getAttribute('y1')),
                x2: parseFloat(line.getAttribute('x2')),
                y2: parseFloat(line.getAttribute('y2')),
                color: line.getAttribute('stroke')
            }))
        };
        
        return JSON.stringify(data, null, 2);
    }
}

// Export for use in templates
window.MindmapVisualization = MindmapVisualization;
