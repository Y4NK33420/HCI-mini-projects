import { useState, useEffect, useRef } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import './App.css';

// Configure PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

// Types
interface GestureData {
  gesture: string;
  clutch_active: boolean;
  pointer_active: boolean;
  action: string | null;
  pointer_pos: { x: number; y: number } | null;
  time_left: number | null;
  num_hands: number;
}

interface WebSocketMessage {
  frame: string;
  gesture_data: GestureData;
}

function App() {
  const [connected, setConnected] = useState(false);
  const [currentFrame, setCurrentFrame] = useState<string>('');
  const [gestureData, setGestureData] = useState<GestureData | null>(null);
  const [currentSlide, setCurrentSlide] = useState(0);
  const [totalSlides, setTotalSlides] = useState(1);
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pointerPosition, setPointerPosition] = useState<{ x: number; y: number } | null>(null);
  
  const wsRef = useRef<WebSocket | null>(null);
  const videoRef = useRef<HTMLImageElement>(null);
  const slideRef = useRef<HTMLDivElement>(null);
  const totalSlidesRef = useRef<number>(1);

  // Connect to WebSocket
  useEffect(() => {
    const connectWebSocket = () => {
      const ws = new WebSocket('ws://localhost:8000/ws/video');
      
      ws.onopen = () => {
        console.log('📡 Connected to gesture server');
        setConnected(true);
      };
      
      ws.onmessage = (event) => {
        const data: WebSocketMessage = JSON.parse(event.data);
        setCurrentFrame(`data:image/jpeg;base64,${data.frame}`);
        setGestureData(data.gesture_data);
        
        // Update pointer position for slide overlay
        if (data.gesture_data.pointer_active && data.gesture_data.pointer_pos) {
          setPointerPosition(data.gesture_data.pointer_pos);
        } else {
          setPointerPosition(null);
        }
        
        // Handle actions
        if (data.gesture_data.action) {
          console.log('Action detected:', data.gesture_data.action);
          
          if (data.gesture_data.action === 'next') {
            setCurrentSlide(prev => {
              const newSlide = Math.min(prev + 1, totalSlidesRef.current - 1);
              console.log(`Next slide: ${prev + 1} -> ${newSlide + 1} (total: ${totalSlidesRef.current})`);
              return newSlide;
            });
          } else if (data.gesture_data.action === 'previous') {
            setCurrentSlide(prev => {
              const newSlide = Math.max(prev - 1, 0);
              console.log(`Previous slide: ${prev + 1} -> ${newSlide + 1} (total: ${totalSlidesRef.current})`);
              return newSlide;
            });
          } else if (data.gesture_data.action === 'exit') {
            console.log('🚪 Exit gesture detected');
          }
        }
      };
      
      ws.onerror = (error) => {
        console.error('❌ WebSocket error:', error);
      };
      
      ws.onclose = () => {
        console.log('📡 Disconnected from gesture server');
        setConnected(false);
        // Reconnect after 2 seconds
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
  }, [totalSlides]);

  const getStatusColor = () => {
    if (!gestureData) return 'bg-gray-500';
    if (gestureData.pointer_active) return 'bg-cyan-500';
    if (gestureData.clutch_active) return 'bg-green-500';
    return 'bg-red-500';
  };

  const getStatusText = () => {
    if (!gestureData) return 'DISCONNECTED';
    if (gestureData.pointer_active) return '🎯 POINTER MODE';
    if (gestureData.clutch_active) return '🟢 LISTENING';
    return '🔴 IDLE';
  };

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file && file.type === 'application/pdf') {
      setPdfFile(file);
      const url = URL.createObjectURL(file);
      setPdfUrl(url);
      setCurrentSlide(0);
    }
  };

  const onDocumentLoadSuccess = ({ numPages }: { numPages: number }) => {
    setTotalSlides(numPages);
    totalSlidesRef.current = numPages;
    console.log(`PDF loaded: ${numPages} pages`);
  };

  // Sync ref with state
  useEffect(() => {
    totalSlidesRef.current = totalSlides;
  }, [totalSlides]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-purple-900 to-gray-900 text-white">
      {/* Header */}
      <header className="bg-white/10 backdrop-blur-md border border-white/20 rounded-xl shadow-2xl m-4 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-4xl font-bold bg-gradient-to-r from-green-400 to-blue-500 bg-clip-text text-transparent">
              🎯 Aura Mode 2
            </h1>
            <p className="text-gray-300 mt-1">Gesture-Controlled Presentation System</p>
          </div>
          
          <div className="flex items-center gap-4">
            {/* Connection Status */}
            <div className="flex items-center gap-2">
              <div className={`w-3 h-3 rounded-full ${connected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
              <span className="text-sm">{connected ? 'Connected' : 'Disconnected'}</span>
            </div>
            
            {/* Current Status */}
            <div className={`${getStatusColor()} px-6 py-2 rounded-full font-bold text-center text-lg`}>
              {getStatusText()}
            </div>
            
            {/* Timer */}
            {gestureData?.clutch_active && !gestureData.pointer_active && (
              <div className="text-2xl font-mono bg-green-500/20 px-4 py-2 rounded-lg">
                {gestureData.time_left}s
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 p-4 h-[calc(100vh-150px)]">
        {/* Left Panel - Camera & Status (Smaller) */}
        <div className="lg:col-span-1 space-y-4 overflow-y-auto">
          {/* Video Feed */}
          <div className="bg-white/10 backdrop-blur-md border border-white/20 rounded-xl shadow-2xl p-4">
            <h2 className="text-lg font-bold mb-2">📹 Camera</h2>
            <div className="relative bg-black rounded-lg overflow-hidden aspect-video">
              {currentFrame ? (
                <img 
                  ref={videoRef}
                  src={currentFrame} 
                  alt="Video Feed" 
                  className="w-full h-full object-contain"
                />
              ) : (
                <div className="flex items-center justify-center h-full">
                  <div className="text-center">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-green-500 mx-auto mb-2"></div>
                    <p className="text-xs text-gray-400">Connecting...</p>
                  </div>
                </div>
              )}
            </div>
          </div>
          {/* Gesture Info */}
          <div className="bg-white/10 backdrop-blur-md border border-white/20 rounded-xl shadow-2xl p-6">
            <h2 className="text-xl font-bold mb-4">🤚 Current Gesture</h2>
            <div className="bg-gradient-to-br from-purple-500/20 to-pink-500/20 p-6 rounded-xl border border-purple-500/30">
              <p className="text-3xl font-bold text-center">
                {gestureData?.gesture || 'None'}
              </p>
            </div>
            
            <div className="mt-4 space-y-2 text-sm">
              <div className="flex justify-between">
                <span>Hands Detected:</span>
                <span className="font-bold">{gestureData?.num_hands || 0}</span>
              </div>
              <div className="flex justify-between">
                <span>Clutch:</span>
                <span className={`font-bold ${gestureData?.clutch_active ? 'text-green-400' : 'text-red-400'}`}>
                  {gestureData?.clutch_active ? 'Active' : 'Inactive'}
                </span>
              </div>
              <div className="flex justify-between">
                <span>Pointer:</span>
                <span className={`font-bold ${gestureData?.pointer_active ? 'text-cyan-400' : 'text-gray-400'}`}>
                  {gestureData?.pointer_active ? 'Active' : 'Inactive'}
                </span>
              </div>
            </div>
          </div>

          {/* Gesture Guide */}
          <div className="bg-white/10 backdrop-blur-md border border-white/20 rounded-xl shadow-2xl p-4">
            <h2 className="text-lg font-bold mb-3">📖 Gestures</h2>
            <div className="space-y-1 text-xs">
              <div className="flex items-center gap-2 p-2 bg-white/5 rounded">
                <span>👍</span>
                <span>Hold 2s → Activate</span>
              </div>
              <div className="flex items-center gap-2 p-2 bg-white/5 rounded">
                <span>👈</span>
                <span>LEFT → Next</span>
              </div>
              <div className="flex items-center gap-2 p-2 bg-white/5 rounded">
                <span>👉</span>
                <span>RIGHT → Prev</span>
              </div>
              <div className="flex items-center gap-2 p-2 bg-white/5 rounded">
                <span>✌️</span>
                <span>Hold 1s → Pointer</span>
              </div>
              <div className="flex items-center gap-2 p-2 bg-white/5 rounded">
                <span>✋✋</span>
                <span>Hold 2s → Exit</span>
              </div>
            </div>
          </div>
        </div>

        {/* Right Panel - Slide Display (Larger) */}
        <div className="lg:col-span-3 flex flex-col">
          <div className="bg-white/10 backdrop-blur-md border border-white/20 rounded-xl shadow-2xl p-6 h-full flex flex-col">
            {/* Header with controls */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-4">
                <h2 className="text-2xl font-bold">📄 Presentation</h2>
                
                {/* PDF Upload */}
                <label className="px-4 py-2 bg-blue-500 hover:bg-blue-600 rounded-lg cursor-pointer transition-colors text-sm font-bold">
                  <input 
                    type="file" 
                    accept=".pdf" 
                    onChange={handleFileUpload}
                    className="hidden"
                  />
                  📎 Upload PDF
                </label>
                
                {pdfFile && <span className="text-sm text-green-400">✓ {pdfFile.name}</span>}
              </div>
              
              {/* Slide Counter & Controls */}
              <div className="flex items-center gap-4">
                <div className="bg-gradient-to-r from-purple-500/20 to-pink-500/20 px-6 py-2 rounded-lg border border-purple-500/30">
                  <p className="text-2xl font-bold">
                    {currentSlide + 1} / {totalSlides}
                  </p>
                </div>
                
                <div className="flex gap-2">
                  <button 
                    onClick={() => setCurrentSlide(prev => Math.max(prev - 1, 0))}
                    disabled={currentSlide === 0}
                    className="bg-blue-500 hover:bg-blue-600 disabled:bg-gray-600 disabled:cursor-not-allowed px-4 py-2 rounded-lg font-bold transition-colors"
                  >
                    ⬅️
                  </button>
                  <button 
                    onClick={() => setCurrentSlide(prev => Math.min(prev + 1, totalSlides - 1))}
                    disabled={currentSlide === totalSlides - 1}
                    className="bg-blue-500 hover:bg-blue-600 disabled:bg-gray-600 disabled:cursor-not-allowed px-4 py-2 rounded-lg font-bold transition-colors"
                  >
                    ➡️
                  </button>
                </div>
              </div>
            </div>

            {/* Slide Display */}
            <div className="flex-1 bg-gray-800 rounded-lg overflow-auto flex items-center justify-center p-4 relative" ref={slideRef}>
              {pdfUrl ? (
                <div className="w-full h-full flex items-center justify-center relative">
                  <Document
                    file={pdfUrl}
                    onLoadSuccess={onDocumentLoadSuccess}
                    loading={
                      <div className="text-center">
                        <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-green-500 mx-auto mb-4"></div>
                        <p className="text-white">Loading PDF...</p>
                      </div>
                    }
                    error={
                      <div className="text-center text-red-400">
                        <p>Failed to load PDF</p>
                      </div>
                    }
                  >
                    <Page
                      pageNumber={currentSlide + 1}
                      renderTextLayer={false}
                      renderAnnotationLayer={false}
                      width={Math.min(window.innerWidth * 0.7, 1200)}
                      loading={
                        <div className="flex items-center justify-center h-96">
                          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-green-500"></div>
                        </div>
                      }
                    />
                  </Document>
                  
                  {/* Pointer Overlay on Slides */}
                  {pointerPosition && gestureData?.pointer_active && slideRef.current && (
                    <div
                      className="absolute w-8 h-8 pointer-events-none z-50"
                      style={{
                        left: `${pointerPosition.x * 100}%`,
                        top: `${pointerPosition.y * 100}%`,
                        transform: 'translate(-50%, -50%)',
                      }}
                    >
                      {/* Outer glow */}
                      <div className="absolute inset-0 bg-red-500 rounded-full opacity-30 animate-ping"></div>
                      {/* Middle ring */}
                      <div className="absolute inset-0 border-4 border-yellow-400 rounded-full"></div>
                      {/* Inner dot */}
                      <div className="absolute inset-2 bg-red-500 rounded-full shadow-lg"></div>
                      {/* Center dot */}
                      <div className="absolute inset-3 bg-white rounded-full"></div>
                      
                      {/* Laser beam effect */}
                      <div className="absolute w-1 h-screen bg-gradient-to-b from-red-500 to-transparent opacity-30" style={{ left: '50%', top: '100%', transform: 'translateX(-50%)' }}></div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-center">
                  <div className="mb-4">
                    <svg className="w-32 h-32 mx-auto text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                  <h3 className="text-2xl font-bold mb-2">No Presentation Loaded</h3>
                  <p className="text-gray-400 mb-4">Upload a PDF to get started</p>
                  <label className="inline-block px-6 py-3 bg-green-500 hover:bg-green-600 rounded-lg cursor-pointer transition-colors text-lg font-bold">
                    <input 
                      type="file" 
                      accept=".pdf" 
                      onChange={handleFileUpload}
                      className="hidden"
                    />
                    📎 Upload PDF Presentation
                  </label>
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

