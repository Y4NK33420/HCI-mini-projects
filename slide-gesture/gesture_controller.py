"""
Aura - Mode 1: Universal Desktop Controller
A standalone gesture control system compatible with any presentation software.

HCI Features Implemented:
- Clutch mechanism (Feature 3.1)
- Positional activation zone (Feature 3.2)
- Core navigation and interaction (Feature 3.3)
- Critical action safety (Feature 3.4)
"""

import cv2
import pyautogui
import numpy as np
import time
import sys
import os
import platform

# Add shared module to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from shared.hand_detector import HandDetector, GestureRecognizer, SwipeDetector

# Windows-specific imports for overlay window
if platform.system() == "Windows":
    try:
        import win32gui  # type: ignore
        import win32con  # type: ignore

        WINDOWS_OVERLAY_AVAILABLE = True
    except ImportError:
        print("⚠️  Warning: pywin32 not installed. Overlay mode will not work.")
        print("   Install with: pip install pywin32")
        WINDOWS_OVERLAY_AVAILABLE = False
else:
    WINDOWS_OVERLAY_AVAILABLE = False


# --- Configuration Constants ---
# Overlay Configuration
ENABLE_OVERLAY_MODE = (
    True  # Set to True to enable overlay mode (window stays on top, click-through)
)
OVERLAY_OPACITY = 0.5  # Opacity of overlay window (0.0-1.0, lower = more transparent)

# HCI: "Clutch" configuration (Feature 3.1)
CLUTCH_GESTURE_THRESHOLD = 2.0  # Seconds to hold "Thumbs Up" to activate
CLUTCH_WINDOW_DURATION = 15.0   # Seconds the gesture window stays active

# HCI: Positional Activation (Feature 3.2)
ACTIVATION_ZONE_RATIO = 0.6  # Gestures only count if hand is in top 60% of frame

# HCI: Pointer configuration
POINTER_SMOOTHING = 5  # Smoothing factor (higher = smoother, more lag)

# HCI: Swipe configuration (NEW: Zone-based approach)
SWIPE_ZONE_SIZE = 0.30       # 30% of screen width on each side is a swipe zone (increased!)
SWIPE_HOLD_TIME = 0.3        # Seconds to hold hand in zone to trigger
SWIPE_DEBOUNCE_TIME = 1.5    # Seconds to wait between swipes

# HCI: Two-hand exit configuration
TWO_HAND_HOLD_TIME = 2.0     # Must hold both hands for 2 seconds to exit (increased!)

# HCI: Pointer configuration (IMPROVED)
POINTER_SMOOTHING_FACTOR = 7  # Higher = smoother but more lag (increased from 5)
PEACE_SIGN_HOLD_TIME = 1.0    # Seconds to hold peace sign to toggle pointer mode

# Screen size for pointer control
SCREEN_WIDTH, SCREEN_HEIGHT = pyautogui.size()

# Prevent pyautogui fail-safe
pyautogui.FAILSAFE = False


class AuraController:
    """Main controller class that manages the gesture-based presentation control."""

    def __init__(self):
        self.detector = HandDetector(max_num_hands=2)
        self.recognizer = GestureRecognizer(self.detector)

        # State variables
        self.clutch_active = False
        self.clutch_hold_start = 0
        self.clutch_activation_time = 0
        self.clutch_paused = False  # NEW: Pause timer when pointer is active

        # NEW: Improved pointer mode
        self.pointer_active = False
        self.pointer_prev_x = 0
        self.pointer_prev_y = 0
        self.pointer_entry_time = 0  # Track when pointer was activated
        self.peace_sign_hold_start = 0  # Track peace sign hold time

        # NEW: Zone-based swipe detection
        self.in_left_zone_since = 0
        self.in_right_zone_since = 0
        self.last_swipe_time = 0

        # NEW: Two-hand exit detection
        self.two_hands_since = 0

        # Video capture
        self.cap = None

    def initialize_camera(self, camera_index=0):
        """Initialize the webcam."""
        self.cap = cv2.VideoCapture(camera_index)
        if not self.cap.isOpened():
            raise Exception("Error: Cannot open webcam.")

        # Set camera properties for better performance
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)

    def setup_overlay_window(self, window_name):
        """
        Configure the window to be an overlay that stays on top and is click-through.
        This allows the gesture control window to be visible while interacting with other apps.
        """
        if not ENABLE_OVERLAY_MODE or not WINDOWS_OVERLAY_AVAILABLE:
            return

        try:
            # Create the window first
            cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

            # Set window to always be on top
            cv2.setWindowProperty(window_name, cv2.WND_PROP_TOPMOST, 1)

            # Get the window handle
            hwnd = win32gui.FindWindow(None, window_name)
            if hwnd:
                # Get current window style
                style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)

                # Set window as layered (required for transparency and click-through)
                style |= win32con.WS_EX_LAYERED
                # Set window as transparent to mouse events (click-through)
                style |= win32con.WS_EX_TRANSPARENT
                # Keep it on top
                style |= win32con.WS_EX_TOPMOST

                # Apply the new style
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style)

                # Set window opacity (0 = invisible, 255 = opaque)
                opacity = int(255 * OVERLAY_OPACITY)
                win32gui.SetLayeredWindowAttributes(
                    hwnd, 0, opacity, win32con.LWA_ALPHA
                )

                # Position window to always be on top
                win32gui.SetWindowPos(
                    hwnd,
                    win32con.HWND_TOPMOST,
                    0,
                    0,
                    0,
                    0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE,
                )

                print("✅ Overlay mode enabled: Window is now on top and click-through")
                print(f"   Opacity: {OVERLAY_OPACITY:.0%}")
            else:
                print("⚠️  Warning: Could not find window handle for overlay mode")
        except Exception as e:
            print(f"⚠️  Warning: Could not enable overlay mode: {e}")

    def check_clutch_activation(self, gesture, current_time):
        """
        HCI Feature 3.1: Clutch Mechanism (IMPROVED)
        Manages the deliberate activation of gesture control.
        Timer pauses when pointer is active.
        
        Returns:
            True if clutch status changed
        """
        if gesture == GestureRecognizer.THUMBS_UP:
            if not self.clutch_active:
                # User is holding thumbs up
                if self.clutch_hold_start == 0:
                    self.clutch_hold_start = current_time
                elif current_time - self.clutch_hold_start >= CLUTCH_GESTURE_THRESHOLD:
                    # Activate clutch!
                    self.clutch_active = True
                    self.clutch_activation_time = current_time
                    self.clutch_hold_start = 0
                    print("🟢 CLUTCH ACTIVATED - Gesture listening enabled")
                    return True
        else:
            # Reset hold timer if gesture is lost
            self.clutch_hold_start = 0

        # Check if clutch window has expired (but not if pointer is active!)
        if self.clutch_active and not self.pointer_active:
            if current_time - self.clutch_activation_time > CLUTCH_WINDOW_DURATION:
                self.clutch_active = False
                print("🔴 CLUTCH DEACTIVATED - Gesture listening disabled")
                return True

        return False

    def handle_pointer(self, gesture, current_time, frame):
        """
        HCI Feature 3.3: Virtual Pointer (COMPLETELY REDESIGNED v3.1)
        Peace sign (hold 1s) toggles pointer mode on/off.
        When active, timer pauses and can use pointer indefinitely.
        Uses FULL camera frame including area below activation line.
        """
        h, w, _ = frame.shape

        # Check for peace sign hold to toggle
        if gesture == GestureRecognizer.PEACE_SIGN:
            # Start tracking hold time
            if self.peace_sign_hold_start == 0:
                self.peace_sign_hold_start = current_time

            # Check if held long enough
            hold_duration = current_time - self.peace_sign_hold_start

            if hold_duration >= PEACE_SIGN_HOLD_TIME:
                # Toggle pointer mode
                if not self.pointer_active:
                    # Activate pointer mode
                    self.pointer_active = True
                    self.pointer_entry_time = current_time
                    self.pointer_prev_x = 0
                    self.pointer_prev_y = 0
                    print("🎯 POINTER MODE ACTIVATED - Timer paused")
                    print("   Use index finger to point ANYWHERE on screen (full frame!)")
                    print("   Hold peace sign for 1s again to exit pointer mode")
                else:
                    # Deactivate pointer mode
                    self.pointer_active = False
                    self.pointer_prev_x = 0
                    self.pointer_prev_y = 0
                    # Extend clutch time by the time spent in pointer mode
                    time_in_pointer = current_time - self.pointer_entry_time
                    self.clutch_activation_time += time_in_pointer
                    print("🎯 POINTER MODE DEACTIVATED - Timer resumed")

                # Reset hold timer after toggle
                self.peace_sign_hold_start = 0
            else:
                # Show progress indicator while holding
                progress = hold_duration / PEACE_SIGN_HOLD_TIME
                bar_width = int(w * 0.3)
                bar_x = (w - bar_width) // 2
                bar_y = h - 150

                # Draw progress bar
                cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_width, bar_y + 20), (50, 50, 50), cv2.FILLED)
                cv2.rectangle(frame, (bar_x, bar_y), (bar_x + int(bar_width * progress), bar_y + 20), (0, 255, 255), cv2.FILLED)

                toggle_text = "ACTIVATING POINTER..." if not self.pointer_active else "DEACTIVATING POINTER..."
                cv2.putText(frame, toggle_text, (bar_x, bar_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        else:
            # Reset hold timer if gesture is lost
            self.peace_sign_hold_start = 0

        # If pointer is active, track index finger (FULL FRAME - even below activation line!)
        if self.pointer_active and gesture == GestureRecognizer.INDEX_POINT:
            # Get index finger tip position
            tip_pos = self.detector.get_finger_tip(1)  # 1 = index finger
            if tip_pos:
                # Draw visual feedback (bigger and clearer)
                cv2.circle(frame, tuple(tip_pos), 20, (0, 255, 255), cv2.FILLED)
                cv2.circle(frame, tuple(tip_pos), 25, (255, 255, 0), 3)
                cv2.circle(frame, tuple(tip_pos), 30, (0, 255, 0), 2)

                # Draw line from activation zone to show full frame is active
                activation_y = int(h * ACTIVATION_ZONE_RATIO)
                cv2.line(frame, (0, activation_y), (w, activation_y), (0, 255, 255), 3)
                cv2.putText(frame, "FULL FRAME ACTIVE", (w//2 - 100, activation_y - 10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

                # Use ENTIRE camera frame (including area below activation line!)
                # Map directly from camera coordinates to screen coordinates
                screen_x = np.interp(tip_pos[0], [0, w], [0, SCREEN_WIDTH])
                screen_y = np.interp(tip_pos[1], [0, h], [0, SCREEN_HEIGHT])

                # Apply stronger smoothing for stability
                if self.pointer_prev_x == 0:
                    self.pointer_prev_x = screen_x
                    self.pointer_prev_y = screen_y

                smooth_x = self.pointer_prev_x + (screen_x - self.pointer_prev_x) / POINTER_SMOOTHING_FACTOR
                smooth_y = self.pointer_prev_y + (screen_y - self.pointer_prev_y) / POINTER_SMOOTHING_FACTOR

                # Move cursor
                pyautogui.moveTo(smooth_x, smooth_y, duration=0)

                self.pointer_prev_x = smooth_x
                self.pointer_prev_y = smooth_y

    def handle_navigation(self, gesture, current_time, frame):
        """
        HCI Feature 3.3: Core Navigation (IMPROVED)
        Uses zone-based detection for more reliable swipes.
        Disabled when pointer is active.
        """
        if not self.pointer_active:  # Don't navigate while pointer is active
            # Get hand position
            hand_center = self.detector.get_hand_center()

            if hand_center and gesture in [GestureRecognizer.OPEN_PALM, GestureRecognizer.CLOSED_FIST]:
                h, w, _ = frame.shape
                hand_x = hand_center[0]

                # Check debounce
                if current_time - self.last_swipe_time < SWIPE_DEBOUNCE_TIME:
                    return None

                # Define zones
                left_zone_end = int(w * SWIPE_ZONE_SIZE)
                right_zone_start = int(w * (1 - SWIPE_ZONE_SIZE))

                # Check if in left zone (for NEXT slide - swipe from left)
                if hand_x < left_zone_end:
                    if self.in_left_zone_since == 0:
                        self.in_left_zone_since = current_time
                    elif current_time - self.in_left_zone_since >= SWIPE_HOLD_TIME:
                        # Trigger NEXT
                        pyautogui.press('right')
                        print("➡️  NEXT SLIDE (from left zone)")
                        self.last_swipe_time = current_time
                        self.in_left_zone_since = 0
                        self.in_right_zone_since = 0
                        return "NEXT SLIDE"

                    # Draw feedback
                    cv2.rectangle(frame, (0, 0), (left_zone_end, h), (0, 255, 0), 3)
                else:
                    self.in_left_zone_since = 0

                # Check if in right zone (for PREVIOUS slide - swipe from right)
                if hand_x > right_zone_start:
                    if self.in_right_zone_since == 0:
                        self.in_right_zone_since = current_time
                    elif current_time - self.in_right_zone_since >= SWIPE_HOLD_TIME:
                        # Trigger PREVIOUS
                        pyautogui.press('left')
                        print("⬅️  PREVIOUS SLIDE (from right zone)")
                        self.last_swipe_time = current_time
                        self.in_left_zone_since = 0
                        self.in_right_zone_since = 0
                        return "PREVIOUS SLIDE"

                    # Draw feedback
                    cv2.rectangle(frame, (right_zone_start, 0), (w, h), (0, 255, 0), 3)
                else:
                    self.in_right_zone_since = 0
            else:
                # Reset if hand not visible or wrong gesture
                self.in_left_zone_since = 0
                self.in_right_zone_since = 0

        return None

    def handle_critical_actions(self, current_time):
        """
        HCI Feature 3.4: Critical Action Safety (IMPROVED)
        Two-hand gesture required for exit - must be stable for 1 second.
        """
        num_hands = self.detector.get_num_hands()

        if num_hands >= 2:
            # Two hands detected - start counting
            if self.two_hands_since == 0:
                self.two_hands_since = current_time
                print("⚠️  Hold both hands for 1 second to exit...")
            elif current_time - self.two_hands_since >= TWO_HAND_HOLD_TIME:
                # Held for full duration - trigger escape
                pyautogui.press('esc')
                print("🚪 EXIT - Two hands held")
                self.clutch_active = False
                self.two_hands_since = 0
                return True
        else:
            # Reset if hands removed
            if self.two_hands_since > 0:
                print("✋ Exit cancelled")
            self.two_hands_since = 0

        return False

    def draw_ui_feedback(self, frame, gesture, current_time):
        """
        Draws UI feedback on the frame to show system state.
        HCI: Clear, non-disruptive feedback.
        """
        h, w, _ = frame.shape

        # Draw swipe zones (NEW - clearer feedback)
        if self.clutch_active:
            left_zone_end = int(w * SWIPE_ZONE_SIZE)
            right_zone_start = int(w * (1 - SWIPE_ZONE_SIZE))

            # Left zone (for NEXT)
            cv2.rectangle(frame, (0, 0), (left_zone_end, h), (100, 100, 100), 2)
            cv2.putText(
                frame,
                "NEXT",
                (10, h // 2),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (100, 100, 100),
                2
            )
            cv2.putText(
                frame,
                "Hold 0.3s",
                (10, h // 2 + 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (100, 100, 100),
                1
            )

            # Right zone (for PREVIOUS)
            cv2.rectangle(frame, (right_zone_start, 0), (w, h), (100, 100, 100), 2)
            cv2.putText(
                frame,
                "PREV",
                (right_zone_start + 10, h // 2),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (100, 100, 100),
                2
            )
            cv2.putText(
                frame,
                "Hold 0.3s",
                (right_zone_start + 10, h // 2 + 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (100, 100, 100),
                1
            )

        # Draw activation zone line (Feature 3.2)
        activation_y = int(h * ACTIVATION_ZONE_RATIO)
        cv2.line(frame, (0, activation_y), (w, activation_y), (100, 100, 100), 2)
        cv2.putText(
            frame,
            "RAISE HAND ABOVE THIS LINE",
            (10, activation_y - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (100, 100, 100),
            1
        )

        # Status bar at top
        status_bar_height = 60
        cv2.rectangle(frame, (0, 0), (w, status_bar_height), (40, 40, 40), cv2.FILLED)

        # Clutch status
        if self.clutch_active:
            status_text = "🟢 LISTENING"
            status_color = (0, 255, 0)

            # Show time remaining
            time_remaining = CLUTCH_WINDOW_DURATION - (current_time - self.clutch_activation_time)
            time_text = f"{int(time_remaining)}s"
            cv2.putText(frame, time_text, (w - 80, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_color, 2)

            # Draw border around frame
            cv2.rectangle(frame, (0, 0), (w, h), status_color, 8)

        elif self.clutch_hold_start > 0:
            status_text = "⏳ ACTIVATING..."
            status_color = (0, 255, 255)
        else:
            status_text = "🔴 IDLE"
            status_color = (0, 0, 255)

        cv2.putText(frame, status_text, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, status_color, 2)

        # Current gesture
        gesture_text = f"Gesture: {gesture}"
        cv2.putText(frame, gesture_text, (w - 300, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

        # Pointer status (NEW - more prominent)
        if self.pointer_active:
            # Draw big pointer mode indicator
            pointer_text = "🎯 POINTER MODE - Timer Paused"
            text_size = cv2.getTextSize(pointer_text, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
            text_x = (w - text_size[0]) // 2
            text_y = 100

            # Background box
            cv2.rectangle(frame, (text_x - 10, text_y - 30), (text_x + text_size[0] + 10, text_y + 10), (0, 0, 0), cv2.FILLED)
            cv2.rectangle(frame, (text_x - 10, text_y - 30), (text_x + text_size[0] + 10, text_y + 10), (0, 255, 255), 3)

            # Text
            cv2.putText(frame, pointer_text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

            # Instructions
            cv2.putText(frame, "Point with index finger | Hold peace sign 1s to exit", 
                       (text_x, text_y + 35), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

            # Show full frame indicator
            cv2.putText(frame, "FULL FRAME MODE - Point anywhere!", 
                       (text_x, text_y + 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 255, 255), 1)

        # Two-hand exit progress
        if self.two_hands_since > 0:
            progress = min(1.0, (current_time - self.two_hands_since) / TWO_HAND_HOLD_TIME)
            bar_width = int(w * 0.3)
            bar_x = (w - bar_width) // 2
            bar_y = h - 100

            cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_width, bar_y + 30), (50, 50, 50), cv2.FILLED)
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x + int(bar_width * progress), bar_y + 30), (0, 0, 255), cv2.FILLED)
            cv2.putText(frame, "EXITING...", (bar_x + 10, bar_y + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        # Instructions (NEW - clearer, context-aware)
        if not self.clutch_active:
            cv2.putText(
                frame,
                "Hold THUMBS UP for 2s to activate | Q to quit",
                (10, h - 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (200, 200, 200),
                1
            )
        elif self.pointer_active:
            cv2.putText(
                frame,
                "POINTER ACTIVE: Point with finger ANYWHERE | Hold peace sign 1s to exit",
                (10, h - 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 255),
                1
            )
        else:
            cv2.putText(
                frame,
                "LEFT/RIGHT edge = Nav | Peace sign = Pointer | 2 hands (hold 2s) = Exit",
                (10, h - 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (200, 200, 200),
                1
            )

    def run(self):
        """Main control loop."""
        print("=" * 60)
        print("🎯 AURA GESTURE CONTROLLER - MODE 1")
        print("=" * 60)
        print("\n📋 GESTURES:")
        print("  👍 Hold 'Thumbs Up' for 2 seconds → Activate gesture listening")
        print("\n  🔄 NAVIGATION (NEW IMPROVED METHOD):")
        print("     ➡️  Move hand to LEFT edge and hold 0.3s → NEXT slide")
        print("     ⬅️  Move hand to RIGHT edge and hold 0.3s → PREVIOUS slide")
        print("     💡 You'll see zones highlighted on screen!")
        print("\n  🎯 POINTER (NEW IMPROVED METHOD v3.1!):")
        print("     ✌️  Hold Peace Sign for 1s → Toggle pointer mode ON/OFF")
        print("     ☝️  While active: Point with index finger ANYWHERE")
        print("     💡 Timer pauses while in pointer mode!")
        print("     💡 Uses ENTIRE camera frame (even below activation line)!")
        print("     💡 Hold peace sign 1s again to exit pointer mode")
        print("\n  🚪 EXIT:")
        print("     ✋✋ Show both hands for 2 seconds → Exit (ESC)")
        print("\n⚠️  HCI Features:")
        print("  • Gestures only register above the activation line")
        print("  • Clutch window lasts 15 seconds (pauses in pointer mode)")
        print("  • Zone-based swipes are more reliable (30% zones)")
        print("  • Two-hand exit requires 2s hold to prevent accidents")
        print("  • Pointer uses ENTIRE camera frame (even below activation line)")
        print("  • Peace sign requires 1s hold to prevent accidental toggles")
        if ENABLE_OVERLAY_MODE and WINDOWS_OVERLAY_AVAILABLE:
            print("  • OVERLAY MODE: Window stays on top and is click-through")
        print("\n🎬 Press 'Q' in the video window to quit")
        print("=" * 60)
        print()

        self.initialize_camera()

        # Window name
        window_name = "Aura Controller - Press 'Q' to quit"

        # Setup overlay window (must be done before first imshow)
        self.setup_overlay_window(window_name)

        try:
            while True:
                success, frame = self.cap.read()
                if not success:
                    print("Error: Failed to capture frame.")
                    break

                current_time = time.time()

                # Process hand detection
                frame = self.detector.find_hands(frame, flip=True)
                landmarks = self.detector.get_landmarks(frame)
                fingers = self.detector.get_fingers_up()

                # Recognize gesture
                gesture = self.recognizer.recognize_static_gesture(fingers)
                self.recognizer.add_to_history(gesture)
                stable_gesture = self.recognizer.get_stable_gesture()

                # HCI Feature 3.2: Check if hand is in activation zone
                h, w, _ = frame.shape
                activation_y = int(h * ACTIVATION_ZONE_RATIO)
                in_activation_zone = self.detector.is_above_threshold(activation_y) if landmarks else False

                # Only process gestures if hand is in activation zone
                # EXCEPT for pointer mode which uses the entire frame!
                if in_activation_zone or not landmarks or self.pointer_active:
                    # Always check clutch activation (even when not active)
                    self.check_clutch_activation(stable_gesture, current_time)

                    # Only process other gestures when clutch is active
                    if self.clutch_active:
                        # Check for critical actions first (Feature 3.4)
                        if self.handle_critical_actions(current_time):
                            pass  # Exit was triggered

                        # Handle pointer (Feature 3.3) - works in FULL FRAME
                        self.handle_pointer(stable_gesture, current_time, frame)

                        # Handle navigation (Feature 3.3) - only if pointer not active
                        if not self.pointer_active:
                            self.handle_navigation(stable_gesture, current_time, frame)

                # Draw hand landmarks
                self.detector.draw_landmarks(frame)

                # Draw UI feedback
                self.draw_ui_feedback(frame, stable_gesture, current_time)

                # Show frame
                cv2.imshow(window_name, frame)

                # Check for quit
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    print("\n👋 Shutting down...")
                    break

        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up resources."""
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()
        self.detector.close()
        print("✅ Cleanup complete")


def main():
    try:
        controller = AuraController()
        controller.run()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
