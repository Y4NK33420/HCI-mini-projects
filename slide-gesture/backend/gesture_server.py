"""
Aura Mode 2 - FastAPI Backend with WebSocket Video Streaming
Integrates full Mode 1 gesture controller pipeline
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import cv2
import numpy as np
import asyncio
import json
import base64
import time
import sys
import os
from typing import Optional

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.hand_detector import HandDetector, GestureRecognizer

# Configuration (Mode 1 settings)
CLUTCH_THRESHOLD = 2.0
CLUTCH_DURATION = 15.0
ACTIVATION_ZONE_RATIO = 0.6
ZONE_SIZE = 0.30
ZONE_HOLD_TIME = 0.3
ZONE_DEBOUNCE = 1.5
EXIT_HOLD_TIME = 2.0
PEACE_HOLD_TIME = 1.0
POINTER_SMOOTHING = 7

app = FastAPI(title="Aura Gesture Server")

# CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GestureController:
    """Full Mode 1 gesture controller for Mode 2"""
    
    def __init__(self):
        self.detector = HandDetector(max_num_hands=2)
        self.recognizer = GestureRecognizer(self.detector)
        
        # State
        self.clutch_active = False
        self.clutch_start = 0
        self.clutch_time = 0
        
        # Pointer
        self.pointer_active = False
        self.pointer_start = 0
        self.peace_start = 0
        
        # Navigation
        self.left_zone_start = 0
        self.right_zone_start = 0
        self.last_swipe = 0
        
        # Exit
        self.exit_start = 0
    
    def process_frame(self, frame):
        """Process frame with full Mode 1 gesture detection"""
        t = time.time()
        
        # Detect hands
        frame = self.detector.find_hands(frame, flip=True)
        landmarks = self.detector.get_landmarks(frame)
        fingers = self.detector.get_fingers_up()
        
        # Recognize gesture
        gesture = self.recognizer.recognize_static_gesture(fingers)
        self.recognizer.add_to_history(gesture)
        stable = self.recognizer.get_stable_gesture()
        
        h, w, _ = frame.shape
        activation_y = int(h * ACTIVATION_ZONE_RATIO)
        in_zone = self.detector.is_above_threshold(activation_y) if landmarks else False
        
        action = None
        pointer_pos = None
        
        # Check clutch activation
        if in_zone or not landmarks or self.pointer_active:
            self._check_clutch(gesture, t)
            
            if self.clutch_active:
                # Exit check
                if self._check_exit(t):
                    action = "exit"
                
                # Pointer (full frame)
                pointer_action, pointer_pos = self._handle_pointer(gesture, t, frame)
                if pointer_action:
                    action = pointer_action
                
                # Navigation (only if pointer off)
                if not self.pointer_active:
                    nav_action = self._handle_navigation(gesture, t, frame)
                    if nav_action:
                        action = nav_action
        
        # Draw UI
        self._draw_ui(frame, stable, t)
        self.detector.draw_landmarks(frame)
        
        return frame, {
            "gesture": stable,
            "clutch_active": self.clutch_active,
            "pointer_active": self.pointer_active,
            "action": action,
            "pointer_pos": pointer_pos,
            "time_left": int(CLUTCH_DURATION - (t - self.clutch_time)) if self.clutch_active and not self.pointer_active else None,
            "num_hands": self.detector.get_num_hands()
        }
    
    def _check_clutch(self, gesture, t):
        """Clutch activation with 2s hold"""
        if gesture == GestureRecognizer.THUMBS_UP:
            if not self.clutch_active and self.clutch_start == 0:
                self.clutch_start = t
            elif not self.clutch_active and t - self.clutch_start >= CLUTCH_THRESHOLD:
                self.clutch_active = True
                self.clutch_time = t
                self.clutch_start = 0
        else:
            self.clutch_start = 0
        
        # Expiration (pauses in pointer mode)
        if self.clutch_active and not self.pointer_active:
            if t - self.clutch_time > CLUTCH_DURATION:
                self.clutch_active = False
    
    def _handle_pointer(self, gesture, t, frame):
        """Pointer with peace sign toggle (1s hold) - uses full frame"""
        h, w, _ = frame.shape
        
        # Peace sign hold to toggle
        if gesture == GestureRecognizer.PEACE_SIGN:
            if self.peace_start == 0:
                self.peace_start = t
            elif t - self.peace_start >= PEACE_HOLD_TIME:
                self.pointer_active = not self.pointer_active
                if self.pointer_active:
                    self.pointer_start = t
                    action = "pointer_on"
                else:
                    self.clutch_time += (t - self.pointer_start)
                    action = "pointer_off"
                self.peace_start = 0
                return action, None
            else:
                # Draw progress bar
                progress = (t - self.peace_start) / PEACE_HOLD_TIME
                bar_w = int(w * 0.3)
                bar_x = (w - bar_w) // 2
                bar_y = h - 150
                cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + 20), (50, 50, 50), -1)
                cv2.rectangle(frame, (bar_x, bar_y), (bar_x + int(bar_w * progress), bar_y + 20), (0, 255, 255), -1)
                text = "DEACTIVATING..." if self.pointer_active else "ACTIVATING..."
                cv2.putText(frame, text, (bar_x, bar_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        else:
            self.peace_start = 0
        
        # If pointer active, track index finger (FULL FRAME!)
        if self.pointer_active and gesture == GestureRecognizer.INDEX_POINT:
            tip = self.detector.get_finger_tip(1)
            if tip:
                # Draw pointer indicator
                cv2.circle(frame, tuple(tip), 20, (0, 255, 255), -1)
                cv2.circle(frame, tuple(tip), 25, (255, 255, 0), 3)
                cv2.circle(frame, tuple(tip), 30, (0, 255, 0), 2)
                
                # Show full frame is active
                activation_y = int(h * ACTIVATION_ZONE_RATIO)
                cv2.line(frame, (0, activation_y), (w, activation_y), (0, 255, 255), 3)
                cv2.putText(frame, "FULL FRAME ACTIVE", (w//2 - 100, activation_y - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                
                # Return normalized position (0-1 range)
                norm_x = tip[0] / w
                norm_y = tip[1] / h
                return None, {"x": norm_x, "y": norm_y}
        
        return None, None
    
    def _handle_navigation(self, gesture, t, frame):
        """Zone-based navigation"""
        if gesture not in [GestureRecognizer.OPEN_PALM, GestureRecognizer.CLOSED_FIST]:
            self.left_zone_start = 0
            self.right_zone_start = 0
            return None
        
        hand = self.detector.get_hand_center()
        if not hand or t - self.last_swipe < ZONE_DEBOUNCE:
            return None
        
        h, w, _ = frame.shape
        left_zone = int(w * ZONE_SIZE)
        right_zone = int(w * (1 - ZONE_SIZE))
        
        # Left zone (NEXT)
        if hand[0] < left_zone:
            if self.left_zone_start == 0:
                self.left_zone_start = t
            elif t - self.left_zone_start >= ZONE_HOLD_TIME:
                self.last_swipe = t
                self.left_zone_start = 0
                self.right_zone_start = 0
                return "next"
            # Draw zone
            progress = min(1.0, (t - self.left_zone_start) / ZONE_HOLD_TIME)
            color_intensity = int(100 + 155 * progress)
            cv2.rectangle(frame, (0, 0), (left_zone, h), (0, color_intensity, 0), 3)
            cv2.putText(frame, "NEXT", (10, h//2), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, color_intensity, 0), 3)
        else:
            self.left_zone_start = 0
        
        # Right zone (PREVIOUS)
        if hand[0] > right_zone:
            if self.right_zone_start == 0:
                self.right_zone_start = t
            elif t - self.right_zone_start >= ZONE_HOLD_TIME:
                self.last_swipe = t
                self.left_zone_start = 0
                self.right_zone_start = 0
                return "previous"
            # Draw zone
            progress = min(1.0, (t - self.right_zone_start) / ZONE_HOLD_TIME)
            color_intensity = int(100 + 155 * progress)
            cv2.rectangle(frame, (right_zone, 0), (w, h), (0, color_intensity, 0), 3)
            cv2.putText(frame, "PREV", (right_zone + 10, h//2), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, color_intensity, 0), 3)
        else:
            self.right_zone_start = 0
        
        return None
    
    def _check_exit(self, t):
        """Two-hand exit (2s hold)"""
        if self.detector.get_num_hands() >= 2:
            if self.exit_start == 0:
                self.exit_start = t
            elif t - self.exit_start >= EXIT_HOLD_TIME:
                self.clutch_active = False
                self.pointer_active = False
                self.exit_start = 0
                return True
        else:
            self.exit_start = 0
        return False
    
    def _draw_ui(self, frame, gesture, t):
        """Draw UI elements"""
        h, w, _ = frame.shape
        
        # Zone outlines (when clutch active and pointer off)
        if self.clutch_active and not self.pointer_active:
            left_zone = int(w * ZONE_SIZE)
            right_zone = int(w * (1 - ZONE_SIZE))
            cv2.rectangle(frame, (0, 0), (left_zone, h), (100, 100, 100), 2)
            cv2.rectangle(frame, (right_zone, 0), (w, h), (100, 100, 100), 2)
        
        # Activation line
        activation_y = int(h * ACTIVATION_ZONE_RATIO)
        color = (0, 255, 255) if self.pointer_active else (100, 100, 100)
        cv2.line(frame, (0, activation_y), (w, activation_y), color, 2)
        
        # Status bar
        cv2.rectangle(frame, (0, 0), (w, 60), (40, 40, 40), -1)
        
        if self.clutch_active:
            if self.pointer_active:
                cv2.putText(frame, "POINTER MODE", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 255), 3)
                cv2.putText(frame, "∞", (w - 60, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
                cv2.rectangle(frame, (0, 0), (w, h), (0, 255, 255), 8)
            else:
                cv2.putText(frame, "LISTENING", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
                time_left = int(CLUTCH_DURATION - (t - self.clutch_time))
                cv2.putText(frame, f"{time_left}s", (w - 80, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
                cv2.rectangle(frame, (0, 0), (w, h), (0, 255, 0), 8)
        elif self.clutch_start > 0:
            cv2.putText(frame, "ACTIVATING...", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 255), 3)
        else:
            cv2.putText(frame, "IDLE", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
        
        # Exit progress
        if self.exit_start > 0:
            progress = min(1.0, (t - self.exit_start) / EXIT_HOLD_TIME)
            bar_w = int(w * 0.3)
            bar_x = (w - bar_w) // 2
            bar_y = h - 100
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + 30), (50, 50, 50), -1)
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x + int(bar_w * progress), bar_y + 30), (0, 0, 255), -1)
            cv2.putText(frame, "EXITING...", (bar_x + 20, bar_y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)


# Global controller instance
controller = GestureController()


@app.get("/")
async def root():
    return {"message": "Aura Gesture Server Running", "mode": "2", "version": "3.1"}


@app.websocket("/ws/video")
async def video_stream(websocket: WebSocket):
    """WebSocket endpoint for video streaming with gesture detection"""
    await websocket.accept()
    
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 30)
    
    print("📹 Video stream started")
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Process with gesture controller
            processed_frame, gesture_data = controller.process_frame(frame)
            
            # Encode frame as JPEG
            _, buffer = cv2.imencode('.jpg', processed_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            frame_base64 = base64.b64encode(buffer).decode('utf-8')
            
            # Send frame + gesture data
            await websocket.send_json({
                "frame": frame_base64,
                "gesture_data": gesture_data
            })
            
            await asyncio.sleep(0.033)  # ~30 FPS
            
    except WebSocketDisconnect:
        print("📹 Video stream disconnected")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        cap.release()
        print("📹 Video stream stopped")


@app.get("/status")
async def get_status():
    """Get current controller status"""
    return {
        "clutch_active": controller.clutch_active,
        "pointer_active": controller.pointer_active,
        "gesture": controller.recognizer.get_stable_gesture()
    }


if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Aura Gesture Server...")
    print("📡 Backend: http://localhost:8000")
    print("📹 WebSocket: ws://localhost:8000/ws/video")
    uvicorn.run(app, host="0.0.0.0", port=8000)

