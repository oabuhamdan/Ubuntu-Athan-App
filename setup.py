#!/usr/bin/env python3
"""
Setup script for Athan App
"""

from setuptools import setup, find_packages
import os

# Read README for long description
readme_path = os.path.join(os.path.dirname(__file__), 'README.md')
if os.path.exists(readme_path):
    with open(readme_path, 'r', encoding='utf-8') as f:
        long_description = f.read()
else:
    long_description = "Islamic Prayer Times and Athan Notification"

setup(
    name='athan-app',
    version='1.0.0',
    author='Athan App Team',
    author_email='contact@athanapp.com',
    description='Islamic Prayer Times and Athan Notification',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/athan-app/athan-app',
    packages=find_packages(),
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: X11 Applications :: GTK',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: MIT License',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Topic :: Desktop Environment :: Gnome',
        'Topic :: Religion',
    ],
    python_requires='>=3.8',
    install_requires=[
        'pytz>=2023.3',
        'python-dateutil>=2.8.2',
    ],
    extras_require={
        'geolocation': ['geopy>=2.3.0'],
    },
    entry_points={
        'console_scripts': [
            'athan-app=athan_ui:main',
            'athan-daemon=athan_daemon:main',
        ],
    },
    data_files=[
        ('share/applications', ['data/athan-app.desktop']),
        ('share/icons/hicolor/scalable/apps', ['data/icons/athan-app.svg']),
        ('share/dbus-1/services', ['data/com.athanapp.AthanService.service']),
        ('lib/systemd/user', ['data/athan-daemon.service']),
        ('/etc/xdg/autostart', ['data/athan-app-autostart.desktop']),
    ],
    include_package_data=True,
)
