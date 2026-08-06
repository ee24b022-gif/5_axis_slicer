import { useState, useRef, useMemo } from 'react';
import axios from 'axios';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Grid } from '@react-three/drei';
import * as THREE from 'three';
// @ts-ignore
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader';
import './index.css';

function StlModel({ geometry }: { geometry: THREE.BufferGeometry | null }) {
  if (!geometry) return null;
  return (
    <mesh geometry={geometry} castShadow receiveShadow>
      <meshStandardMaterial 
        color="#777777" 
        roughness={0.5}
        metalness={0.2}
      />
    </mesh>
  );
}

function Toolpath({ points, progress }: { points: {x: number, y: number, z: number}[], progress: number }) {
  if (!points || points.length < 2) return null;
  
  const pointCount = Math.max(2, Math.floor(points.length * (progress / 100)));
  const visiblePoints = points.slice(0, pointCount);
  
  const line = useMemo(() => {
    const positions = new Float32Array(visiblePoints.length * 3);
    for (let i = 0; i < visiblePoints.length; i++) {
      positions[i * 3] = visiblePoints[i].x;
      positions[i * 3 + 1] = visiblePoints[i].y;
      positions[i * 3 + 2] = visiblePoints[i].z;
    }
    const geom = new THREE.BufferGeometry();
    geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const material = new THREE.LineBasicMaterial({ color: 0x39ff14 });
    return new THREE.Line(geom, material);
  }, [visiblePoints]);

  return <primitive object={line} />;
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
  const [infill, setInfill] = useState(20);
  const [resolution, setResolution] = useState(1.0);
  const [file, setFile] = useState<File | null>(null);
  
  const [stlGeometry, setStlGeometry] = useState<THREE.BufferGeometry | null>(null);
  
  const [isSlicing, setIsSlicing] = useState(false);
  const [toolpathPoints, setToolpathPoints] = useState([]);
  const [gcodeData, setGcodeData] = useState<string | null>(null);
  const [previewProgress, setPreviewProgress] = useState(100);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [status, setStatus] = useState<string>('SYSTEM_READY');
  
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const selectedFile = e.target.files[0];
      setFile(selectedFile);
      setStatus(`LOADED: ${selectedFile.name}`);
      
      // Parse the STL file to display the model instantly
      const reader = new FileReader();
      reader.onload = (event) => {
        if (event.target && event.target.result) {
          try {
            const loader = new STLLoader();
            const geometry = loader.parse(event.target.result as ArrayBuffer);
            
            // Re-center geometry to match backend's bounding box centering
            geometry.computeBoundingBox();
            if (geometry.boundingBox) {
              const minB = geometry.boundingBox.min;
              const maxB = geometry.boundingBox.max;
              const centerX = (minB.x + maxB.x) / 2.0;
              const centerY = (minB.y + maxB.y) / 2.0;
              const minZ = minB.z;
              geometry.translate(-centerX, -centerY, -minZ);
            }
            
            setStlGeometry(geometry);
          } catch (err) {
            console.error("Error parsing STL", err);
            setStatus('ERR: INVALID_STL');
          }
        }
      };
      reader.readAsArrayBuffer(selectedFile);
    }
  };

  const handleSlice = async () => {
    if (!file) {
      setStatus('ERR: NO_FILE_SELECTED');
      return;
    }
    
    setIsSlicing(true);
    setStatus('UPLOADING_STL...');
    setUploadProgress(0);
    setToolpathPoints([]);
    setGcodeData(null);
    setPreviewProgress(100);
    
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("line_width", "0.4");
      formData.append("bed_center_z", "50.0");
      formData.append("resolution", resolution.toString());
      formData.append("infill", infill.toString());
      
      const apiUrl = import.meta.env.VITE_API_URL || '';
      const response = await axios.post(`${apiUrl}/slice_stl`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total) {
            const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            setUploadProgress(percent);
            if (percent === 100) setStatus('PROCESSING_STL...');
          }
        },
        onDownloadProgress: (progressEvent) => {
          if (progressEvent.total) {
            const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            setStatus(`DOWNLOADING_GCODE... ${percent}%`);
          } else {
            setStatus(`DOWNLOADING_GCODE... ${Math.round(progressEvent.loaded / 1024 / 1024)}MB`);
          }
        }
      });
      
      const gcode = response.data.gcode;
      const points = response.data.toolpath_points;
      
      setToolpathPoints(points);
      setGcodeData(gcode);
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
      
    } catch (error: any) {
      console.error("Failed to slice:", error);
      const errMsg = error.response?.data?.detail || 'SLICE_FAILED';
      setStatus(`ERR: ${errMsg.substring(0, 30)}`);
      alert(`Slicing failed: ${errMsg}`);
    } finally {
      setIsSlicing(false);
    }
  };

  if (!hasEntered) {
    return <WelcomeScreen onEnter={() => setHasEntered(true)} />;
  }

  const handleDownload = () => {
    if (!gcodeData || !file) return;
    const blob = new Blob([gcodeData], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${file.name.replace('.stl', '')}_open5x.gcode`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

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
              <label>INFILL DENSITY (%)</label>
              <input 
                type="number" 
                className="terminal-input"
                step="5" 
                min="0"
                max="100"
                value={infill} 
                onChange={e => setInfill(parseInt(e.target.value))} 
              />
            </div>
            
            <div className="input-row">
              <label>Y-STEP RESOLUTION (mm)</label>
              <input 
                type="number" 
                className="terminal-input"
                step="0.1" 
                value={resolution} 
                onChange={e => setResolution(parseFloat(e.target.value))} 
              />
            </div>
            
            {toolpathPoints.length > 0 && (
              <div className="input-row" style={{ marginTop: '20px' }}>
                <label>PREVIEW PROGRESS: {previewProgress}%</label>
                <input 
                  type="range" 
                  min="0" 
                  max="100" 
                  value={previewProgress} 
                  onChange={e => setPreviewProgress(parseInt(e.target.value))}
                  className="terminal-slider"
                />
              </div>
            )}
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
            
            {isSlicing && uploadProgress < 100 && (
              <div style={{ marginTop: '10px', width: '100%', height: '10px', backgroundColor: '#111', border: '1px solid #1f6b1f' }}>
                <div style={{ height: '100%', backgroundColor: '#39ff14', width: `${uploadProgress}%`, transition: 'width 0.2s' }}></div>
              </div>
            )}
            
            <button className="btn-primary" onClick={handleSlice} disabled={isSlicing || !file}>
              {isSlicing ? (uploadProgress < 100 ? `Uploading ${uploadProgress}%...` : 'Executing C++ Engine...') : 'Initiate Slicing'}
            </button>
            
            {gcodeData && (
              <button 
                className="btn-secondary" 
                onClick={handleDownload} 
                style={{ marginTop: '10px', width: '100%', borderColor: '#39ff14', color: '#39ff14' }}
              >
                [ Download G-Code ]
              </button>
            )}
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
          <Canvas shadows camera={{ position: [0, -80, 15], up: [0, 0, 1], fov: 50 }}>
            {/* 3-Point Lighting Setup */}
            <ambientLight intensity={0.3} />
            <directionalLight position={[20, 20, 30]} intensity={1.5} castShadow shadow-mapSize={[1024, 1024]} />
            <directionalLight position={[-20, -20, 10]} intensity={0.5} />
            
            <Grid infiniteGrid fadeDistance={100} sectionColor="#1f6b1f" cellColor="transparent" />
            
            {/* Shadow Catching Floor at Z=0 */}
            <mesh position={[0, 0, -0.1]} receiveShadow>
              <planeGeometry args={[200, 200]} />
              <shadowMaterial opacity={0.4} />
            </mesh>
            
            {/* Render uploaded STL Model */}
            <StlModel geometry={stlGeometry} />
            
            {/* Render Toolpath with progress slider */}
            <Toolpath points={toolpathPoints} progress={previewProgress} />
            
            <OrbitControls makeDefault />
          </Canvas>
        </main>
      </div>
    </div>
  );
}

export default App;
