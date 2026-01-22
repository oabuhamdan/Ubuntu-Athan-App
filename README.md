# Athan App - Ubuntu Prayer Times Application

A production-ready Ubuntu GNOME desktop application for Islamic prayer times (Athan).

## Features

- **Accurate Prayer Times**: Calculates all five daily prayer times using the ISNA method
- **Top Panel Indicator**: Persistent indicator showing next prayer and countdown
- **Background Service**: Reliable daemon that plays Athan even when UI is closed
- **Audio Device Selection**: Choose specific audio output for Athan playback
- **Location Settings**: City search or manual coordinates input
- **Auto-Relaunch**: Configurable auto-restart after X minutes
- **System Integration**: Proper systemd user service, survives sleep/resume

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     User Interface (GTK)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ Main Window  │  │   Settings   │  │  Panel Indicator │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │ D-Bus
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Background Service (Daemon)                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │  Scheduler   │  │ Audio Player │  │ Prayer Calculator │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Installation

### From .deb Package (Recommended)

```bash
sudo dpkg -i athan-app_1.0.0_all.deb
sudo apt-get install -f  # Install dependencies if needed
```

### From Source

```bash
# Install dependencies
sudo apt-get install python3 python3-gi python3-gi-cairo \
    gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1 \
    gstreamer1.0-tools gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good python3-gst-1.0 \
    python3-dbus python3-pip

# Install Python dependencies
pip3 install --user -r requirements.txt

# Run the application
./athan-ui.py
```

## Building .deb Package

```bash
# Install build dependencies
sudo apt-get install dpkg-dev debhelper dh-python

# Build the package
dpkg-buildpackage -us -uc -b

# Or use the build script
./build-deb.sh
```

## Usage

### Starting the Application

- **From Applications Menu**: Search for "Athan" and click
- **From Terminal**: `athan-app` or `athan-ui`

### Background Service

The background service starts automatically and continues running when the UI is closed.

```bash
# Check service status
systemctl --user status athan-daemon

# Restart service
systemctl --user restart athan-daemon

# View logs
journalctl --user -u athan-daemon -f
```

### Configuration

Settings are stored in `~/.config/athan-app/config.json`:

- Calculation method and parameters
- Location coordinates
- Audio device and file selection
- Auto-relaunch settings

## File Locations

- Configuration: `~/.config/athan-app/config.json`
- Custom Athan audio: `~/.local/share/athan-app/sounds/`
- Logs: `~/.local/share/athan-app/logs/`
- Default sounds: `/usr/share/athan-app/sounds/`

## Requirements

- Ubuntu 20.04+ (GNOME Desktop)
- Python 3.8+
- GTK 3.0
- GStreamer 1.0
- libayatana-appindicator3

## License

MIT License - See LICENSE file for details.

## Contributing

Contributions are welcome! Please read the contributing guidelines before submitting pull requests.
