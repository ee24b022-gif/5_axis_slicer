import { useState, useRef } from 'react';
import axios from 'axios';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Grid } from '@react-three/drei';
import * as THREE from 'three';
import './index.css';

function Toolpath({ points }: { points: {x: number, y: number, z: number}[] }) {
  if (!points || points.length === 0) return null;
  
  const vectorPoints = points.map(p => new THREE.Vector3(p.x, p.y, p.z));
  const curve = new THREE.CatmullRomCurve3(vectorPoints);
  const tubeGeometry = new THREE.TubeGeometry(curve, points.length * 2, 0.2, 8, false);

  return (
    <mesh geometry={tubeGeometry}>
      <meshStandardMaterial color="#00f2fe" />
    </mesh>
  );
}

function App() {
  const [mode, setMode] = useState<'hemisphere' | 'stl'>('hemisphere');
  
  // Params
  const [radius, setRadius] = useState(20.0);
  const [lineWidth, setLineWidth] = useState(0.4);
  const [bedCenterZ, setBedCenterZ] = useState(50.0);
  const [file, setFile] = useState<File | null>(null);
  
  // State
  const [isSlicing, setIsSlicing] = useState(false);
  const [toolpathPoints, setToolpathPoints] = useState([]);
  
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setFile(e.target.files[0]);
    }
  };

  const handleSlice = async () => {
    setIsSlicing(true);
    setToolpathPoints([]);
    try {
      let gcode = "";
      let points = [];
      
      if (mode === 'hemisphere') {
        const response = await axios.post('http://localhost:8001/slice', {
          radius,
          line_width: lineWidth,
          bed_center_z: bedCenterZ
        });
        gcode = response.data.gcode;
        points = response.data.toolpath_points;
      } else {
        if (!file) {
          alert("Please select an STL file first.");
          setIsSlicing(false);
          return;
        }
        const formData = new FormData();
        formData.append("file", file);
        formData.append("line_width", lineWidth.toString());
        formData.append("bed_center_z", bedCenterZ.toString());
        
        const response = await axios.post('http://localhost:8001/slice_stl', formData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        });
        gcode = response.data.gcode;
        points = response.data.toolpath_points;
      }
      
      setToolpathPoints(points);
      
      // Trigger download
      const blob = new Blob([gcode], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = mode === 'stl' && file ? `${file.name}.gcode` : 'output.gcode';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      
    } catch (error) {
      console.error("Failed to slice:", error);
      alert("Failed to slice. Ensure the backend is running and the file is valid.");
    } finally {
      setIsSlicing(false);
    }
  };

  return (
    <div className="app-container">
      <div className="sidebar">
        <h1>Open5x Slicer</h1>
        <p style={{ color: '#8b949e', fontSize: '0.9rem' }}>Conformal 5-Axis Slicer Web App</p>
        
        <div style={{ display: 'flex', gap: '10px', marginTop: '1rem' }}>
          <button 
            style={{ flex: 1, background: mode === 'hemisphere' ? '#2ea043' : '#21262d', filter: 'none', border: mode === 'hemisphere' ? 'none' : '1px solid #30363d' }}
            onClick={() => setMode('hemisphere')}
          >
            Hemisphere
          </button>
          <button 
            style={{ flex: 1, background: mode === 'stl' ? '#2ea043' : '#21262d', filter: 'none', border: mode === 'stl' ? 'none' : '1px solid #30363d' }}
            onClick={() => setMode('stl')}
          >
            Custom STL
          </button>
        </div>

        <div className="settings-group">
          {mode === 'hemisphere' ? (
            <div className="input-field">
              <label>Hemisphere Radius (mm)</label>
              <input type="number" step="0.1" value={radius} onChange={e => setRadius(parseFloat(e.target.value))} />
            </div>
          ) : (
            <div className="input-field">
              <label>Upload STL File</label>
              <input 
                type="file" 
                accept=".stl" 
                onChange={handleFileChange} 
                ref={fileInputRef}
                style={{ padding: '0.5rem', cursor: 'pointer' }}
              />
            </div>
          )}
          
          <div className="input-field">
            <label>Line Width (mm)</label>
            <input type="number" step="0.05" value={lineWidth} onChange={e => setLineWidth(parseFloat(e.target.value))} />
          </div>
          
          <div className="input-field">
            <label>Bed Center Z (mm)</label>
            <input type="number" step="1" value={bedCenterZ} onChange={e => setBedCenterZ(parseFloat(e.target.value))} />
          </div>
        </div>
        
        <button onClick={handleSlice} disabled={isSlicing || (mode === 'stl' && !file)} style={{ marginTop: '2rem' }}>
          {isSlicing ? 'Slicing...' : 'Slice & Download G-Code'}
        </button>
      </div>
      
      <div className="viewer-container">
        <Canvas camera={{ position: [40, 40, 40], up: [0, 0, 1] }}>
          <ambientLight intensity={0.5} />
          <directionalLight position={[10, 10, 10]} intensity={1} />
          <Grid infiniteGrid fadeDistance={100} sectionColor="#4facfe" cellColor="#30363d" />
          
          <Toolpath points={toolpathPoints} />
          <OrbitControls makeDefault />
        </Canvas>
      </div>
    </div>
  );
}

export default App;
