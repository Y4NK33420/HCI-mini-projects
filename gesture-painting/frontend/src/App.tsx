import { useState, useEffect, useRef } from 'react';
import './App.css';

interface GestureData {
  mode: string;
  color: string;
  brush_size: number;
  eraser_size: number;
  action: any;
  position: { x: number; y: number } | null;
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

  // Initialize canvas
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
      }
    }
  }, []);

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
            
          } else if (action.type === 'color_change') {
            // Update current color
            setCurrentColor(action.color);
            
          } else if (action.type === 'size_change') {
            // Update both brush and eraser sizes
            if (action.brush_size !== undefined) setBrushSize(action.brush_size);
            if (action.eraser_size !== undefined) setEraserSize(action.eraser_size);
          }
        }
        
        // Reset last position if not drawing
        if (!data.gesture_data.action || data.gesture_data.action.type !== 'draw') {
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
    if (gestureData.mode === 'drawing') return 'bg-green-500';
    if (gestureData.mode === 'erasing') return 'bg-red-500';
    return 'bg-gray-500';
  };

  const getModeText = () => {
    if (!gestureData) return 'IDLE';
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
                  <span>Peace (1s) → Color</span>
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

