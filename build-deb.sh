#!/bin/bash
#
# Build script for Athan App .deb package
#
# This script creates a Debian package from the source.
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Athan App - Debian Package Builder${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check for required tools
echo -e "${YELLOW}Checking build dependencies...${NC}"

MISSING_DEPS=""

if ! command -v dpkg-buildpackage &> /dev/null; then
    MISSING_DEPS="$MISSING_DEPS dpkg-dev"
fi

if ! command -v dh &> /dev/null; then
    MISSING_DEPS="$MISSING_DEPS debhelper"
fi

if ! command -v dh_python3 &> /dev/null; then
    MISSING_DEPS="$MISSING_DEPS dh-python"
fi

if [ -n "$MISSING_DEPS" ]; then
    echo -e "${RED}Missing dependencies:${NC}$MISSING_DEPS"
    echo ""
    echo "Install them with:"
    echo "  sudo apt-get install$MISSING_DEPS"
    exit 1
fi

echo -e "${GREEN}All build dependencies satisfied.${NC}"
echo ""

# Get version from changelog
VERSION=$(dpkg-parsechangelog -S Version 2>/dev/null || echo "1.0.0-1")
echo -e "${YELLOW}Building version: ${VERSION}${NC}"
echo ""

# Clean previous builds
echo -e "${YELLOW}Cleaning previous builds...${NC}"
rm -rf debian/.debhelper debian/athan-app debian/files debian/*.substvars debian/*.debhelper.log 2>/dev/null || true
rm -f ../athan-app_*.deb ../athan-app_*.changes ../athan-app_*.buildinfo 2>/dev/null || true

# Make scripts executable
chmod +x athan-ui.py athan-daemon.py 2>/dev/null || true
chmod +x debian/rules 2>/dev/null || true
chmod +x debian/postinst debian/prerm 2>/dev/null || true

# Build the package
echo -e "${YELLOW}Building package...${NC}"
echo ""

dpkg-buildpackage -us -uc -b

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Build completed successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Find and display the built package
DEB_FILE=$(ls ../athan-app_*.deb 2>/dev/null | head -1)

if [ -n "$DEB_FILE" ]; then
    echo -e "Package created: ${GREEN}${DEB_FILE}${NC}"
    echo ""
    echo "To install:"
    echo "  sudo dpkg -i ${DEB_FILE}"
    echo "  sudo apt-get install -f  # Install any missing dependencies"
    echo ""
    echo "Package info:"
    dpkg-deb --info "$DEB_FILE" | head -20
else
    echo -e "${RED}Warning: Could not find built .deb file${NC}"
fi
