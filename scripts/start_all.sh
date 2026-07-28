#!/bin/bash
# Start both FastAPI and React Vite servers

echo "Starting FastAPI server..."
uvicorn src.presentation.api.app:create_app --factory --reload --host 0.0.0.0 --port 8000 &
API_PID=$!

echo "Starting React Vite frontend..."
cd src/presentation/react
npm run dev &
FRONTEND_PID=$!
cd ../../..

echo "Servers started!"
echo "API: http://localhost:8000"
echo "Frontend: http://localhost:3000"
echo "API Docs: http://localhost:8000/docs"

# Wait for both processes
wait $API_PID $FRONTEND_PID