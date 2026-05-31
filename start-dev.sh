#!/bin/bash
# Vider development server startup script
# Starts both backend (FastAPI) and frontend (Vite) concurrently

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}═══════════════════════════════════════${NC}"
echo -e "${BLUE}  Vider Development Server${NC}"
echo -e "${BLUE}═══════════════════════════════════════${NC}"

# Function to cleanup on exit
cleanup() {
    echo -e "\n${RED}Stopping servers...${NC}"
    jobs -p | xargs -r kill 2>/dev/null || true
    wait 2>/dev/null || true
    echo -e "${RED}Done${NC}"
}

trap cleanup EXIT INT TERM

# Start backend
echo -e "\n${GREEN}Starting backend (FastAPI)...${NC}"
(
    cd "$BACKEND_DIR"
    echo "Backend running at http://localhost:8000"
    uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
) &
BACKEND_PID=$!

# Small delay to ensure backend starts first
sleep 2

# Start frontend
echo -e "${GREEN}Starting frontend (Vite)...${NC}"
(
    cd "$FRONTEND_DIR"
    echo "Frontend running at http://localhost:5173"
    npm run dev
) &
FRONTEND_PID=$!

echo -e "\n${GREEN}═══════════════════════════════════════${NC}"
echo -e "${GREEN}Both servers are running!${NC}"
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo ""
echo -e "Backend:  ${BLUE}http://localhost:8000${NC}"
echo -e "Frontend: ${BLUE}http://localhost:5173${NC}"
echo -e "API Docs: ${BLUE}http://localhost:8000/docs${NC}"
echo ""
echo "Press Ctrl+C to stop both servers"
echo ""

# Wait for both processes
wait $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
