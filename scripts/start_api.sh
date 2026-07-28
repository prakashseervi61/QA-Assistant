#!/bin/bash
# Start FastAPI development server
uvicorn src.presentation.api.app:create_app --factory --reload --host 0.0.0.0 --port 8000
