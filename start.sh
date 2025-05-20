#!/bin/bash

# Start script for Render
echo "Starting the application..."

# Download required models (if not cached)
python -c "
from transformers import AutoTokenizer, AutoModel
print('Downloading PhoBERT model...')
AutoTokenizer.from_pretrained('vinai/phobert-base')
AutoModel.from_pretrained('vinai/phobert-base')
print('Models downloaded successfully!')
"

# Start the application with gunicorn
exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --timeout 120 --keep-alive 2 ai_service:app