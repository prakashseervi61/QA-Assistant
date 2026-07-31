#!/bin/bash
# Start both FastAPI and React Vite servers

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Starting FastAPI server..."
(cd "$PROJECT_ROOT" && uvicorn src.presentation.api.app:create_app --factory --reload --host 0.0.0.0 --port 8000) &
API_PID=$!

echo "Starting React Vite frontend..."
(cd "$PROJECT_ROOT/src/presentation/react" && npm run dev) &
FRONTEND_PID=$!

echo "Servers started!"
echo "API: http://localhost:8000"
echo "Frontend: http://localhost:3000"
echo "API Docs: http://localhost:8000/docs"

# Wait for both processes
wait $API_PID $FRONTEND_PID