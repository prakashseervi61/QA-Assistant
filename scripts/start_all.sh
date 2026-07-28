#!/bin/bash
# Start both FastAPI and Streamlit servers

echo "Starting FastAPI server..."
uvicorn src.presentation.api.app:create_app --factory --reload --host 0.0.0.0 --port 8000 &
API_PID=$!

echo "Starting Streamlit server..."
streamlit run src/presentation/streamlit/app.py --server.port 8501 &
STREAMLIT_PID=$!

echo "Servers started!"
echo "API: http://localhost:8000"
echo "Streamlit: http://localhost:8501"
echo "API Docs: http://localhost:8000/docs"

# Wait for both processes
wait $API_PID $STREAMLIT_PID
