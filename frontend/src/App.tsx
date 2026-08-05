import { useState } from 'react';
import axios from 'axios';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Grid } from '@react-three/drei';
import * as THREE from 'three';
import './index.css';

function Toolpath({ points }: { points: {x: number, y: number, z: number}[] }) {
  if (!points || points.length === 0) return null;
  
  // Convert points to Vector3 array
  const vectorPoints = points.map(p => new THREE.Vector3(p.x, p.y, p.z));
  const curve = new THREE.CatmullRomCurve3(vectorPoints);
  // Get more points for a smoother tube
  const tubeGeometry = new THREE.TubeGeometry(curve, points.length * 2, 0.1, 8, false);

  return (
    <mesh geometry={tubeGeometry}>
      <meshStandardMaterial color="#00f2fe" />
    </mesh>
  );
}

function Substrate({ radius }: { radius: number }) {
  return (
    <mesh position={[0, 0, radius/2]} rotation={[Math.PI / 2, 0, 0]}>
      <cylinderGeometry args={[radius, radius, radius, 32, 1, false, 0, Math.PI]} />
      <meshStandardMaterial color="#30363d" transparent opacity={0.6} side={THREE.DoubleSide} />
    </mesh>
  );
}

function App() {
  const [radius, setRadius] = useState(20.0);
  const [lineWidth, setLineWidth] = useState(0.4);
  const [bedCenterZ, setBedCenterZ] = useState(50.0);
  const [isSlicing, setIsSlicing] = useState(false);
  const [toolpathPoints, setToolpathPoints] = useState([]);

  const handleSlice = async () => {
    setIsSlicing(true);
    try {
      const response = await axios.post('http://localhost:8000/slice', {
        radius,
        line_width: lineWidth,
        bed_center_z: bedCenterZ
      });
      
      const { gcode, toolpath_points } = response.data;
      setToolpathPoints(toolpath_points);
      
      // Trigger download
      const blob = new Blob([gcode], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'output.gcode';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      
    } catch (error) {
      console.error("Failed to slice:", error);
      alert("Failed to slice. Is the backend running?");
    } finally {
      setIsSlicing(false);
    }
  };

  return (
    <div className="app-container">
      <div className="sidebar">
        <h1>Open5x Slicer</h1>
        <p style={{ color: '#8b949e', fontSize: '0.9rem' }}>Conformal 5-Axis Slicer Web App</p>
        
        <div className="settings-group">
          <div className="input-field">
            <label>Hemisphere Radius (mm)</label>
            <input type="number" step="0.1" value={radius} onChange={e => setRadius(parseFloat(e.target.value))} />
          </div>
          
          <div className="input-field">
            <label>Line Width (mm)</label>
            <input type="number" step="0.05" value={lineWidth} onChange={e => setLineWidth(parseFloat(e.target.value))} />
          </div>
          
          <div className="input-field">
            <label>Bed Center Z (mm)</label>
            <input type="number" step="1" value={bedCenterZ} onChange={e => setBedCenterZ(parseFloat(e.target.value))} />
          </div>
        </div>
        
        <button onClick={handleSlice} disabled={isSlicing}>
          {isSlicing ? 'Slicing...' : 'Slice & Download G-Code'}
        </button>
      </div>
      
      <div className="viewer-container">
        <Canvas camera={{ position: [40, 40, 40], up: [0, 0, 1] }}>
          <ambientLight intensity={0.5} />
          <directionalLight position={[10, 10, 10]} intensity={1} />
          
          {/* Base Grid */}
          <Grid infiniteGrid fadeDistance={100} sectionColor="#4facfe" cellColor="#30363d" />
          
          {/* 3D Content */}
          <Substrate radius={radius} />
          <Toolpath points={toolpathPoints} />
          
          <OrbitControls makeDefault />
        </Canvas>
      </div>
    </div>
  );
}

export default App;
