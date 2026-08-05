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
  const tubeGeometry = new THREE.TubeGeometry(curve, points.length * 2, 0.2, 4, false);

  return (
    <mesh geometry={tubeGeometry}>
      <meshBasicMaterial color="#39ff14" wireframe={true} />
    </mesh>
  );
}

function WelcomeScreen({ onEnter }: { onEnter: () => void }) {
  return (
    <div className="layout">
      {/* NAVBAR */}
      <nav className="navbar">
        <div className="nav-brand text-muted">
          &gt;_ OPEN5X_SLICER.EXE
        </div>
      </nav>

      {/* HERO SECTION */}
      <main className="hero" style={{ alignItems: 'center', textAlign: 'center' }}>
        <div className="accent-text">
          &gt; SYSTEM READY...
        </div>
        
        <h1 style={{ fontSize: '5rem', marginBottom: '40px' }}>WELCOME TO<br/>5 AXIS SLICER</h1>
        
        <div className="btn-group" style={{ justifyContent: 'center' }}>
          <button className="btn-primary" onClick={onEnter}>
            Enter Slicer Page
          </button>
          
          <button className="btn-secondary" onClick={() => alert("Destination TBD")}>
            [ Coming Soon ]
          </button>
        </div>
      </main>
    </div>
  );
}

function App() {
  const [hasEntered, setHasEntered] = useState(false);
  const [lineWidth, setLineWidth] = useState(0.4);
  const [bedCenterZ, setBedCenterZ] = useState(50.0);
  const [file, setFile] = useState<File | null>(null);
  
  const [isSlicing, setIsSlicing] = useState(false);
  const [toolpathPoints, setToolpathPoints] = useState([]);
  const [status, setStatus] = useState<string>('SYSTEM_READY');
  
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setFile(e.target.files[0]);
      setStatus(`LOADED: ${e.target.files[0].name}`);
    }
  };

  const handleSlice = async () => {
    if (!file) {
      setStatus('ERR: NO_FILE_SELECTED');
      return;
    }
    
    setIsSlicing(true);
    setStatus('PROCESSING_STL...');
    setToolpathPoints([]);
    
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("line_width", lineWidth.toString());
      formData.append("bed_center_z", bedCenterZ.toString());
      
      const apiUrl = import.meta.env.VITE_API_URL || '';
      const response = await axios.post(`${apiUrl}/slice_stl`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      
      const gcode = response.data.gcode;
      const points = response.data.toolpath_points;
      
      setToolpathPoints(points);
      setStatus(`SUCCESS: GENERATED ${points.length} POINTS`);
      
      const blob = new Blob([gcode], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${file.name.replace('.stl', '')}_open5x.gcode`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      
    } catch (error) {
      console.error("Failed to slice:", error);
      setStatus('ERR: SLICE_FAILED');
    } finally {
      setIsSlicing(false);
    }
  };

  if (!hasEntered) {
    return <WelcomeScreen onEnter={() => setHasEntered(true)} />;
  }

  return (
    <div className="layout">
      {/* NAVBAR */}
      <nav className="navbar">
        <div className="nav-brand text-muted">
          &gt;_ OPEN5X_SLICER.EXE
        </div>
        <button className="btn-secondary" onClick={() => window.location.reload()} style={{ padding: '8px 16px', fontSize: '14px' }}>
          [ RESTART_KERNEL ]
        </button>
      </nav>

      {/* HERO SECTION */}
      <main className="hero">
        <div className="accent-text">
          &gt; INITIALIZING GEOMETRY PROTOCOLS...
        </div>
        
        <h1>GENERATE 5-AXIS<br/>CONFORMAL TOOLPATHS</h1>
        
        <div className="controls-container">
          <p style={{ marginTop: 0, marginBottom: '20px' }}>
            Open5x Slicer brings your team together with powerful tools designed to seamlessly convert 3D meshes into 5-axis G-code for complex architectures.
          </p>
          
          <div className="input-row">
            <label>LINE WIDTH</label>
            <input 
              type="number" 
              className="terminal-input"
              step="0.05" 
              value={lineWidth} 
              onChange={e => setLineWidth(parseFloat(e.target.value))} 
            />
          </div>
          
          <div className="input-row">
            <label>BED CENTER Z</label>
            <input 
              type="number" 
              className="terminal-input"
              step="1" 
              value={bedCenterZ} 
              onChange={e => setBedCenterZ(parseFloat(e.target.value))} 
            />
          </div>
        </div>
        
        <div className="btn-group">
          <button className="btn-primary" onClick={handleSlice} disabled={isSlicing || !file}>
            {isSlicing ? 'Executing...' : 'Initiate Slicing'}
          </button>
          
          <label style={{ display: 'inline-block' }}>
            <span className="btn-secondary">
              [ {file ? file.name.substring(0, 15) + (file.name.length > 15 ? '...' : '') : "Upload STL"} ]
            </span>
            <input 
              type="file" 
              accept=".stl" 
              onChange={handleFileChange} 
              ref={fileInputRef}
              style={{ display: 'none' }}
            />
          </label>
        </div>
        
        <div className="status-text">
          STATUS: {status} <span className="cursor-blink"></span>
        </div>
      </main>

      {/* 3D VIEWER (BOTTOM GRID) */}
      <section className="viewer-section">
        <div>
          <div className="text-muted" style={{ fontSize: '12px' }}>GEOMETRY ENGINE</div>
          <div style={{ fontSize: '24px', fontWeight: 'bold' }}>{toolpathPoints.length > 0 ? 'ONLINE' : 'STANDBY'}</div>
        </div>
        <div>
          <div className="text-muted" style={{ fontSize: '12px' }}>TOOLPATH POINTS</div>
          <div style={{ fontSize: '24px', fontWeight: 'bold' }}>{toolpathPoints.length}</div>
        </div>
        <div>
          <div className="text-muted" style={{ fontSize: '12px' }}>OUTPUT FORMAT</div>
          <div style={{ fontSize: '24px', fontWeight: 'bold' }}>G-CODE</div>
        </div>
        
        <div className="viewer-wrapper">
          <Canvas camera={{ position: [40, 40, 40], up: [0, 0, 1] }}>
            <Grid infiniteGrid fadeDistance={100} sectionColor="#1f6b1f" cellColor="#090a09" />
            <Toolpath points={toolpathPoints} />
            <OrbitControls makeDefault />
          </Canvas>
        </div>
      </section>
    </div>
  );
}

export default App;
