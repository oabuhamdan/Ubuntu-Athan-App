#!/usr/bin/env python3
"""
Athan Daemon - Background Service

This script runs the background Athan service that:
- Schedules and plays Athan at correct times
- Runs independently of the UI
- Exposes D-Bus interface for communication
- Handles system sleep/resume
"""

import os
import sys
import logging

# Add package to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from athan.service.daemon import run_daemon
from athan.utils.helpers import setup_logging, get_data_dir


def main():
    """Main entry point for the daemon."""
    # Set up logging
    log_file = os.path.join(get_data_dir(), 'logs', 'daemon.log')
    
    # Ensure log directory exists
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    setup_logging('athan.daemon', logging.INFO, log_file)
    
    logging.info("Starting Athan daemon")
    
    return run_daemon()


if __name__ == '__main__':
    sys.exit(main())
