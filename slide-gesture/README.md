# Aura - Gesture Presentation Control

Gesture-based presentation control system using MediaPipe hand tracking.

## Quick Start

### Mode 1: Universal Desktop Controller
```bash
run_mode1.bat
```

**NEW: Overlay Mode** 🎯
Mode 1 now features an overlay window that stays on top of other applications while being click-through, allowing you to control presentations without blocking your view or interaction with other apps!

To enable overlay mode on Windows:
```bash
install_pywin32.bat
```

Features:
- ✅ Window stays always on top
- ✅ Click-through (doesn't block mouse interactions with other apps)
- ✅ Semi-transparent (configurable opacity)
- ✅ Non-intrusive gesture control

### Mode 2: Web Application
Terminal 1:
```bash
run_mode2_react_backend.bat
```

Terminal 2:
```bash
cd react-frontend
npm install
npm run dev
```

## Configuration (Mode 1 Overlay)

Edit `gesture_controller.py` to customize overlay behavior:

```python
ENABLE_OVERLAY_MODE = True  # Toggle overlay mode on/off
OVERLAY_OPACITY = 0.85      # Transparency (0.0-1.0, 0.7-0.9 recommended)
```

**How it works:**
- Window stays always on top of other apps
- Mouse clicks pass through to underlying applications
- You can interact with your presentation software while seeing gesture feedback
- Windows only (requires pywin32)

**Troubleshooting:**
- If overlay doesn't activate: Run `install_pywin32.bat`
- If window is too transparent: Increase `OVERLAY_OPACITY` (try 0.9)
- If window is distracting: Decrease `OVERLAY_OPACITY` (try 0.7)
- To disable: Set `ENABLE_OVERLAY_MODE = False`

## Requirements
- Python 3.10 or 3.11
- Node.js (for Mode 2)
- pywin32>=306 (for Windows overlay mode)

## Installation
```bash
install_dependencies.bat
```

For overlay mode support (Windows):
```bash
install_pywin32.bat
```

