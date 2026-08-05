#!/bin/bash
cd "$(dirname "$0")"

# Start the backend API on port 8001
npx pm2 start "source venv/bin/activate && uvicorn api:app --reload --port 8001" --name "open5x-backend" --cwd ./backend

# Start the frontend dev server
npx pm2 start "npm run dev" --name "open5x-frontend" --cwd ./frontend

# Save pm2 state
npx pm2 save
npx pm2 list
