import { useState, useEffect, useRef } from 'react';
import './App.css';

interface GestureData {
  mode: string;
  color: string;
  brush_size: number;
  eraser_size: number;
  action: any;
  position: { x: number; y: number } | null;
  shape_mode_active: boolean;
  shape_cycling: boolean;
  current_shape: string | null;
  selected_shape: string | null;
  shape_preview_active: boolean;
}

interface WebSocketMessage {
  frame: string;
  gesture_data: GestureData;
}

function App() {
  const [connected, setConnected] = useState(false);
  const [currentFrame, setCurrentFrame] = useState<string>('');
  const [gestureData, setGestureData] = useState<GestureData | null>(null);
  const [currentColor, setCurrentColor] = useState('#00FF00');
  const [brushSize, setBrushSize] = useState(5);
  const [eraserSize, setEraserSize] = useState(15);
  const [cursorPosition, setCursorPosition] = useState<{ x: number; y: number } | null>(null);
  
  const wsRef = useRef<WebSocket | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const ctxRef = useRef<CanvasRenderingContext2D | null>(null);
  const lastPosRef = useRef<{ x: number; y: number } | null>(null);
  
  // Undo/Redo history
  const historyRef = useRef<string[]>([]);
  const historyIndexRef = useRef<number>(-1);
  const maxHistorySize = 50;
  
  // Shape preview state
  const previewCanvasRef = useRef<HTMLCanvasElement>(null);
  const previewCtxRef = useRef<CanvasRenderingContext2D | null>(null);

  // Initialize canvases
  useEffect(() => {
    if (canvasRef.current) {
      const canvas = canvasRef.current;
      const ctx = canvas.getContext('2d');
      if (ctx) {
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
        ctxRef.current = ctx;
        
        // Fill with white background
        ctx.fillStyle = '#FFFFFF';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        
        // Save initial state
        saveToHistory();
      }
    }
    
    // Initialize preview canvas
    if (previewCanvasRef.current) {
      const previewCtx = previewCanvasRef.current.getContext('2d');
      if (previewCtx) {
        previewCtx.lineCap = 'round';
        previewCtx.lineJoin = 'round';
        previewCtxRef.current = previewCtx;
      }
    }
  }, []);
  
  // Save canvas state to history
  const saveToHistory = () => {
    if (!canvasRef.current) return;
    
    const dataUrl = canvasRef.current.toDataURL();
    
    // Remove any states after current index (for redo)
    historyRef.current = historyRef.current.slice(0, historyIndexRef.current + 1);
    
    // Add new state
    historyRef.current.push(dataUrl);
    
    // Limit history size
    if (historyRef.current.length > maxHistorySize) {
      historyRef.current.shift();
    } else {
      historyIndexRef.current++;
    }
  };
  
  // Restore canvas from history
  const restoreFromHistory = (index: number) => {
    if (!canvasRef.current || !ctxRef.current) return;
    if (index < 0 || index >= historyRef.current.length) return;
    
    const img = new Image();
    img.onload = () => {
      if (ctxRef.current && canvasRef.current) {
        ctxRef.current.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
        ctxRef.current.drawImage(img, 0, 0);
      }
    };
    img.src = historyRef.current[index];
    historyIndexRef.current = index;
  };
  
  // Undo action
  const undo = () => {
    if (historyIndexRef.current > 0) {
      restoreFromHistory(historyIndexRef.current - 1);
    }
  };
  
  // Redo action
  const redo = () => {
    if (historyIndexRef.current < historyRef.current.length - 1) {
      restoreFromHistory(historyIndexRef.current + 1);
    }
  };
  
  // Draw shape helper (works on any canvas)
  const drawShape = (
    ctx: CanvasRenderingContext2D,
    canvas: HTMLCanvasElement,
    shape: string,
    start: {x: number, y: number},
    end: {x: number, y: number},
    color: string,
    size: number,
    preview: boolean = false
  ) => {
    const startX = start.x * canvas.width;
    const startY = start.y * canvas.height;
    const endX = end.x * canvas.width;
    const endY = end.y * canvas.height;
    
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = size;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    
    // Add semi-transparent fill for preview only
    if (preview) {
      ctx.fillStyle = color + '30';
    }
    
    ctx.beginPath();
    
    if (shape === 'circle') {
      const radius = Math.sqrt(Math.pow(endX - startX, 2) + Math.pow(endY - startY, 2));
      ctx.arc(startX, startY, radius, 0, 2 * Math.PI);
      if (preview) ctx.fill();
      ctx.stroke();
    } else if (shape === 'rectangle') {
      const width = endX - startX;
      const height = endY - startY;
      ctx.rect(startX, startY, width, height);
      if (preview) ctx.fill();
      ctx.stroke();
    } else if (shape === 'triangle') {
      const midX = startX + (endX - startX) / 2;
      ctx.moveTo(midX, startY);
      ctx.lineTo(endX, endY);
      ctx.lineTo(startX, endY);
      ctx.closePath();
      if (preview) ctx.fill();
      ctx.stroke();
    } else if (shape === 'line') {
      ctx.moveTo(startX, startY);
      ctx.lineTo(endX, endY);
      ctx.stroke();
    }
    
    ctx.restore();
  };

  // Connect to WebSocket
  useEffect(() => {
    const connectWebSocket = () => {
      const ws = new WebSocket('ws://localhost:8001/ws/painting');
      
      ws.onopen = () => {
        console.log('🎨 Connected to painting server');
        setConnected(true);
      };
      
      ws.onmessage = (event) => {
        const data: WebSocketMessage = JSON.parse(event.data);
        setCurrentFrame(`data:image/jpeg;base64,${data.frame}`);
        setGestureData(data.gesture_data);
        
        // Update cursor position for visual tracking
        if (data.gesture_data.position) {
          setCursorPosition(data.gesture_data.position);
        } else {
          setCursorPosition(null);
        }
        
        // Handle painting actions
        if (data.gesture_data.action && canvasRef.current && ctxRef.current) {
          const action = data.gesture_data.action;
          const canvas = canvasRef.current;
          const ctx = ctxRef.current;
          
          if (action.type === 'draw' && action.position) {
            // Draw on canvas
            const x = action.position.x * canvas.width;
            const y = action.position.y * canvas.height;
            
            ctx.strokeStyle = action.color;
            ctx.lineWidth = action.size;
            
            if (lastPosRef.current) {
              ctx.beginPath();
              ctx.moveTo(lastPosRef.current.x, lastPosRef.current.y);
              ctx.lineTo(x, y);
              ctx.stroke();
            }
            
            lastPosRef.current = { x, y };
            
          } else if (action.type === 'erase' && action.position) {
            // Erase from canvas
            const x = action.position.x * canvas.width;
            const y = action.position.y * canvas.height;
            
            ctx.clearRect(x - action.size, y - action.size, action.size * 2, action.size * 2);
            
          } else if (action.type === 'clear') {
            // Clear entire canvas
            ctx.fillStyle = '#FFFFFF';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            lastPosRef.current = null;
            saveToHistory();
            
          } else if (action.type === 'color_change') {
            // Update current color
            setCurrentColor(action.color);
            
          } else if (action.type === 'size_change') {
            // Update both brush and eraser sizes
            if (action.brush_size !== undefined) setBrushSize(action.brush_size);
            if (action.eraser_size !== undefined) setEraserSize(action.eraser_size);
            
          } else if (action.type === 'undo') {
            // Undo last action
            undo();
            
          } else if (action.type === 'redo') {
            // Redo last undone action
            redo();
            
          } else if (action.type === 'shape_mode_enter') {
            // Entered shape mode
            console.log('🔷 Shape mode activated');
            
          } else if (action.type === 'shape_mode_exit') {
            // Exited shape mode
            console.log('🔷 Shape mode exited');
            // Clear preview canvas
            if (previewCanvasRef.current && previewCtxRef.current) {
              previewCtxRef.current.clearRect(0, 0, previewCanvasRef.current.width, previewCanvasRef.current.height);
            }
            
          } else if (action.type === 'shape_selected') {
            // Shape selected
            console.log('🔷 Shape selected:', action.shape);
            // Clear preview canvas
            if (previewCanvasRef.current && previewCtxRef.current) {
              previewCtxRef.current.clearRect(0, 0, previewCanvasRef.current.width, previewCanvasRef.current.height);
            }
            
          } else if (action.type === 'shape_cancelled') {
            // Shape cancelled
            console.log('🔷 Shape cancelled');
            // Clear preview canvas
            if (previewCanvasRef.current && previewCtxRef.current) {
              previewCtxRef.current.clearRect(0, 0, previewCanvasRef.current.width, previewCanvasRef.current.height);
            }
            
          } else if (action.type === 'shape_start') {
            // Shape drawing started
            console.log('🔷 Shape start at:', action.position);
            
          } else if (action.type === 'shape_preview') {
            // Preview shape in real-time
            if (previewCanvasRef.current && previewCtxRef.current) {
              // Clear preview canvas
              previewCtxRef.current.clearRect(0, 0, previewCanvasRef.current.width, previewCanvasRef.current.height);
              // Draw shape preview
              drawShape(previewCtxRef.current, previewCanvasRef.current, action.shape, action.start, action.end, action.color, action.size, true);
            }
            
          } else if (action.type === 'shape_finalize') {
            // Finalize shape - draw on main canvas
            if (ctxRef.current && canvasRef.current) {
              drawShape(ctxRef.current, canvasRef.current, action.shape, action.start, action.end, action.color, action.size, false);
              saveToHistory();
            }
            // Clear preview canvas
            if (previewCanvasRef.current && previewCtxRef.current) {
              previewCtxRef.current.clearRect(0, 0, previewCanvasRef.current.width, previewCanvasRef.current.height);
            }
            console.log('🔷 Shape finalized:', action.shape);
          }
        }
        
        // Reset last position and save to history when action completes
        if (!data.gesture_data.action || (data.gesture_data.action.type !== 'draw' && data.gesture_data.action.type !== 'erase')) {
          if (lastPosRef.current !== null) {
            // User just finished drawing/erasing, save to history
            saveToHistory();
          }
          lastPosRef.current = null;
        }
      };
      
      ws.onerror = (error) => {
        console.error('❌ WebSocket error:', error);
      };
      
      ws.onclose = () => {
        console.log('🎨 Disconnected from painting server');
        setConnected(false);
        setTimeout(connectWebSocket, 2000);
      };
      
      wsRef.current = ws;
    };
    
    connectWebSocket();
    
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const clearCanvas = () => {
    if (canvasRef.current && ctxRef.current) {
      const ctx = ctxRef.current;
      ctx.fillStyle = '#FFFFFF';
      ctx.fillRect(0, 0, canvasRef.current.width, canvasRef.current.height);
    }
  };

  const downloadArt = () => {
    if (canvasRef.current) {
      const link = document.createElement('a');
      link.download = `gesture-art-${Date.now()}.png`;
      link.href = canvasRef.current.toDataURL();
      link.click();
    }
  };

  const getModeColor = () => {
    if (!gestureData) return 'bg-gray-500';
    if (gestureData.shape_mode_active) return 'bg-orange-500';
    if (gestureData.mode === 'drawing') return 'bg-green-500';
    if (gestureData.mode === 'erasing') return 'bg-red-500';
    return 'bg-gray-500';
  };

  const getModeText = () => {
    if (!gestureData) return 'IDLE';
    if (gestureData.shape_mode_active) return '🔷 SHAPE MODE';
    return gestureData.mode.toUpperCase();
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-900 via-pink-900 to-orange-900 text-white">
      {/* Header */}
      <header className="bg-white/10 backdrop-blur-md border-b border-white/20 p-4">
        <div className="flex items-center justify-between max-w-screen-2xl mx-auto">
          <div>
            <h1 className="text-3xl font-bold bg-gradient-to-r from-pink-400 to-orange-400 bg-clip-text text-transparent">
              🎨 Gesture Painting
            </h1>
            <p className="text-sm text-gray-300 mt-1">Paint with your hands in the air!</p>
          </div>
          
          <div className="flex items-center gap-4">
            {/* Connection */}
            <div className="flex items-center gap-2">
              <div className={`w-3 h-3 rounded-full ${connected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
              <span className="text-sm">{connected ? 'Connected' : 'Disconnected'}</span>
            </div>
            
            {/* Mode */}
            <div className={`${getModeColor()} px-6 py-2 rounded-full font-bold`}>
              {getModeText()}
            </div>
            
            {/* Color indicator */}
            <div className="flex items-center gap-2">
              <span className="text-sm">Color:</span>
              <div 
                className="w-10 h-10 rounded-lg border-2 border-white shadow-lg"
                style={{ backgroundColor: currentColor }}
              />
            </div>
            
            {/* Brush and eraser sizes */}
            <div className="bg-white/20 px-4 py-2 rounded-lg">
              <span className="text-sm">Brush: {brushSize}px | Eraser: {eraserSize}px</span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 p-4 h-[calc(100vh-100px)]">
        {/* Left Panel - Camera */}
        <div className="lg:col-span-1 space-y-4">
          <div className="bg-white/10 backdrop-blur-md border border-white/20 rounded-xl p-4 h-full flex flex-col">
            <h2 className="text-xl font-bold mb-3">📹 Camera</h2>
            
            {/* Camera feed */}
            <div className="flex-1 bg-black rounded-lg overflow-hidden mb-4">
              {currentFrame ? (
                <img 
                  src={currentFrame} 
                  alt="Camera" 
                  className="w-full h-full object-contain"
                />
              ) : (
                <div className="flex items-center justify-center h-full">
                  <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-pink-500 mx-auto mb-3"></div>
                    <p className="text-sm text-gray-400">Connecting...</p>
                  </div>
                </div>
              )}
            </div>

            {/* Instructions */}
            <div className="bg-gradient-to-br from-purple-500/20 to-pink-500/20 border border-purple-500/30 rounded-lg p-3">
              <h3 className="font-bold mb-2 text-sm">✋ Gestures:</h3>
              <div className="space-y-1 text-xs">
                <div className="flex items-center gap-2">
                  <span className="text-lg">☝️</span>
                  <span>Index → Draw</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-lg">✊</span>
                  <span>Fist → Erase</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-lg">✌️</span>
                  <span className="font-bold text-cyan-300">Peace (2s) → Color</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-lg">👍</span>
                  <span className="font-bold text-orange-300">Thumbs Up (2s) → Shapes</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-lg">✋</span>
                  <span>Palm Swipe L/R → Undo/Redo</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-lg">✋✋</span>
                  <span>Two Hands (2s) → Clear</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-lg">🤏</span>
                  <span>Pinch → Size</span>
                </div>
              </div>
            </div>
            
            {/* Shape Mode Indicator */}
            {gestureData?.shape_mode_active && (
              <div className="bg-gradient-to-br from-orange-500/30 to-yellow-500/30 border-2 border-orange-500/50 rounded-lg p-4 mt-3">
                <h3 className="font-bold text-orange-300 mb-3 text-center text-base">🔷 SHAPE MODE ACTIVE</h3>
                {gestureData.selected_shape ? (
                  <div className="text-center">
                    <div className="bg-green-500/20 border border-green-500 rounded-lg p-3 mb-2">
                      <p className="text-green-300 font-bold text-xl mb-2">
                        ✓ SELECTED: {gestureData.selected_shape.toUpperCase()}
                      </p>
                      {/* Large shape icon */}
                      <div className="flex justify-center my-3">
                        {gestureData.selected_shape === 'circle' && (
                          <div className="w-16 h-16 border-4 border-green-400 rounded-full"></div>
                        )}
                        {gestureData.selected_shape === 'rectangle' && (
                          <div className="w-16 h-16 border-4 border-green-400"></div>
                        )}
                        {gestureData.selected_shape === 'triangle' && (
                          <div className="w-0 h-0 border-l-[32px] border-l-transparent border-r-[32px] border-r-transparent border-b-[56px] border-b-green-400"></div>
                        )}
                        {gestureData.selected_shape === 'line' && (
                          <div className="w-16 h-0.5 bg-green-400 self-center" style={{transform: 'rotate(45deg)'}}></div>
                        )}
                      </div>
                    </div>
                    {gestureData.shape_preview_active ? (
                      <div className="bg-yellow-500/20 border border-yellow-500 rounded p-2">
                        <p className="text-xs text-yellow-300 font-bold mb-1">📐 DRAWING SHAPE...</p>
                        <p className="text-xs text-gray-300">✊ Fist: Finalize</p>
                        <p className="text-xs text-gray-300">✋ Palm: Cancel</p>
                      </div>
                    ) : (
                      <>
                        <p className="text-xs text-gray-300">☝️ Index: Start Drawing</p>
                        <p className="text-xs text-gray-300">✋ Palm: Change Shape</p>
                      </>
                    )}
                    <p className="text-xs text-gray-400 mt-2">👍 Thumbs Up (2s): Exit</p>
                  </div>
                ) : gestureData.current_shape ? (
                  <div className="text-center">
                    <p className="text-white font-bold text-sm mb-3">SELECT A SHAPE:</p>
                    <p className="text-yellow-300 text-xs mb-2">⏱️ Shapes change every 4 seconds</p>
                    
                    {/* Shape selector with all shapes */}
                    <div className="grid grid-cols-2 gap-2 mb-3">
                      {['circle', 'rectangle', 'triangle', 'line'].map((shape) => {
                        const isActive = shape === gestureData.current_shape;
                        return (
                          <div
                            key={shape}
                            className={`flex flex-col items-center justify-center p-3 rounded-lg border-2 transition-all ${
                              isActive 
                                ? 'border-cyan-400 bg-cyan-500/30 scale-110 shadow-lg shadow-cyan-500/50' 
                                : 'border-gray-600 bg-gray-700/20'
                            }`}
                          >
                            {/* Shape icon */}
                            <div className="mb-1">
                              {shape === 'circle' && (
                                <div className={`w-10 h-10 border-3 rounded-full ${isActive ? 'border-cyan-400' : 'border-gray-500'}`}></div>
                              )}
                              {shape === 'rectangle' && (
                                <div className={`w-10 h-10 border-3 ${isActive ? 'border-cyan-400' : 'border-gray-500'}`}></div>
                              )}
                              {shape === 'triangle' && (
                                <div 
                                  className="w-0 h-0 border-l-[20px] border-l-transparent border-r-[20px] border-r-transparent border-b-[35px]"
                                  style={{borderBottomColor: isActive ? '#22d3ee' : '#6b7280'}}
                                ></div>
                              )}
                              {shape === 'line' && (
                                <div className={`w-10 h-0.5 self-center ${isActive ? 'bg-cyan-400' : 'bg-gray-500'}`} style={{transform: 'rotate(45deg)'}}></div>
                              )}
                            </div>
                            {/* Shape name */}
                            <p className={`text-xs font-bold ${isActive ? 'text-cyan-300' : 'text-gray-500'}`}>
                              {shape.toUpperCase()}
                            </p>
                            {/* Active indicator */}
                            {isActive && (
                              <div className="mt-1">
                                <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></div>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                    
                    <div className="bg-cyan-500/20 border border-cyan-500 rounded p-2 mb-2">
                      <p className="text-xs text-cyan-300 font-bold">✋ OPEN PALM TO SELECT CURRENT SHAPE</p>
                      <p className="text-xs text-gray-400 mt-1">Watch the progress bar on camera!</p>
                    </div>
                    <p className="text-xs text-gray-400">👍 Thumbs Up (2s): Exit</p>
                  </div>
                ) : null}
              </div>
            )}

            {/* Actions */}
            <div className="mt-4 space-y-2">
              <button
                onClick={clearCanvas}
                className="w-full bg-red-500 hover:bg-red-600 py-2 rounded-lg font-bold transition-colors"
              >
                🗑️ Clear Canvas
              </button>
              <button
                onClick={downloadArt}
                className="w-full bg-blue-500 hover:bg-blue-600 py-2 rounded-lg font-bold transition-colors"
              >
                💾 Download Art
              </button>
            </div>
          </div>
        </div>

        {/* Right Panel - Canvas */}
        <div className="lg:col-span-3">
          <div className="bg-white/10 backdrop-blur-md border border-white/20 rounded-xl p-6 h-full flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-2xl font-bold">🖼️ Your Artwork</h2>
              <div className="text-sm text-gray-300">
                Draw freely with your gestures!
              </div>
            </div>

            {/* Canvas */}
            <div className="flex-1 flex items-center justify-center bg-gray-900 rounded-lg p-4 relative">
              <canvas
                ref={canvasRef}
                width={1400}
                height={800}
                className="max-w-full max-h-full bg-white rounded shadow-2xl"
              />
              
              {/* Preview Canvas Overlay - for shape preview */}
              <canvas
                ref={previewCanvasRef}
                width={1400}
                height={800}
                className="max-w-full max-h-full absolute pointer-events-none"
                style={{
                  left: '50%',
                  top: '50%',
                  transform: 'translate(-50%, -50%)',
                }}
              />
              
              {/* Cursor Overlay - shows where user is pointing */}
              {cursorPosition && canvasRef.current && (
                <div
                  className="absolute pointer-events-none z-50"
                  style={{
                    left: `calc(50% - 700px + ${cursorPosition.x * 1400}px)`,
                    top: `calc(50% - 400px + ${cursorPosition.y * 800}px)`,
                  }}
                >
                  {gestureData?.mode === 'drawing' ? (
                    // Drawing cursor - shows brush color and size
                    <>
                      <div 
                        className="rounded-full border-2 border-white shadow-lg"
                        style={{
                          width: `${brushSize * 2}px`,
                          height: `${brushSize * 2}px`,
                          backgroundColor: currentColor,
                          transform: 'translate(-50%, -50%)',
                        }}
                      />
                      <div 
                        className="absolute rounded-full border-2 animate-ping opacity-50"
                        style={{
                          width: `${brushSize * 3}px`,
                          height: `${brushSize * 3}px`,
                          borderColor: currentColor,
                          transform: 'translate(-50%, -50%)',
                          left: 0,
                          top: 0,
                        }}
                      />
                    </>
                  ) : gestureData?.mode === 'erasing' ? (
                    // Eraser cursor - shows eraser size
                    <>
                      <div 
                        className="rounded-full border-4 border-red-500 bg-black/30 shadow-lg"
                        style={{
                          width: `${eraserSize * 2}px`,
                          height: `${eraserSize * 2}px`,
                          transform: 'translate(-50%, -50%)',
                        }}
                      />
                      <div className="absolute w-1 h-8 bg-red-500" style={{ left: '50%', top: '50%', transform: 'translate(-50%, -50%)' }} />
                      <div className="absolute w-8 h-1 bg-red-500" style={{ left: '50%', top: '50%', transform: 'translate(-50%, -50%)' }} />
                    </>
                  ) : (
                    // Idle cursor - simple crosshair
                    <div className="relative" style={{ transform: 'translate(-50%, -50%)' }}>
                      <div className="absolute w-0.5 h-8 bg-blue-400" style={{ left: '50%', top: '50%', transform: 'translate(-50%, -50%)' }} />
                      <div className="absolute w-8 h-0.5 bg-blue-400" style={{ left: '50%', top: '50%', transform: 'translate(-50%, -50%)' }} />
                      <div className="absolute w-3 h-3 border-2 border-blue-400 rounded-full" style={{ left: '50%', top: '50%', transform: 'translate(-50%, -50%)' }} />
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;

