"""
Gesture Painting App - FastAPI Backend
Real-time hand gesture detection for creative painting
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import cv2
import numpy as np
import asyncio
import json
import base64
import time
import mediapipe as mp

app = FastAPI(title="Gesture Painting Server")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GesturePainter:
    """Detects hand gestures for painting"""
    
    def __init__(self):
        # MediaPipe setup
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,  # Support 2 hands for clear gesture
            min_detection_confidence=0.7,
            min_tracking_confidence=0.5
        )
        self.mp_draw = mp.solutions.drawing_utils
        
        # State
        self.current_mode = "idle"  # idle, drawing, erasing
        self.current_color = "#00FF00"  # Green
        self.brush_size = 5
        self.eraser_size = 15
        self.last_position = None
        
        # Timers
        self.peace_sign_hold_start = 0
        self.peace_sign_hold_time = 1.0  # 1 second for color change
        self.peace_sign_cooldown = 0
        self.two_hands_hold_start = 0
        self.two_hands_hold_time = 2.0  # 2 seconds for clear canvas
        self.two_hands_cooldown = 0
        self.cooldown_duration = 1.0  # 1 second cooldown after action
        
        # Color palette
        self.colors = [
            "#FF0000",  # Red
            "#00FF00",  # Green
            "#0000FF",  # Blue
            "#FFFF00",  # Yellow
            "#FF00FF",  # Magenta
            "#00FFFF",  # Cyan
            "#FFFFFF",  # White
            "#FFA500",  # Orange
        ]
        self.color_index = 1
    
    def process_frame(self, frame):
        """Process frame and detect gestures"""
        h, w, _ = frame.shape
        
        # Flip for mirror effect
        frame = cv2.flip(frame, 1)
        
        # Convert to RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb_frame)
        
        action = None
        position = None
        current_time = time.time()
        num_hands = len(results.multi_hand_landmarks) if results.multi_hand_landmarks else 0
        
        # Check for two hands (clear canvas)
        if num_hands >= 2:
            # Draw both hands
            for hand_landmarks in results.multi_hand_landmarks:
                self.mp_draw.draw_landmarks(
                    frame, 
                    hand_landmarks, 
                    self.mp_hands.HAND_CONNECTIONS,
                    self.mp_draw.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2),
                    self.mp_draw.DrawingSpec(color=(255, 255, 255), thickness=2)
                )
            
            # Two hands detected - clear canvas gesture (with cooldown)
            # Check if we're in cooldown period
            if current_time - self.two_hands_cooldown < self.cooldown_duration:
                # Still in cooldown, show message
                cv2.putText(frame, "Wait...", (w//2 - 30, h//2), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
            else:
                if self.two_hands_hold_start == 0:
                    self.two_hands_hold_start = current_time
                
                hold_duration = current_time - self.two_hands_hold_start
                
                if hold_duration >= self.two_hands_hold_time:
                    action = {"type": "clear"}
                    self.two_hands_hold_start = 0
                    self.two_hands_cooldown = current_time  # Start cooldown
                else:
                    # Show progress bar
                    progress = hold_duration / self.two_hands_hold_time
                    bar_w = int(w * 0.4)
                    bar_x = (w - bar_w) // 2
                    bar_y = h // 2
                    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + 30), (50, 50, 50), -1)
                    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + int(bar_w * progress), bar_y + 30), (0, 0, 255), -1)
                    cv2.putText(frame, "CLEARING CANVAS...", (bar_x, bar_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        
        elif results.multi_hand_landmarks:
            # Single hand detected
            self.two_hands_hold_start = 0
            hand_landmarks = results.multi_hand_landmarks[0]
            
            # Draw hand skeleton
            self.mp_draw.draw_landmarks(
                frame, 
                hand_landmarks, 
                self.mp_hands.HAND_CONNECTIONS,
                self.mp_draw.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2),
                self.mp_draw.DrawingSpec(color=(255, 255, 255), thickness=2)
            )
            
            # Get finger states
            fingers = self._get_fingers_up(hand_landmarks)
            
            # Get index finger tip position (for drawing)
            index_tip = hand_landmarks.landmark[8]
            tip_x = int(index_tip.x * w)
            tip_y = int(index_tip.y * h)
            
            # Normalize position (0-1 range)
            norm_x = index_tip.x
            norm_y = index_tip.y
            position = {"x": norm_x, "y": norm_y}
            
            # Detect gesture
            gesture = self._recognize_gesture(fingers)
            current_time = time.time()
            
            # Handle gesture
            if gesture == "index_point":
                # Drawing mode
                self.current_mode = "drawing"
                self.peace_sign_hold_start = 0
                action = {
                    "type": "draw",
                    "position": position,
                    "color": self.current_color,
                    "size": self.brush_size
                }
                
                # Visual feedback
                cv2.circle(frame, (tip_x, tip_y), 15, self._hex_to_bgr(self.current_color), -1)
                cv2.circle(frame, (tip_x, tip_y), 20, (255, 255, 255), 2)
                
            elif gesture == "fist":
                # Erasing mode
                self.current_mode = "erasing"
                self.peace_sign_hold_start = 0
                action = {
                    "type": "erase",
                    "position": position,
                    "size": self.eraser_size
                }
                
                # Visual feedback
                cv2.circle(frame, (tip_x, tip_y), self.eraser_size, (0, 0, 0), -1)
                cv2.circle(frame, (tip_x, tip_y), self.eraser_size + 5, (255, 0, 0), 2)
                
            elif gesture == "peace_sign":
                # Change color (with 1s hold timer + cooldown)
                # Check if we're in cooldown period
                if current_time - self.peace_sign_cooldown < self.cooldown_duration:
                    # Still in cooldown, show message
                    cv2.putText(frame, "Wait...", (w//2 - 30, h - 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
                else:
                    if self.peace_sign_hold_start == 0:
                        self.peace_sign_hold_start = current_time
                    
                    hold_duration = current_time - self.peace_sign_hold_start
                    
                    if hold_duration >= self.peace_sign_hold_time:
                        self.color_index = (self.color_index + 1) % len(self.colors)
                        self.current_color = self.colors[self.color_index]
                        action = {
                            "type": "color_change",
                            "color": self.current_color
                        }
                        self.peace_sign_hold_start = 0
                        self.peace_sign_cooldown = current_time  # Start cooldown
                    else:
                        # Show progress bar
                        progress = hold_duration / self.peace_sign_hold_time
                        bar_w = int(w * 0.3)
                        bar_x = (w - bar_w) // 2
                        bar_y = h - 100
                        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + 20), (50, 50, 50), -1)
                        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + int(bar_w * progress), bar_y + 20), (0, 255, 255), -1)
                        cv2.putText(frame, "CHANGING COLOR...", (bar_x, bar_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
                
            elif gesture == "thumb_index":
                # Adjust size (works for both brush and eraser)
                self.peace_sign_hold_start = 0
                thumb_tip = hand_landmarks.landmark[4]
                distance = np.sqrt((index_tip.x - thumb_tip.x)**2 + (index_tip.y - thumb_tip.y)**2)
                new_size = int(distance * 50) + 2
                
                if self.current_mode == "drawing":
                    self.brush_size = new_size
                elif self.current_mode == "erasing":
                    self.eraser_size = new_size
                else:
                    self.brush_size = new_size
                    
                action = {
                    "type": "size_change",
                    "brush_size": self.brush_size,
                    "eraser_size": self.eraser_size
                }
                
            else:
                self.current_mode = "idle"
                # Reset timers when no recognized gesture
                if gesture != "peace_sign":
                    self.peace_sign_hold_start = 0
        
        else:
            # No hands detected
            self.current_mode = "idle"
            self.two_hands_hold_start = 0
            self.peace_sign_hold_start = 0
        
        # Draw UI
        self._draw_ui(frame)
        
        return frame, {
            "mode": self.current_mode,
            "color": self.current_color,
            "brush_size": self.brush_size,
            "eraser_size": self.eraser_size,
            "action": action,
            "position": position
        }
    
    def _get_fingers_up(self, hand_landmarks):
        """Detect which fingers are up"""
        fingers = []
        landmarks = hand_landmarks.landmark
        
        # Thumb
        if landmarks[4].x < landmarks[3].x:
            fingers.append(1)
        else:
            fingers.append(0)
        
        # Other fingers
        tip_ids = [8, 12, 16, 20]
        for tip_id in tip_ids:
            if landmarks[tip_id].y < landmarks[tip_id - 2].y:
                fingers.append(1)
            else:
                fingers.append(0)
        
        return fingers
    
    def _recognize_gesture(self, fingers):
        """Recognize gesture from finger states"""
        if fingers == [0, 1, 0, 0, 0]:
            return "index_point"
        elif fingers == [0, 0, 0, 0, 0]:
            return "fist"
        elif fingers == [0, 1, 1, 0, 0]:
            return "peace_sign"
        elif fingers == [1, 1, 1, 1, 1]:
            return "open_palm"
        elif fingers == [1, 1, 0, 0, 0]:
            return "thumb_index"
        else:
            return "unknown"
    
    def _hex_to_bgr(self, hex_color):
        """Convert hex color to BGR tuple"""
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return (b, g, r)
    
    def _draw_ui(self, frame):
        """Draw UI overlay"""
        h, w, _ = frame.shape
        
        # Status bar
        cv2.rectangle(frame, (0, 0), (w, 60), (40, 40, 40), -1)
        
        # Mode indicator
        mode_text = f"Mode: {self.current_mode.upper()}"
        color = (0, 255, 0) if self.current_mode == "drawing" else (0, 0, 255) if self.current_mode == "erasing" else (200, 200, 200)
        cv2.putText(frame, mode_text, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)
        
        # Current color
        cv2.rectangle(frame, (w - 250, 10), (w - 200, 50), self._hex_to_bgr(self.current_color), -1)
        cv2.rectangle(frame, (w - 250, 10), (w - 200, 50), (255, 255, 255), 2)
        
        # Brush and eraser size
        cv2.putText(frame, f"B:{self.brush_size} E:{self.eraser_size}", (w - 190, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        
        # Instructions
        instructions = [
            "Index: Draw",
            "Fist: Erase",
            "Peace (1s): Color",
            "Two Hands (2s): Clear",
            "Pinch: Size"
        ]
        
        y_offset = h - 150
        for instruction in instructions:
            cv2.putText(frame, instruction, (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            y_offset += 25


# Global painter instance
painter = GesturePainter()


@app.get("/")
async def root():
    return {"message": "Gesture Painting Server", "status": "running"}


@app.websocket("/ws/painting")
async def painting_stream(websocket: WebSocket):
    """WebSocket endpoint for painting stream"""
    await websocket.accept()
    
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 30)
    
    print("🎨 Painting stream started")
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Process with gesture painter
            processed_frame, gesture_data = painter.process_frame(frame)
            
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
        print("🎨 Painting stream disconnected")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        cap.release()
        print("🎨 Painting stream stopped")


if __name__ == "__main__":
    import uvicorn
    print("🎨 Starting Gesture Painting Server...")
    print("📡 Backend: http://localhost:8001")
    print("🎨 WebSocket: ws://localhost:8001/ws/painting")
    uvicorn.run(app, host="0.0.0.0", port=8001)

