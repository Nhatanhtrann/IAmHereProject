#!/bin/bash

# Build script for Render
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Build completed successfully!"