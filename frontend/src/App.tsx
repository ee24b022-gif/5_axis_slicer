import { useState, useRef, useMemo } from 'react';
import axios from 'axios';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, TransformControls } from '@react-three/drei';
import * as THREE from 'three';
// @ts-ignore
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader';
import './index.css';

function CameraResetter({ isResetting, setIsResetting, controlsRef }: any) {
  useFrame((state, delta) => {
    if (isResetting && controlsRef.current) {
      const targetPos = new THREE.Vector3(0, -80, 15);
      const targetLook = new THREE.Vector3(0, 0, 0);
      
      const lerpFactor = delta * 1.5; // Slower factor for a smooth cinematic glide
      
      state.camera.position.lerp(targetPos, lerpFactor);
      controlsRef.current.target.lerp(targetLook, lerpFactor);
      controlsRef.current.update();
      
      if (state.camera.position.distanceTo(targetPos) < 0.2 && controlsRef.current.target.distanceTo(targetLook) < 0.2) {
        state.camera.position.copy(targetPos);
        controlsRef.current.target.copy(targetLook);
        controlsRef.current.update();
        setIsResetting(false);
      }
    }
  });
  return null;
}

function StlModel({ geometry, modelScale, rotX, rotY, rotZ, posX, posY }: any) {
  if (!geometry) return null;
  
  const transformedGeometry = useMemo(() => {
    const geom = geometry.clone();
    geom.scale(modelScale, modelScale, modelScale);
    geom.rotateX(rotX * Math.PI / 180);
    geom.rotateY(rotY * Math.PI / 180);
    geom.rotateZ(rotZ * Math.PI / 180);
    geom.computeBoundingBox();
    if (geom.boundingBox) {
      geom.translate(posX, posY, -geom.boundingBox.min.z);
    }
    return geom;
  }, [geometry, modelScale, rotX, rotY, rotZ, posX, posY]);

  return (
    <mesh geometry={transformedGeometry} castShadow receiveShadow>
      <meshStandardMaterial 
        color="#777777" 
        roughness={0.5}
        metalness={0.2}
        transparent={true}
        opacity={0.3}
      />
    </mesh>
  );
}

function Toolpath({ points, progress, maxVisibleLayer, isolateLayer }: { points: any, progress: number, maxVisibleLayer: number, isolateLayer: boolean }) {
  if (!points || !points.x || points.x.length < 2) return null;
  
  const totalPoints = points.x.length;
  const pointCount = Math.max(2, Math.floor(totalPoints * (progress / 100)));
  
  const lineGeometries = useMemo(() => {
    const groups: Record<string, number[]> = {};
    const colors = [0xffff00, 0x00ff00, 0x00ffff, 0x1e90ff, 0xff00ff, 0xff4500];
    
    let currentType = '';
    let currentLayer = -1;
    let startIdx = -1;
    
    const addSegment = (start: number, end: number, type: string, layer: number) => {
      if (end - start < 1) return;
      const groupKey = type === 'infill' ? 'infill' : `perimeter_${layer % colors.length}`;
      if (!groups[groupKey]) groups[groupKey] = [];
      
      const arr = groups[groupKey];
      for (let i = start; i < end; i++) {
        arr.push(points.x[i], points.y[i], points.z[i], points.x[i+1], points.y[i+1], points.z[i+1]);
      }
    };
    
    for (let i = 0; i < pointCount; i++) {
      const layer = points.layer[i];
      const isVisible = isolateLayer ? layer === maxVisibleLayer : layer <= maxVisibleLayer;
      
      if (!isVisible) {
        if (startIdx !== -1) {
          addSegment(startIdx, i - 1, currentType, currentLayer);
          startIdx = -1;
        }
        continue;
      }
      
      const type = points.type[i] === 0 ? 'perimeter' : 'infill';
      
      if (startIdx === -1) {
        startIdx = i;
        currentType = type;
        currentLayer = layer;
        continue;
      }
      
      const typeChanged = type !== currentType || layer !== currentLayer;
      const jumpZ = Math.abs(points.z[i] - points.z[i-1]) > 0.1 && type === 'infill';
      const jumpXY = Math.sqrt(Math.pow(points.x[i] - points.x[i-1], 2) + Math.pow(points.y[i] - points.y[i-1], 2)) > 5.0;
      
      if (typeChanged || jumpZ || jumpXY) {
        addSegment(startIdx, i - 1, currentType, currentLayer);
        startIdx = i;
        currentType = type;
        currentLayer = layer;
      }
    }
    
    if (startIdx !== -1) {
      addSegment(startIdx, pointCount - 1, currentType, currentLayer);
    }
    
    const result = [];
    for (const key of Object.keys(groups)) {
      const arr = groups[key];
      if (arr.length === 0) continue;
      
      const positions = new Float32Array(arr);
      const geom = new THREE.BufferGeometry();
      geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      
      let color = key === 'infill' ? 0xff8c00 : colors[parseInt(key.split('_')[1])];
      
      const material = new THREE.LineBasicMaterial({ color: color });
      result.push(<primitive key={key} object={new THREE.LineSegments(geom, material)} />);
    }
    
    return result;
  }, [points, pointCount, maxVisibleLayer, isolateLayer]);

  return <>{lineGeometries}</>;
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
  const [infillDensity, setInfillDensity] = useState(20);
  const [infillPattern, setInfillPattern] = useState("lines");
  const [layerHeight, setLayerHeight] = useState(0.2);
  const [waveAmplitude, setWaveAmplitude] = useState(0.0);
  const [waveFrequency, setWaveFrequency] = useState(0.1);
  const [modelScale, setModelScale] = useState(1.0);
  const [rotX, setRotX] = useState(0);
  const [rotY, setRotY] = useState(0);
  const [rotZ, setRotZ] = useState(0);
  const [posX, setPosX] = useState(0);
  const [posY, setPosY] = useState(0);
  const [transformMode, setTransformMode] = useState("translate");
  const [autoSegment, setAutoSegment] = useState(false);
  const [segmentInfo, setSegmentInfo] = useState<any>(null);
  const [isolateLayer, setIsolateLayer] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  
  const [stlGeometry, setStlGeometry] = useState<THREE.BufferGeometry | null>(null);
  
  const [isSlicing, setIsSlicing] = useState(false);
  const [isResettingCamera, setIsResettingCamera] = useState(false);
  const [toolpathPoints, setToolpathPoints] = useState<any>(null);
  const [gcodeData, setGcodeData] = useState<string | null>(null);
  const [previewProgress, setPreviewProgress] = useState(100);
  const [maxVisibleLayer, setMaxVisibleLayer] = useState(9999);
  const [totalLayers, setTotalLayers] = useState(0);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [status, setStatus] = useState<string>('SYSTEM_READY');
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const controlsRef = useRef<any>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const selectedFile = e.target.files[0];
      setFile(selectedFile);
      setStatus(`LOADED: ${selectedFile.name}`);
      
      const reader = new FileReader();
      reader.onload = (event) => {
        if (event.target && event.target.result) {
          try {
            const loader = new STLLoader();
            const geometry = loader.parse(event.target.result as ArrayBuffer);
            
            geometry.computeBoundingBox();
            if (geometry.boundingBox) {
              const minB = geometry.boundingBox.min;
              const maxB = geometry.boundingBox.max;
              const centerX = (minB.x + maxB.x) / 2.0;
              const centerY = (minB.y + maxB.y) / 2.0;
              const centerZ = (minB.z + maxB.z) / 2.0;
              geometry.translate(-centerX, -centerY, -centerZ);
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
    setToolpathPoints(null);
    setGcodeData(null);
    setSegmentInfo(null);
    setPreviewProgress(100);
    
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("line_width", "0.4");
      formData.append("bed_center_z", "50.0");
      formData.append("layer_height", layerHeight.toString());
      formData.append("wave_amplitude", waveAmplitude.toString());
      formData.append("wave_frequency", waveFrequency.toString());
      formData.append("infill_density", infillDensity.toString());
      formData.append("infill_pattern", infillPattern);
      formData.append("auto_segment", autoSegment ? "true" : "false");
      formData.append("model_scale", modelScale.toString());
      formData.append("rot_x", rotX.toString());
      formData.append("rot_y", rotY.toString());
      formData.append("rot_z", rotZ.toString());
      formData.append("pos_x", posX.toString());
      formData.append("pos_y", posY.toString());
      
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
      const segInfo = response.data.segmentation_info;
      
      if (points.length > 0) {
        const maxLayer = Math.max(...points.map((p: any) => p.layer));
        setTotalLayers(maxLayer);
        setMaxVisibleLayer(maxLayer);
      }
      
      setToolpathPoints(points);
      setGcodeData(gcode);
      if (segInfo) setSegmentInfo(segInfo);
      setStatus(`SUCCESS: GENERATED ${points.length} Pts`);
      
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
    a.download = `${file.name.replace('.stl', '')}_open5x_volumetric.gcode`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="app-container">
      <header className="topbar">
        <div className="text-muted" style={{ fontWeight: 700 }}>
          &gt;_ OPEN5X_SLICER.EXE
        </div>
        <button className="btn-secondary" onClick={() => setHasEntered(false)} style={{ padding: '8px 16px', fontSize: '14px', width: 'auto' }}>
          [ EXIT_SLICER ]
        </button>
      </header>

      <div className="main-content">
        <aside className="sidebar">
          <div className="accent-text" style={{ marginBottom: '10px' }}>
            &gt; TRANSFORM MODEL
          </div>
          
          <div className="btn-group" style={{ marginBottom: '10px', display: 'flex', gap: '5px' }}>
            <button 
              className={transformMode === 'translate' ? 'btn-primary' : 'btn-secondary'} 
              style={{ width: '33%', padding: '5px', fontSize: '10px' }}
              onClick={() => setTransformMode('translate')}
            >MOVE</button>
            <button 
              className={transformMode === 'rotate' ? 'btn-primary' : 'btn-secondary'} 
              style={{ width: '33%', padding: '5px', fontSize: '10px' }}
              onClick={() => setTransformMode('rotate')}
            >ROTATE</button>
            <button 
              className={transformMode === 'scale' ? 'btn-primary' : 'btn-secondary'} 
              style={{ width: '33%', padding: '5px', fontSize: '10px' }}
              onClick={() => setTransformMode('scale')}
            >SCALE</button>
          </div>
          
          <div className="controls-container" style={{ marginBottom: '20px' }}>
            <div className="input-row">
              <label>SCALE (Multiplier)</label>
              <input 
                type="number" 
                className="terminal-input"
                step="0.1" 
                min="0.1"
                value={modelScale} 
                onChange={e => setModelScale(parseFloat(e.target.value))} 
              />
            </div>
            
            <div className="input-row" style={{ marginTop: '10px' }}>
              <label>ROTATION X/Y/Z (Deg)</label>
              <div style={{ display: 'flex', gap: '5px' }}>
                <input type="number" className="terminal-input" style={{ width: '33%' }} value={rotX} onChange={e => setRotX(parseFloat(e.target.value))} />
                <input type="number" className="terminal-input" style={{ width: '33%' }} value={rotY} onChange={e => setRotY(parseFloat(e.target.value))} />
                <input type="number" className="terminal-input" style={{ width: '33%' }} value={rotZ} onChange={e => setRotZ(parseFloat(e.target.value))} />
              </div>
            </div>
            
            <div className="input-row" style={{ marginTop: '10px' }}>
              <label>POSITION X/Y (mm)</label>
              <div style={{ display: 'flex', gap: '5px' }}>
                <input type="number" className="terminal-input" style={{ width: '50%' }} value={posX} onChange={e => setPosX(parseFloat(e.target.value))} />
                <input type="number" className="terminal-input" style={{ width: '50%' }} value={posY} onChange={e => setPosY(parseFloat(e.target.value))} />
              </div>
            </div>
          </div>
          
          <div className="accent-text" style={{ marginBottom: '10px', borderTop: '1px solid rgba(31,107,31,0.4)', paddingTop: '10px' }}>
            &gt; CONFIGURE VOLUMETRIC SLICER
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
                value={infillDensity} 
                onChange={e => setInfillDensity(parseInt(e.target.value))} 
              />
            </div>
            
            <div className="input-row" style={{ marginTop: '10px' }}>
              <label>INFILL PATTERN</label>
              <select 
                className="terminal-input"
                value={infillPattern} 
                onChange={e => setInfillPattern(e.target.value)}
                style={{ width: '80px' }}
              >
                <option value="lines">LINES</option>
                <option value="grid">GRID</option>
              </select>
            </div>
            
            <div className="input-row" style={{ marginTop: '10px' }}>
              <label>LAYER HEIGHT (mm)</label>
              <input 
                type="number" 
                className="terminal-input"
                step="0.1" 
                min="0.1"
                value={layerHeight} 
                onChange={e => setLayerHeight(parseFloat(e.target.value))} 
              />
            </div>
            
            <div className="input-row" style={{ marginTop: '10px' }}>
              <label>WAVE AMPLITUDE (mm)</label>
              <input 
                type="number" 
                className="terminal-input"
                step="0.5" 
                min="0"
                value={waveAmplitude} 
                onChange={e => setWaveAmplitude(parseFloat(e.target.value))} 
              />
            </div>
            
            <div className="input-row" style={{ marginTop: '10px' }}>
              <label>WAVE FREQ (1/mm)</label>
              <input 
                type="number" 
                className="terminal-input"
                step="0.05" 
                min="0"
                value={waveFrequency} 
                onChange={e => setWaveFrequency(parseFloat(e.target.value))} 
              />
            </div>
            
            <div className="input-row" style={{ marginTop: '20px', borderTop: '1px solid rgba(31,107,31,0.4)', paddingTop: '10px', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <input 
                type="checkbox" 
                id="autoSegment" 
                checked={autoSegment}
                onChange={(e) => setAutoSegment(e.target.checked)}
              />
              <label htmlFor="autoSegment" style={{ color: '#39ff14', cursor: 'pointer', fontWeight: 'bold' }}>AUTO-SEGMENT OVERHANGS</label>
            </div>
            
            {segmentInfo && segmentInfo.auto_segment && (
              <div style={{ marginTop: '10px', fontSize: '11px', color: '#ff8c00', backgroundColor: '#111', padding: '8px', border: '1px solid #1f6b1f' }}>
                <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>ANALYSIS RESULTS:</div>
                <div>Z-CUTOFF: {segmentInfo.calc_z_cutoff} mm</div>
                <div>BED TILT: {segmentInfo.calc_segment_tilt}°</div>
              </div>
            )}
            
            {toolpathPoints && toolpathPoints.x && toolpathPoints.x.length > 0 && (
              <>
                <div className="input-row" style={{ marginTop: '20px' }}>
                  <label>VISIBLE LAYER: {maxVisibleLayer} / {totalLayers}</label>
                  <input 
                    type="range" 
                    min="0" 
                    max={totalLayers} 
                    value={maxVisibleLayer} 
                    onChange={e => setMaxVisibleLayer(parseInt(e.target.value))}
                    className="terminal-slider"
                  />
                </div>
                
                <div style={{ marginTop: '10px', display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <input 
                    type="checkbox" 
                    id="isolate" 
                    checked={isolateLayer}
                    onChange={(e) => setIsolateLayer(e.target.checked)}
                  />
                  <label htmlFor="isolate" style={{ cursor: 'pointer' }}>ISOLATE SINGLE LAYER</label>
                </div>

                <div className="input-row" style={{ marginTop: '10px' }}>
                  <label>PRINT PROGRESS: {previewProgress}%</label>
                  <input 
                    type="range" 
                    min="0" 
                    max="100" 
                    value={previewProgress} 
                    onChange={e => setPreviewProgress(parseInt(e.target.value))}
                    className="terminal-slider"
                  />
                </div>
                <div style={{ marginTop: '10px', fontSize: '10px', display: 'flex', gap: '10px' }}>
                  <div style={{ color: '#ffffff' }}>■ 5-Axis Perimeter (Rainbow)</div>
                  <div style={{ color: '#ff8c00' }}>■ 3-Axis Infill (Solid Orange)</div>
                </div>
              </>
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
              {isSlicing ? (uploadProgress < 100 ? `Uploading ${uploadProgress}%...` : 'Executing Python Engine...') : 'Initiate Slicing'}
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

        <main className="canvas-area" style={{ position: 'relative' }}>
          <Canvas shadows camera={{ position: [0, -80, 15], up: [0, 0, 1], fov: 50 }}>
            <ambientLight intensity={0.3} />
            <directionalLight position={[20, 20, 30]} intensity={1.5} castShadow shadow-mapSize={[1024, 1024]} />
            <directionalLight position={[-20, -20, 10]} intensity={0.5} />
            
            <mesh position={[0, 0, -2.5]} receiveShadow>
              <boxGeometry args={[250, 250, 5]} />
              <meshStandardMaterial color="#3a3a3a" roughness={0.8} metalness={0.2} />
            </mesh>
            
            <gridHelper 
              args={[250, 25, 0x39ff14, 0x1f6b1f]} 
              rotation={[Math.PI / 2, 0, 0]} 
              position={[0, 0, 0.01]} 
            />
            
            <TransformControls 
              mode={transformMode as any}
              showZ={transformMode !== 'translate'} // Hide Z arrow for move mode (since it snaps to bed)
              position={[posX, posY, 0]}
              rotation={[rotX * Math.PI / 180, rotY * Math.PI / 180, rotZ * Math.PI / 180]}
              scale={[modelScale, modelScale, modelScale]}
              onMouseUp={(e: any) => {
                if (e.target.object) {
                  const obj = e.target.object;
                  setPosX(Number(obj.position.x.toFixed(2)));
                  setPosY(Number(obj.position.y.toFixed(2)));
                  setRotX(Number((obj.rotation.x * 180 / Math.PI).toFixed(2)));
                  setRotY(Number((obj.rotation.y * 180 / Math.PI).toFixed(2)));
                  setRotZ(Number((obj.rotation.z * 180 / Math.PI).toFixed(2)));
                  setModelScale(Number(obj.scale.x.toFixed(2)));
                }
              }}
            >
              <mesh visible={false}>
                <boxGeometry args={[50, 50, 50]} />
                <meshBasicMaterial />
              </mesh>
            </TransformControls>
            
            <StlModel geometry={stlGeometry} modelScale={modelScale} rotX={rotX} rotY={rotY} rotZ={rotZ} posX={posX} posY={posY} />
            <Toolpath points={toolpathPoints} progress={previewProgress} maxVisibleLayer={maxVisibleLayer} isolateLayer={isolateLayer} />
            
            <CameraResetter isResetting={isResettingCamera} setIsResetting={setIsResettingCamera} controlsRef={controlsRef} />
            <OrbitControls ref={controlsRef} makeDefault onStart={() => setIsResettingCamera(false)} />
          </Canvas>
          <button 
            className="btn-secondary" 
            style={{ position: 'absolute', bottom: '20px', right: '20px', zIndex: 10, width: 'auto', padding: '8px 16px', fontSize: '14px' }}
            onClick={() => setIsResettingCamera(true)}
          >
            [ HOME_VIEW ]
          </button>
        </main>
      </div>
    </div>
  );
}

export default App;
