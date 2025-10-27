"""
Shared Hand Detection and Gesture Recognition Module
Used by both Mode 1 (Desktop Controller) and Mode 2 (Web App)
"""

import cv2
import mediapipe as mp
import numpy as np


class HandDetector:
    """
    Detects hands and recognizes gestures using MediaPipe.
    Implements HCI principles for robust gesture recognition.
    """
    
    def __init__(self, max_num_hands=2, min_detection_confidence=0.7, min_tracking_confidence=0.5):
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=max_num_hands,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence
        )
        self.mp_drawing = mp.solutions.drawing_utils
        self.landmarks = None
        self.results = None
        
    def find_hands(self, frame, flip=True):
        """
        Processes the frame to find hand landmarks.
        
        Args:
            frame: BGR image from OpenCV
            flip: Whether to flip horizontally for selfie view
            
        Returns:
            Processed frame (BGR)
        """
        if flip:
            frame = cv2.flip(frame, 1)
        
        # Convert to RGB for MediaPipe
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self.results = self.hands.process(frame_rgb)
        
        return frame
    
    def get_landmarks(self, frame, hand_index=0):
        """
        Returns the list of 21 landmarks for a specific hand.
        
        Args:
            frame: The processed frame
            hand_index: Which hand to get (0 = first hand, 1 = second hand)
            
        Returns:
            List of [x, y, z] coordinates for each landmark, or None if no hand found
        """
        self.landmarks = []
        if self.results.multi_hand_landmarks:
            if len(self.results.multi_hand_landmarks) > hand_index:
                hand = self.results.multi_hand_landmarks[hand_index]
                h, w, _ = frame.shape
                for lm in hand.landmark:
                    cx, cy = int(lm.x * w), int(lm.y * h)
                    self.landmarks.append([cx, cy, lm.z])
                return self.landmarks
        return None
    
    def get_num_hands(self):
        """Returns the number of hands currently detected."""
        if self.results.multi_hand_landmarks:
            return len(self.results.multi_hand_landmarks)
        return 0
    
    def get_fingers_up(self):
        """
        Returns which fingers are extended.
        
        Returns:
            List [Thumb, Index, Middle, Ring, Pinky] where 1 = Up, 0 = Down
            None if no hand detected
        """
        if not self.landmarks:
            return None
        
        fingers = []
        tip_ids = [4, 8, 12, 16, 20]  # Landmark IDs for finger tips
        
        # Thumb (special case - check X position)
        # Check if thumb tip X is to the left of the thumb IP joint
        if self.landmarks[tip_ids[0]][0] < self.landmarks[tip_ids[0] - 1][0]:
            fingers.append(1)
        else:
            fingers.append(0)
        
        # Other four fingers (check Y position)
        for id in range(1, 5):
            # Check if finger tip Y is above the PIP joint
            if self.landmarks[tip_ids[id]][1] < self.landmarks[tip_ids[id] - 2][1]:
                fingers.append(1)
            else:
                fingers.append(0)
        
        return fingers
    
    def get_hand_center(self):
        """
        Returns the center point of the hand (wrist position).
        
        Returns:
            [x, y] coordinates of wrist, or None if no hand detected
        """
        if self.landmarks:
            return [self.landmarks[0][0], self.landmarks[0][1]]
        return None
    
    def get_finger_tip(self, finger_index):
        """
        Returns the position of a specific finger tip.
        
        Args:
            finger_index: 0=Thumb, 1=Index, 2=Middle, 3=Ring, 4=Pinky
            
        Returns:
            [x, y] coordinates or None
        """
        tip_ids = [4, 8, 12, 16, 20]
        if self.landmarks and 0 <= finger_index <= 4:
            tip_id = tip_ids[finger_index]
            return [self.landmarks[tip_id][0], self.landmarks[tip_id][1]]
        return None
    
    def is_above_threshold(self, threshold_y):
        """
        HCI Feature: Positional Activation Zone
        Checks if the hand is above a certain Y threshold (chest level).
        
        Args:
            threshold_y: Y coordinate of the threshold line
            
        Returns:
            True if hand is above threshold, False otherwise
        """
        if self.landmarks:
            wrist_y = self.landmarks[0][1]
            return wrist_y < threshold_y
        return False
    
    def draw_landmarks(self, frame):
        """
        Draws hand landmarks on the frame.
        
        Args:
            frame: The frame to draw on
        """
        if self.results.multi_hand_landmarks:
            for hand_landmarks in self.results.multi_hand_landmarks:
                self.mp_drawing.draw_landmarks(
                    frame,
                    hand_landmarks,
                    self.mp_hands.HAND_CONNECTIONS
                )
    
    def close(self):
        """Clean up resources."""
        self.hands.close()


class GestureRecognizer:
    """
    High-level gesture recognition built on HandDetector.
    Implements debouncing and state management for robust gesture control.
    """
    
    # Gesture constants
    THUMBS_UP = "thumbs_up"
    INDEX_POINT = "index_point"
    PEACE_SIGN = "peace_sign"
    OPEN_PALM = "open_palm"
    CLOSED_FIST = "fist"
    SWIPE_RIGHT = "swipe_right"
    SWIPE_LEFT = "swipe_left"
    TWO_HANDS = "two_hands"
    UNKNOWN = "unknown"
    
    def __init__(self, detector):
        """
        Args:
            detector: HandDetector instance
        """
        self.detector = detector
        self.gesture_history = []
        self.history_size = 5
        
    def recognize_static_gesture(self, fingers):
        """
        Recognizes static gestures based on finger positions.
        
        Args:
            fingers: List [Thumb, Index, Middle, Ring, Pinky] (1=up, 0=down)
            
        Returns:
            Gesture name string
        """
        if not fingers:
            return self.UNKNOWN
        
        # Thumbs up: Only thumb extended
        if fingers == [1, 0, 0, 0, 0]:
            return self.THUMBS_UP
        
        # Index point: Only index finger extended
        if fingers == [0, 1, 0, 0, 0]:
            return self.INDEX_POINT
        
        # Peace sign / Two fingers: Index and middle extended
        if fingers == [0, 1, 1, 0, 0]:
            return self.PEACE_SIGN
        
        # Open palm: All fingers extended
        if fingers == [1, 1, 1, 1, 1]:
            return self.OPEN_PALM
        
        # Closed fist: No fingers extended
        if fingers == [0, 0, 0, 0, 0]:
            return self.CLOSED_FIST
        
        return self.UNKNOWN
    
    def add_to_history(self, gesture):
        """Adds a gesture to history for smoothing."""
        self.gesture_history.append(gesture)
        if len(self.gesture_history) > self.history_size:
            self.gesture_history.pop(0)
    
    def get_stable_gesture(self):
        """
        Returns the most common gesture in recent history.
        This implements gesture smoothing to reduce jitter.
        """
        if not self.gesture_history:
            return self.UNKNOWN
        
        # Return most common gesture
        return max(set(self.gesture_history), key=self.gesture_history.count)


class SwipeDetector:
    """
    Detects swipe gestures with proper debouncing.
    HCI Feature: Prevents accidental triggers through motion analysis.
    """
    
    def __init__(self, swipe_threshold=0.3, debounce_time=1.0):
        """
        Args:
            swipe_threshold: Percentage of screen width to trigger swipe (0-1)
            debounce_time: Seconds to wait between swipes
        """
        self.swipe_threshold = swipe_threshold
        self.debounce_time = debounce_time
        self.is_tracking = False
        self.start_x = 0
        self.last_swipe_time = 0
        
    def detect(self, hand_x, frame_width, current_time):
        """
        Detects swipe gestures.
        
        Args:
            hand_x: Current X position of hand
            frame_width: Width of the frame
            current_time: Current time in seconds
            
        Returns:
            "swipe_right", "swipe_left", or None
        """
        # Check debounce
        if current_time - self.last_swipe_time < self.debounce_time:
            return None
        
        if not self.is_tracking:
            # Start tracking
            self.start_x = hand_x
            self.is_tracking = True
            return None
        
        # Calculate movement
        delta_x = hand_x - self.start_x
        threshold_pixels = frame_width * self.swipe_threshold
        
        result = None
        if delta_x > threshold_pixels:
            result = "swipe_right"
            self.last_swipe_time = current_time
            self.is_tracking = False
        elif delta_x < -threshold_pixels:
            result = "swipe_left"
            self.last_swipe_time = current_time
            self.is_tracking = False
        
        return result
    
    def reset(self):
        """Reset swipe tracking state."""
        self.is_tracking = False


