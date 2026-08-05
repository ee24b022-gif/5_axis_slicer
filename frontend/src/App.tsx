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
    <div className="welcome-layout">
      <nav className="welcome-navbar">
        <div className="text-muted" style={{ fontWeight: 700 }}>
          &gt;_ OPEN5X_SLICER.EXE
        </div>
      </nav>

      <main className="welcome-hero">
        <div className="accent-text">
          &gt; SYSTEM READY...
        </div>
        
        <h1 className="welcome-title">WELCOME TO<br/>5 AXIS SLICER</h1>
        
        <div className="welcome-btn-group">
          <button className="btn-primary" onClick={onEnter} style={{ width: 'auto' }}>
            Enter Slicer Page
          </button>
          
          <button className="btn-secondary" onClick={() => alert("Destination TBD")} style={{ width: 'auto' }}>
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
      setStatus(`SUCCESS: GENERATED ${points.length} Pts`);
      
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
    <div className="app-container">
      {/* TOP BAR */}
      <header className="topbar">
        <div className="text-muted" style={{ fontWeight: 700 }}>
          &gt;_ OPEN5X_SLICER.EXE
        </div>
        <button className="btn-secondary" onClick={() => setHasEntered(false)} style={{ padding: '8px 16px', fontSize: '14px', width: 'auto' }}>
          [ EXIT_SLICER ]
        </button>
      </header>

      <div className="main-content">
        {/* SIDEBAR */}
        <aside className="sidebar">
          <div className="accent-text" style={{ marginBottom: '10px' }}>
            &gt; CONFIGURE SLICER
          </div>
          
          <div className="controls-container">
            <div className="input-row">
              <label>LINE WIDTH (mm)</label>
              <input 
                type="number" 
                className="terminal-input"
                step="0.05" 
                value={lineWidth} 
                onChange={e => setLineWidth(parseFloat(e.target.value))} 
              />
            </div>
            
            <div className="input-row">
              <label>BED CENTER Z (mm)</label>
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
            <label style={{ display: 'block', width: '100%' }}>
              <div className="btn-secondary" style={{ width: '100%' }}>
                [ {file ? file.name.substring(0, 20) + (file.name.length > 20 ? '...' : '') : "Upload STL"} ]
              </div>
              <input 
                type="file" 
                accept=".stl" 
                onChange={handleFileChange} 
                ref={fileInputRef}
                style={{ display: 'none' }}
              />
            </label>
            
            <button className="btn-primary" onClick={handleSlice} disabled={isSlicing || !file}>
              {isSlicing ? 'Executing...' : 'Initiate Slicing'}
            </button>
          </div>
          
          <div style={{ marginTop: '30px', borderTop: '1px solid rgba(31,107,31,0.4)', paddingTop: '20px' }}>
            <div className="stat-box">
              <div className="text-muted" style={{ fontSize: '12px' }}>GEOMETRY ENGINE</div>
              <div style={{ fontSize: '18px', fontWeight: 'bold' }}>{toolpathPoints.length > 0 ? 'ONLINE' : 'STANDBY'}</div>
            </div>
            <div className="stat-box">
              <div className="text-muted" style={{ fontSize: '12px' }}>TOOLPATH POINTS</div>
              <div style={{ fontSize: '18px', fontWeight: 'bold' }}>{toolpathPoints.length}</div>
            </div>
          </div>

          <div className="status-text">
            STATUS: {status} <span className="cursor-blink"></span>
          </div>
        </aside>

        {/* MAIN CANVAS */}
        <main className="canvas-area">
          <Canvas camera={{ position: [40, 40, 40], up: [0, 0, 1] }}>
            {/* Darker grid to fade into background */}
            <Grid infiniteGrid fadeDistance={100} sectionColor="#1f6b1f" cellColor="transparent" />
            <Toolpath points={toolpathPoints} />
            <OrbitControls makeDefault />
          </Canvas>
        </main>
      </div>
    </div>
  );
}

export default App;
