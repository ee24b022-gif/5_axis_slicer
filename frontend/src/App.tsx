import { useState, useEffect, useRef } from 'react';
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
      <meshBasicMaterial color="#33ff00" wireframe={true} />
    </mesh>
  );
}

function WelcomeScreen({ onEnter }: { onEnter: () => void }) {
  const [lines, setLines] = useState<string[]>([]);
  const fullText = [
    "INITIALIZING OPEN5X SLICING ENGINE...",
    "LOADING GEOMETRY KERNEL... [OK]",
    "CALIBRATING 5-AXIS KINEMATICS... [OK]",
    "ESTABLISHING U-V BED ROTATION MATRIX... [OK]",
    "READY."
  ];

  useEffect(() => {
    let currentLine = 0;
    const interval = setInterval(() => {
      if (currentLine < fullText.length) {
        setLines(prev => [...prev, fullText[currentLine]]);
        currentLine++;
      } else {
        clearInterval(interval);
      }
    }, 400);
    return () => clearInterval(interval);
  }, []);

  return (
    <div style={{ padding: '40px', display: 'flex', flexDirection: 'column', justifyContent: 'center', height: '100vh', width: '100vw' }}>
      <pre className="ascii-art" style={{ textAlign: 'left', marginBottom: '40px', fontSize: '20px', margin: '0 0 40px 0' }}>
{`  ___                   ___       
 / _ \\ _ __  ___ _ __  | __|_  __ 
| (_) | '_ \\/ -_) ' \\  |__ \\ \\/ / 
 \\___/| .__/\\___|_||_| |___/\\  /  
      |_|                   /_/   `}
      </pre>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '40px' }}>
        {lines.map((line, i) => <div key={i}>{line}</div>)}
        {lines.length === fullText.length && (
          <div><span className="cursor-blink"></span></div>
        )}
      </div>
      
      {lines.length === fullText.length && (
        <button className="terminal-btn" style={{ fontSize: '32px' }} onClick={onEnter}>
          [ INITIATE_HACK_SEQUENCE ]
        </button>
      )}
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
      {/* LEFT PANE - COMMAND LINE */}
      <div className="pane sidebar">
        <pre className="ascii-art">
{`  ___                   ___       
 / _ \\ _ __  ___ _ __  | __|_  __ 
| (_) | '_ \\/ -_) ' \\  |__ \\ \\/ / 
 \\___/| .__/\\___|_||_| |___/\\  /  
      |_|                   /_/   
SLICER v1.0.0`}
        </pre>

        <div>
          <div className="terminal-prompt">
            <span className="prompt-symbol">open5x@local:~$</span>
            <div>{status}<span className="cursor-blink"></span></div>
          </div>
        </div>

        <div style={{ marginTop: '20px' }}>
          <div className="terminal-prompt">
            <div className="prompt-line">
              <span className="prompt-symbol">&gt;</span>
              <span>SELECT_TARGET_STL</span>
            </div>
            <label className="file-upload-label">
              [ {file ? file.name : "BROWSE_FILES"} ]
              <input 
                type="file" 
                accept=".stl" 
                onChange={handleFileChange} 
                ref={fileInputRef}
              />
            </label>
          </div>
          
          <div className="terminal-prompt" style={{ marginTop: '10px' }}>
            <div className="prompt-line">
              <span className="prompt-symbol">&gt;</span>
              <span>SET_LINE_WIDTH</span>
            </div>
            <div className="prompt-line">
              <span className="prompt-symbol" style={{ visibility: 'hidden'}}>&gt;</span>
              <input 
                type="number" 
                step="0.05" 
                value={lineWidth} 
                onChange={e => setLineWidth(parseFloat(e.target.value))} 
              />
            </div>
          </div>
          
          <div className="terminal-prompt" style={{ marginTop: '10px' }}>
            <div className="prompt-line">
              <span className="prompt-symbol">&gt;</span>
              <span>SET_BED_CENTER_Z</span>
            </div>
            <div className="prompt-line">
              <span className="prompt-symbol" style={{ visibility: 'hidden'}}>&gt;</span>
              <input 
                type="number" 
                step="1" 
                value={bedCenterZ} 
                onChange={e => setBedCenterZ(parseFloat(e.target.value))} 
              />
            </div>
          </div>
        </div>
        
        <button className="terminal-btn" onClick={handleSlice} disabled={isSlicing || !file}>
          [ {isSlicing ? 'EXECUTING...' : 'INITIATE_SLICING'} ]
        </button>
      </div>
      
      {/* RIGHT PANE - VISUALIZER */}
      <div className="pane viewer-pane">
        <div className="pane-header">
          +--- 3D_VIEWPORT_STREAM ---+
        </div>
        <div className="canvas-wrapper">
          <Canvas camera={{ position: [40, 40, 40], up: [0, 0, 1] }}>
            <Grid infiniteGrid fadeDistance={100} sectionColor="#1f521f" cellColor="#0a0a0a" />
            <Toolpath points={toolpathPoints} />
            <OrbitControls makeDefault />
          </Canvas>
        </div>
      </div>
    </div>
  );
}

export default App;
