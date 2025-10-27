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
        self.current_mode = "idle"  # idle, drawing, erasing, shape
        self.current_color = "#00FF00"  # Green
        self.brush_size = 5
        self.eraser_size = 15
        self.last_position = None

        # Timers
        self.peace_sign_hold_start = 0
        self.peace_sign_hold_time = 2.0  # 2 seconds for color change
        self.peace_sign_cooldown = 0
        self.two_hands_hold_start = 0
        self.two_hands_hold_time = 2.0  # 2 seconds for clear canvas
        self.two_hands_cooldown = 0
        self.cooldown_duration = 1.0  # 1 second cooldown after action

        # Undo/Redo state
        self.last_palm_x = None
        self.swipe_threshold = 0.3  # 30% of screen width
        self.swipe_cooldown = 0
        self.swipe_cooldown_duration = 0.5

        # Shape mode state
        self.shape_mode_active = False
        self.shape_cycling = False
        self.thumbs_up_hold_start = 0
        self.thumbs_up_hold_time = 2.0  # 2 seconds to activate shape mode
        self.shape_cycle_start = 0
        self.shape_cycle_interval = 4.0  # Cycle through shapes every 4 seconds (slower, more predictable)
        self.shape_cycle_initial_delay = 2.0  # 2 second pause before first cycle
        self.shapes = ["circle", "rectangle", "triangle", "line"]
        self.current_shape_index = 0
        self.selected_shape = None
        self.shape_start_pos = None
        self.shape_preview_active = False  # Track if we're previewing a shape

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
            thumb_tip = hand_landmarks.landmark[4]
            tip_x = int(index_tip.x * w)
            tip_y = int(index_tip.y * h)

            # Normalize position (0-1 range)
            norm_x = index_tip.x
            norm_y = index_tip.y
            position = {"x": norm_x, "y": norm_y}

            # Detect gesture
            gesture = self._recognize_gesture(fingers)
            current_time = time.time()

            # === SHAPE MODE LOGIC ===
            if self.shape_mode_active:
                # We're in shape mode
                if gesture == "thumbs_up":
                    # Exit shape mode
                    if self.thumbs_up_hold_start == 0:
                        self.thumbs_up_hold_start = current_time

                    hold_duration = current_time - self.thumbs_up_hold_start
                    if hold_duration >= self.thumbs_up_hold_time:
                        self.shape_mode_active = False
                        self.shape_cycling = False
                        self.selected_shape = None
                        self.thumbs_up_hold_start = 0
                        action = {"type": "shape_mode_exit"}
                    else:
                        # Show progress bar for exit
                        progress = hold_duration / self.thumbs_up_hold_time
                        bar_w = int(w * 0.3)
                        bar_x = (w - bar_w) // 2
                        bar_y = 100
                        cv2.rectangle(
                            frame,
                            (bar_x, bar_y),
                            (bar_x + bar_w, bar_y + 20),
                            (50, 50, 50),
                            -1,
                        )
                        cv2.rectangle(
                            frame,
                            (bar_x, bar_y),
                            (bar_x + int(bar_w * progress), bar_y + 20),
                            (255, 100, 0),
                            -1,
                        )
                        cv2.putText(
                            frame,
                            "EXITING SHAPE MODE...",
                            (bar_x - 50, bar_y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            (255, 100, 0),
                            2,
                        )

                elif gesture == "open_palm":
                    # Select current shape (if cycling) or cancel shape drawing (if selected)
                    if self.shape_cycling:
                        self.selected_shape = self.shapes[self.current_shape_index]
                        self.shape_cycling = False
                        self.shape_start_pos = None
                        self.shape_preview_active = False
                        action = {
                            "type": "shape_selected",
                            "shape": self.selected_shape,
                        }
                    elif self.selected_shape:
                        # Cancel current shape drawing and go back to selection
                        self.selected_shape = None
                        self.shape_start_pos = None
                        self.shape_preview_active = False
                        self.shape_cycling = True
                        self.shape_cycle_start = current_time
                        action = {"type": "shape_cancelled"}

                elif gesture == "index_point":
                    # Draw/preview selected shape
                    if self.selected_shape:
                        if self.shape_start_pos is None:
                            # First point - set start position
                            self.shape_start_pos = position
                            self.shape_preview_active = True
                            action = {"type": "shape_start", "position": position}
                        else:
                            # Continue preview - show shape in real-time
                            action = {
                                "type": "shape_preview",
                                "shape": self.selected_shape,
                                "start": self.shape_start_pos,
                                "end": position,
                                "color": self.current_color,
                                "size": self.brush_size,
                            }

                        # Visual feedback - yellow circle
                        cv2.circle(frame, (tip_x, tip_y), 12, (0, 255, 255), -1)
                        cv2.circle(frame, (tip_x, tip_y), 16, (255, 255, 255), 2)

                elif gesture == "fist":
                    # Finalize shape drawing
                    if self.selected_shape and self.shape_start_pos is not None:
                        action = {
                            "type": "shape_finalize",
                            "shape": self.selected_shape,
                            "start": self.shape_start_pos,
                            "end": position,
                            "color": self.current_color,
                            "size": self.brush_size,
                        }
                        # Reset shape drawing state but keep shape selected
                        self.shape_start_pos = None
                        self.shape_preview_active = False

                        # Visual feedback
                        cv2.circle(frame, (tip_x, tip_y), 20, (0, 255, 0), 3)
                else:
                    # Reset thumbs up timer for other gestures
                    self.thumbs_up_hold_start = 0

                # Auto-cycle through shapes if not selected
                if not self.selected_shape:
                    if self.shape_cycle_start == 0:
                        self.shape_cycle_start = current_time

                    elapsed = current_time - self.shape_cycle_start
                    
                    # Apply initial delay before starting to cycle
                    if elapsed >= self.shape_cycle_initial_delay:
                        adjusted_elapsed = elapsed - self.shape_cycle_initial_delay
                        self.current_shape_index = int(
                            adjusted_elapsed / self.shape_cycle_interval
                        ) % len(self.shapes)
                    else:
                        # Stay on first shape during initial delay
                        self.current_shape_index = 0
                    
                    self.shape_cycling = True

            # === NORMAL MODE LOGIC ===
            else:
                # Handle gesture
                if gesture == "thumbs_up":
                    # Enter shape mode (with 1s hold timer)
                    if self.thumbs_up_hold_start == 0:
                        self.thumbs_up_hold_start = current_time

                    hold_duration = current_time - self.thumbs_up_hold_start

                    if hold_duration >= self.thumbs_up_hold_time:
                        self.shape_mode_active = True
                        self.shape_cycle_start = 0
                        self.current_shape_index = 0
                        self.thumbs_up_hold_start = 0
                        action = {"type": "shape_mode_enter"}
                    else:
                        # Show progress bar
                        progress = hold_duration / self.thumbs_up_hold_time
                        bar_w = int(w * 0.3)
                        bar_x = (w - bar_w) // 2
                        bar_y = 100
                        cv2.rectangle(
                            frame,
                            (bar_x, bar_y),
                            (bar_x + bar_w, bar_y + 20),
                            (50, 50, 50),
                            -1,
                        )
                        cv2.rectangle(
                            frame,
                            (bar_x, bar_y),
                            (bar_x + int(bar_w * progress), bar_y + 20),
                            (255, 165, 0),
                            -1,
                        )
                        cv2.putText(
                            frame,
                            "SHAPE MODE...",
                            (bar_x, bar_y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            (255, 165, 0),
                            2,
                        )

                elif gesture == "open_palm":
                    # Swipe detection for undo/redo
                    self.thumbs_up_hold_start = 0
                    palm_x = norm_x

                    if (
                        current_time - self.swipe_cooldown
                        > self.swipe_cooldown_duration
                    ):
                        if self.last_palm_x is not None:
                            delta_x = palm_x - self.last_palm_x

                            # Swipe left = undo
                            if delta_x < -self.swipe_threshold:
                                action = {"type": "undo"}
                                self.swipe_cooldown = current_time
                                self.last_palm_x = None
                            # Swipe right = redo
                            elif delta_x > self.swipe_threshold:
                                action = {"type": "redo"}
                                self.swipe_cooldown = current_time
                                self.last_palm_x = None
                            else:
                                self.last_palm_x = palm_x
                        else:
                            self.last_palm_x = palm_x
                    else:
                        self.last_palm_x = None

                elif gesture == "index_point":
                    # Drawing mode
                    self.current_mode = "drawing"
                    self.peace_sign_hold_start = 0
                    self.thumbs_up_hold_start = 0
                    self.last_palm_x = None
                    action = {
                        "type": "draw",
                        "position": position,
                        "color": self.current_color,
                        "size": self.brush_size,
                    }

                    # Visual feedback
                    cv2.circle(
                        frame,
                        (tip_x, tip_y),
                        15,
                        self._hex_to_bgr(self.current_color),
                        -1,
                    )
                    cv2.circle(frame, (tip_x, tip_y), 20, (255, 255, 255), 2)

                elif gesture == "fist":
                    # Erasing mode
                    self.current_mode = "erasing"
                    self.peace_sign_hold_start = 0
                    self.thumbs_up_hold_start = 0
                    self.last_palm_x = None
                    action = {
                        "type": "erase",
                        "position": position,
                        "size": self.eraser_size,
                    }

                    # Visual feedback
                    cv2.circle(frame, (tip_x, tip_y), self.eraser_size, (0, 0, 0), -1)
                    cv2.circle(
                        frame, (tip_x, tip_y), self.eraser_size + 5, (255, 0, 0), 2
                    )

                elif gesture == "peace_sign":
                    # Change color (with 1s hold timer + cooldown)
                    self.thumbs_up_hold_start = 0
                    self.last_palm_x = None
                    # Check if we're in cooldown period
                    if current_time - self.peace_sign_cooldown < self.cooldown_duration:
                        # Still in cooldown, show message
                        cv2.putText(
                            frame,
                            "Wait...",
                            (w // 2 - 30, h - 100),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            (255, 0, 0),
                            2,
                        )
                    else:
                        if self.peace_sign_hold_start == 0:
                            self.peace_sign_hold_start = current_time

                        hold_duration = current_time - self.peace_sign_hold_start

                        if hold_duration >= self.peace_sign_hold_time:
                            self.color_index = (self.color_index + 1) % len(self.colors)
                            self.current_color = self.colors[self.color_index]
                            action = {
                                "type": "color_change",
                                "color": self.current_color,
                            }
                            self.peace_sign_hold_start = 0
                            self.peace_sign_cooldown = current_time  # Start cooldown
                        else:
                            # Show progress bar with color preview
                            progress = hold_duration / self.peace_sign_hold_time
                            bar_w = int(w * 0.4)
                            bar_x = (w - bar_w) // 2
                            bar_y = h - 120

                            # Dark background box
                            cv2.rectangle(
                                frame,
                                (bar_x - 20, bar_y - 50),
                                (bar_x + bar_w + 20, bar_y + 30),
                                (30, 30, 30),
                                -1,
                            )
                            cv2.rectangle(
                                frame,
                                (bar_x - 20, bar_y - 50),
                                (bar_x + bar_w + 20, bar_y + 30),
                                (0, 255, 255),
                                3,
                            )

                            # Show current and next color
                            next_color_index = (self.color_index + 1) % len(self.colors)
                            current_bgr = self._hex_to_bgr(self.current_color)
                            next_bgr = self._hex_to_bgr(self.colors[next_color_index])

                            # Current color box
                            cv2.rectangle(
                                frame,
                                (bar_x, bar_y - 40),
                                (bar_x + 40, bar_y - 10),
                                current_bgr,
                                -1,
                            )
                            cv2.rectangle(
                                frame,
                                (bar_x, bar_y - 40),
                                (bar_x + 40, bar_y - 10),
                                (255, 255, 255),
                                2,
                            )
                            cv2.putText(
                                frame,
                                "NOW",
                                (bar_x + 5, bar_y - 15),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.3,
                                (255, 255, 255),
                                1,
                            )

                            # Arrow
                            cv2.putText(
                                frame,
                                "->",
                                (bar_x + 50, bar_y - 20),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.5,
                                (255, 255, 255),
                                2,
                            )

                            # Next color box (pulsing)
                            cv2.rectangle(
                                frame,
                                (bar_x + 80, bar_y - 40),
                                (bar_x + 120, bar_y - 10),
                                next_bgr,
                                -1,
                            )
                            cv2.rectangle(
                                frame,
                                (bar_x + 80, bar_y - 40),
                                (bar_x + 120, bar_y - 10),
                                (0, 255, 255),
                                3,
                            )
                            cv2.putText(
                                frame,
                                "NEXT",
                                (bar_x + 82, bar_y - 15),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.3,
                                (0, 255, 255),
                                1,
                            )

                            # Progress bar
                            cv2.rectangle(
                                frame,
                                (bar_x, bar_y),
                                (bar_x + bar_w, bar_y + 20),
                                (50, 50, 50),
                                -1,
                            )
                            cv2.rectangle(
                                frame,
                                (bar_x, bar_y),
                                (bar_x + int(bar_w * progress), bar_y + 20),
                                (0, 255, 255),
                                -1,
                            )
                            cv2.putText(
                                frame,
                                "CHANGING COLOR...",
                                (bar_x + bar_w - 150, bar_y + 15),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.4,
                                (255, 255, 255),
                                1,
                            )

                elif gesture == "thumb_index":
                    # Adjust size (works for both brush and eraser)
                    self.peace_sign_hold_start = 0
                    self.thumbs_up_hold_start = 0
                    self.last_palm_x = None
                    thumb_tip = hand_landmarks.landmark[4]
                    distance = np.sqrt(
                        (index_tip.x - thumb_tip.x) ** 2
                        + (index_tip.y - thumb_tip.y) ** 2
                    )
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
                        "eraser_size": self.eraser_size,
                    }

                else:
                    self.current_mode = "idle"
                    self.last_palm_x = None
                    # Reset timers when no recognized gesture
                    if gesture != "peace_sign":
                        self.peace_sign_hold_start = 0
                    if gesture != "thumbs_up":
                        self.thumbs_up_hold_start = 0

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
            "position": position,
            "shape_mode_active": self.shape_mode_active,
            "shape_cycling": self.shape_cycling,
            "current_shape": (
                self.shapes[self.current_shape_index] if self.shape_cycling else None
            ),
            "selected_shape": self.selected_shape,
            "shape_preview_active": self.shape_preview_active,
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
        elif fingers == [1, 0, 0, 0, 0]:
            return "thumbs_up"
        elif fingers == [0, 1, 1, 1, 0] or fingers == [0, 1, 1, 1, 1]:
            return "two_fingers"
        else:
            return "unknown"

    def _hex_to_bgr(self, hex_color):
        """Convert hex color to BGR tuple"""
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return (b, g, r)

    def _draw_shape_icon(self, frame, x, y, shape, color, size, filled=False):
        """Draw a shape icon for visual preview"""
        thickness = 3 if filled else 2

        if shape == "circle":
            cv2.circle(frame, (x, y), size // 2, color, thickness)
        elif shape == "rectangle":
            half = size // 2
            cv2.rectangle(
                frame, (x - half, y - half), (x + half, y + half), color, thickness
            )
        elif shape == "triangle":
            half = size // 2
            pts = np.array(
                [[x, y - half], [x + half, y + half], [x - half, y + half]], np.int32
            )
            pts = pts.reshape((-1, 1, 2))
            cv2.polylines(frame, [pts], True, color, thickness)
        elif shape == "line":
            half = size // 2
            cv2.line(
                frame, (x - half, y + half), (x + half, y - half), color, thickness
            )

    def _draw_ui(self, frame):
        """Draw UI overlay"""
        h, w, _ = frame.shape

        # Status bar
        cv2.rectangle(frame, (0, 0), (w, 60), (40, 40, 40), -1)

        # Mode indicator
        if self.shape_mode_active:
            mode_text = "SHAPE MODE"
            color = (255, 165, 0)
        else:
            mode_text = f"Mode: {self.current_mode.upper()}"
            color = (
                (0, 255, 0)
                if self.current_mode == "drawing"
                else (0, 0, 255) if self.current_mode == "erasing" else (200, 200, 200)
            )
        cv2.putText(frame, mode_text, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)

        # Current color
        cv2.rectangle(frame, (w - 250, 10), (w - 200, 50), self._hex_to_bgr(self.current_color), -1)
        cv2.rectangle(frame, (w - 250, 10), (w - 200, 50), (255, 255, 255), 2)

        # Brush and eraser size
        cv2.putText(frame, f"B:{self.brush_size} E:{self.eraser_size}", (w - 190, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

        # Shape mode info overlay
        if self.shape_mode_active:
            # Large shape mode banner
            cv2.rectangle(
                frame,
                (w // 2 - 250, h - 300),
                (w // 2 + 250, h - 120),
                (40, 40, 40),
                -1,
            )
            cv2.rectangle(
                frame,
                (w // 2 - 250, h - 300),
                (w // 2 + 250, h - 120),
                (255, 165, 0),
                4,
            )

            if self.selected_shape:
                # Shape selected - draw large preview of selected shape
                cv2.putText(
                    frame,
                    f"SELECTED: {self.selected_shape.upper()}",
                    (w // 2 - 180, h - 260),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 0),
                    2,
                )

                # Draw shape preview icon
                self._draw_shape_icon(
                    frame, w // 2, h - 210, self.selected_shape, (0, 255, 0), 40, True
                )

                if self.shape_preview_active:
                    cv2.putText(
                        frame,
                        "Fist: Finalize | Palm: Cancel",
                        (w // 2 - 150, h - 150),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (255, 255, 0),
                        1,
                    )
                else:
                    cv2.putText(
                        frame,
                        "Index: Draw Shape",
                        (w // 2 - 150, h - 150),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (255, 255, 255),
                        1,
                    )
                cv2.putText(
                    frame,
                    "Thumbs Up (2s): Exit | Palm: Change Shape",
                    (w // 2 - 200, h - 130),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (255, 255, 255),
                    1,
                )
            else:
                # Cycling through shapes - show ALL shapes with current one highlighted
                cv2.putText(
                    frame,
                    "SELECT A SHAPE",
                    (w // 2 - 100, h - 270),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (255, 255, 255),
                    2,
                )

                # Draw all shape icons horizontally
                shape_spacing = 100
                start_x = w // 2 - (len(self.shapes) * shape_spacing) // 2 + 50
                for i, shape in enumerate(self.shapes):
                    x_pos = start_x + i * shape_spacing
                    y_pos = h - 210

                    # Highlight current shape
                    if i == self.current_shape_index:
                        color = (0, 255, 255)  # Cyan for selected
                        size = 50
                        # Pulsing highlight box
                        cv2.rectangle(
                            frame,
                            (x_pos - 40, y_pos - 40),
                            (x_pos + 40, y_pos + 40),
                            color,
                            3,
                        )
                        cv2.putText(
                            frame,
                            shape.upper()[:4],
                            (x_pos - 30, y_pos + 60),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            color,
                            2,
                        )
                    else:
                        color = (150, 150, 150)  # Gray for others
                        size = 35
                        cv2.putText(
                            frame,
                            shape.upper()[:4],
                            (x_pos - 30, y_pos + 60),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.4,
                            color,
                            1,
                        )

                    self._draw_shape_icon(
                        frame,
                        x_pos,
                        y_pos,
                        shape,
                        color,
                        size,
                        i == self.current_shape_index,
                    )

                # Show cycle progress indicator
                if self.shape_cycle_start > 0:
                    import time
                    current_time = time.time()
                    elapsed = current_time - self.shape_cycle_start
                    
                    # Calculate progress within current cycle
                    if elapsed < self.shape_cycle_initial_delay:
                        # Initial delay progress
                        cycle_progress = elapsed / self.shape_cycle_initial_delay
                        status_text = "LOADING..."
                        bar_color = (255, 255, 0)  # Yellow for initial delay
                    else:
                        # Regular cycle progress
                        adjusted_elapsed = elapsed - self.shape_cycle_initial_delay
                        time_in_cycle = adjusted_elapsed % self.shape_cycle_interval
                        cycle_progress = time_in_cycle / self.shape_cycle_interval
                        next_shape_index = (self.current_shape_index + 1) % len(self.shapes)
                        status_text = f"NEXT: {self.shapes[next_shape_index].upper()}"
                        bar_color = (255, 165, 0)  # Orange for regular cycle
                    
                    # Draw progress bar
                    bar_w = 300
                    bar_h = 12
                    bar_x = (w - bar_w) // 2
                    bar_y = h - 150
                    
                    # Background
                    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (50, 50, 50), -1)
                    # Progress
                    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + int(bar_w * cycle_progress), bar_y + bar_h), bar_color, -1)
                    # Border
                    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (255, 255, 255), 1)
                    
                    # Status text above progress bar
                    text_size = cv2.getTextSize(status_text, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)[0]
                    text_x = bar_x + (bar_w - text_size[0]) // 2
                    cv2.putText(frame, status_text, (text_x, bar_y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, bar_color, 1)

                cv2.putText(
                    frame,
                    "OPEN PALM TO SELECT",
                    (w // 2 - 120, h - 175),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 255),
                    2,
                )
                cv2.putText(
                    frame,
                    "Thumbs Up (2s): Exit",
                    (w // 2 - 120, h - 130),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 255, 255),
                    1,
                )

        # Instructions (normal mode)
        else:
            instructions = [
                "Index: Draw",
                "Fist: Erase",
                "Peace (2s): Color",
                "Two Hands (2s): Clear",
                "Pinch: Size",
                "Thumbs Up (2s): Shapes",
                "Palm Swipe L/R: Undo/Redo",
            ]

            y_offset = h - 200
            for instruction in instructions:
                cv2.putText(
                    frame,
                    instruction,
                    (10, y_offset),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 255, 255),
                    1,
                )
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
