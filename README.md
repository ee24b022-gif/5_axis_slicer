# Open5x Slicer

An open-source, accessible conformal 5-axis 3D printing slicer. 
Built for the [Open5x](https://github.com/Open5x) hardware architecture, this project allows you to slice 3D models and generate 5-axis G-code with a stunning web interface.

## Architecture
- **Frontend**: A modern web interface built with React and Three.js for 3D visualization.
- **Backend**: A fast, Python-based API built with FastAPI, handling the geometry offsetting, toolpath generation, and inverse kinematics.

## Getting Started

### Local Development
We provide a `Makefile` to simplify local development.

1. Install dependencies for both frontend and backend:
   ```bash
   make install
   ```
2. Start the development servers (requires pm2):
   ```bash
   make dev
   ```

The backend API will run on port 8001 and the frontend will run on its default Vite port.

### Manual Setup
If you prefer not to use the Makefile:
- **Backend**: `cd backend && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt && uvicorn api:app --reload`
- **Frontend**: `cd frontend && npm install && npm run dev`

## License
This project is licensed under the MIT License.
