# Open5x Slicer

An open-source, accessible conformal 5-axis 3D printing slicer. 
Built for the [Open5x](https://github.com/Open5x) hardware architecture, this project allows you to slice 3D models and generate 5-axis G-code with a stunning web interface.

## Architecture
- **Frontend**: A modern web interface built with React and Three.js for 3D visualization.
- **Backend**: A fast, Python-based API built with FastAPI, handling the geometry offsetting, toolpath generation, and inverse kinematics.

## Getting Started

### Backend
1. Navigate to the `backend` directory.
2. Install the requirements: `pip install -r requirements.txt`
3. Run the API server: `uvicorn api:app --reload`

### Frontend
1. Navigate to the `frontend` directory.
2. Install dependencies: `npm install`
3. Start the dev server: `npm run dev`

## License
This project is licensed under the MIT License.
