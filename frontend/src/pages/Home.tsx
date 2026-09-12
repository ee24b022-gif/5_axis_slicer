import React, { useState, useRef, useEffect, useMemo } from 'react';
import { useFrame, Canvas } from '@react-three/fiber';
import { OrbitControls, TransformControls } from '@react-three/drei';
import * as THREE from 'three';
// @ts-ignore
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js';
import { useMachineProfiles, useUploadMesh, useSubmitJob } from '../api/queries';
import type { JobMode } from '../api/models';
import { computeSlicePlane } from '../utils/kinematics';
import { JobProgress } from '../components/JobProgress';
import '../index.css';

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
    geom.center(); // Center exactly like the backend does before applying scale and rotation!
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

function Toolpath({ layers, chunkBounds, progress, maxVisibleLayer, isolateLayer, visibleCategories, lodLevel, showChunkBounds }: { layers: any[], chunkBounds?: any[], progress: number, maxVisibleLayer: number, isolateLayer: boolean, visibleCategories: Record<string, boolean>, lodLevel: string, showChunkBounds: boolean }) {
  if (!layers || layers.length === 0) return null;
  
  const layerGeometries = useMemo(() => {
    const visibleLayers = layers.filter(l => 
      isolateLayer ? l.layer_idx === maxVisibleLayer : l.layer_idx <= maxVisibleLayer
    );
    
    const targetLayerCount = Math.max(1, Math.floor(visibleLayers.length * (progress / 100)));
    const slicedLayers = visibleLayers.slice(0, targetLayerCount);

    const groups: Record<string, number[]> = {
      shell: [],
      solid_infill: [],
      internal_infill: [],
      brim: [],
      travel: []
    };
    
    slicedLayers.forEach(layer => {
      if (!layer.paths) return;
      layer.paths.forEach((path: any) => {
        if (!visibleCategories[path.type]) return;
        
        let step = 1;
        if (lodLevel === 'medium') {
          // medium: downsample infill types
          if (path.type.includes('infill')) step = 2;
        } else if (lodLevel === 'low') {
          // low: downsample shells, heavily downsample infill
          if (path.type.includes('shell') || path.type.includes('brim')) step = 2;
          else if (path.type.includes('infill')) step = 3;
        }
        
        // We iterate in pairs/segments: 6 elements per line segment (x1,y1,z1, x2,y2,z2)
        // Note: the points array is sequential [x1,y1,z1, x2,y2,z2, ...]. 
        // If we skip points, we might break line continuity, so we must link (p_i, p_i+step).
        if (step === 1) {
          groups[path.type].push(...path.points);
        } else {
          // Simple decimation for visualization
          for (let i = 0; i < path.points.length - 3 * step; i += 3 * step) {
            groups[path.type].push(
              path.points[i], path.points[i+1], path.points[i+2],
              path.points[i + 3 * step], path.points[i + 3 * step + 1], path.points[i + 3 * step + 2]
            );
          }
        }
      });
    });
    
    const colors: Record<string, number> = {
      shell: 0x00ff00,
      solid_infill: 0xffff00,
      internal_infill: 0xff8c00,
      brim: 0x800080,
      travel: 0x000080
    };

    const result = [];
    for (const key of Object.keys(groups)) {
      const arr = groups[key];
      if (arr.length === 0) continue;
      
      const positions = new Float32Array(arr);
      const geom = new THREE.BufferGeometry();
      geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      
      const material = new THREE.LineBasicMaterial({ 
        color: colors[key] || 0xffffff,
        transparent: key === 'travel',
        opacity: key === 'travel' ? 0.3 : 1.0
      });
      result.push(<primitive key={key} object={new THREE.LineSegments(geom, material)} />);
    }
    
    if (showChunkBounds && chunkBounds) {
      chunkBounds.forEach((bound: any, idx: number) => {
        const height = bound.z_max - bound.z_min;
        const centerZ = bound.z_min + height / 2;
        const geom = new THREE.BoxGeometry(50, 50, height);
        const edges = new THREE.EdgesGeometry(geom);
        const material = new THREE.LineBasicMaterial({ color: 0x00ffff, transparent: true, opacity: 0.2 });
        result.push(
          <group key={`chunk_${idx}`} position={[0, 0, centerZ]}>
            <primitive object={new THREE.LineSegments(edges, material)} />
          </group>
        );
      });
    }

    return result;
  }, [layers, chunkBounds, progress, maxVisibleLayer, isolateLayer, visibleCategories, lodLevel, showChunkBounds]);

  return <>{layerGeometries}</>;
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
function Nozzle({ visible }: { visible: boolean }) {
  if (!visible) return null;
  return (
    <group position={[0, 0, 50]} rotation={[Math.PI / 2, 0, 0]}>
      {/* Nozzle Cone */}
      <mesh position={[0, -10, 0]}>
        <coneGeometry args={[2, 20, 32]} />
        <meshStandardMaterial color="#ff4500" metalness={0.8} roughness={0.2} />
      </mesh>
      {/* Nozzle Tip */}
      <mesh position={[0, 0.5, 0]}>
        <cylinderGeometry args={[0.2, 0.5, 1, 16]} />
        <meshStandardMaterial color="#cccccc" metalness={0.9} roughness={0.1} />
      </mesh>
    </group>
  );
}

function KinematicGroup({ children, points, progress, simulationMode, isPlaying, simulationSpeed, setPreviewProgress }: { children: React.ReactNode, points: any, progress: number, simulationMode: boolean, isPlaying: boolean, simulationSpeed: number, setPreviewProgress: (p: number) => void }) {
  const groupRef = useRef<THREE.Group>(null);
  const targetPos = useRef(new THREE.Vector3());
  const targetQuat = useRef(new THREE.Quaternion());
  const lastUpdate = useRef(0);
  
  useFrame((state, delta) => {
    if (isPlaying) {
      if (state.clock.elapsedTime - lastUpdate.current > 0.02) { // approx 50 FPS updates
        const nextProgress = Math.min(100, progress + (0.1 * simulationSpeed));
        setPreviewProgress(nextProgress);
        lastUpdate.current = state.clock.elapsedTime;
      }
    }

    if (!groupRef.current) return;

    if (!simulationMode || !points || !points.x || points.x.length < 2) {
      targetPos.current.set(0, 0, 0);
      targetQuat.current.identity();
    } else {
      const totalPoints = points.x.length;
      const idx = Math.max(0, Math.min(totalPoints - 1, Math.floor(totalPoints * (progress / 100))));
      
      const px = points.x[idx];
      const py = points.y[idx];
      const pz = points.z[idx];
      
      let nx = 0, ny = 0, nz = 1;
      if (points.nx && points.nx.length > idx) {
        nx = points.nx[idx];
        ny = points.ny[idx];
        nz = points.nz[idx];
      }
      
      const targetNormal = new THREE.Vector3(nx, ny, nz).normalize();
      const up = new THREE.Vector3(0, 0, 1);
      const quat = new THREE.Quaternion().setFromUnitVectors(targetNormal, up);
      targetQuat.current.copy(quat);
      
      const pointPos = new THREE.Vector3(px, py, pz);
      pointPos.applyQuaternion(quat);
      
      const nozzlePos = new THREE.Vector3(0, 0, 50);
      targetPos.current.copy(nozzlePos).sub(pointPos);
    }
    
    const lerpFactor = Math.min(1.0, delta * 15.0);
    groupRef.current.position.lerp(targetPos.current, lerpFactor);
    groupRef.current.quaternion.slerp(targetQuat.current, lerpFactor);
  });

  return <group ref={groupRef}>{children}</group>;
}

export default function Home() {
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
  
  const [visibleCategories, setVisibleCategories] = useState<Record<string, boolean>>({
    shell: true, solid_infill: true, internal_infill: true, brim: true, travel: true
  });
  const [showChunkBounds, setShowChunkBounds] = useState(true);
  const [lodLevel, setLodLevel] = useState('high');
  const [safetyAcknowledged, setSafetyAcknowledged] = useState(false);
  
  const [isSlicing, setIsSlicing] = useState(false);
  const [isResettingCamera, setIsResettingCamera] = useState(false);
  const [toolpathPoints, setToolpathPoints] = useState<any>(null);
  const [previewLayers, setPreviewLayers] = useState<any[] | null>(null);
  const [previewChunkBounds, setPreviewChunkBounds] = useState<any[] | null>(null);
  const [gcodeData, setGcodeData] = useState<string | null>(null);
  const [previewProgress, setPreviewProgress] = useState(100);
  const [maxVisibleLayer, setMaxVisibleLayer] = useState(9999);
  const [totalLayers, setTotalLayers] = useState(0);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [status, setStatus] = useState<string>('SYSTEM_READY');
  const [simulationMode, setSimulationMode] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [simulationSpeed, setSimulationSpeed] = useState(1.0);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const controlsRef = useRef<any>(null);

  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  // New State for F-087 & F-088
  const [machineProfileId, setMachineProfileId] = useState("");
  const [jobMode, setJobMode] = useState<JobMode>("three_axis");
  const [indexedPlanes, setIndexedPlanes] = useState([{ z: 0, theta: 0, phi: 0 }]);
  const [validationError, setValidationError] = useState<string | null>(null);

  // React Query Hooks
  const { data: profiles, isLoading: isLoadingProfiles } = useMachineProfiles();
  const uploadMesh = useUploadMesh();
  const submitJob = useSubmitJob();

  // Auto-select first profile if none selected
  useEffect(() => {
    if (profiles && profiles.length > 0 && !machineProfileId) {
      setMachineProfileId(profiles[0].id);
    }
  }, [profiles, machineProfileId]);

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

  const validateSettings = () => {
    setValidationError(null);
    if (!file) return "NO_FILE_SELECTED";
    if (!machineProfileId) return "NO_MACHINE_PROFILE_SELECTED";
    if (modelScale <= 0) return "INVALID_SCALE";
    if (layerHeight <= 0 || layerHeight > 2.0) return "INVALID_LAYER_HEIGHT";
    if (infillDensity < 0 || infillDensity > 100) return "INVALID_INFILL_DENSITY";
    if (rotX < -360 || rotX > 360) return "INVALID_ROTATION_X";
    if (rotY < -360 || rotY > 360) return "INVALID_ROTATION_Y";
    if (rotZ < -360 || rotZ > 360) return "INVALID_ROTATION_Z";
    
    if (jobMode === 'indexed_multidirectional') {
      if (indexedPlanes.length === 0) return "NO_PLANES_DEFINED";
      if (indexedPlanes[0].theta !== 0) return "INITIAL_PLANE_MUST_BE_HORIZONTAL";
      for (let i = 1; i < indexedPlanes.length; i++) {
        if (indexedPlanes[i].theta === 0) return "INVALID_PLANE_THETA_ZERO";
      }
    }
    
    return null;
  };

  const handleSlice = async () => {
    const error = validateSettings();
    if (error) {
      setValidationError(error);
      setStatus(`ERR: ${error}`);
      return;
    }
    
    setIsSlicing(true);
    setStatus('UPLOADING_STL...');
    setUploadProgress(0);
    setToolpathPoints(null);
    setPreviewLayers(null);
    setPreviewChunkBounds(null);
    setGcodeData(null);
    setSegmentInfo(null);
    setPreviewProgress(100);
    setSafetyAcknowledged(false);
    
    try {
      const formData = new FormData();
      formData.append("file", file!);
      
      const meshResponse = await uploadMesh.mutateAsync({
        formData,
        onUploadProgress: (progressEvent: any) => {
          if (progressEvent.total) {
            const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            setUploadProgress(percent);
            if (percent === 100) setStatus('SUBMITTING_JOB...');
          }
        }
      });
      
      const settings: any = {
        line_width: 0.4,
        bed_center_z: 50.0,
        layer_height: layerHeight,
        wave_amplitude: waveAmplitude,
        wave_frequency: waveFrequency,
        infill_density: infillDensity,
        infill_pattern: infillPattern,
        auto_segment: autoSegment,
        model_scale: modelScale,
        rot_x: rotX,
        rot_y: rotY,
        rot_z: rotZ,
        pos_x: posX,
        pos_y: posY
      };

      if (jobMode === 'indexed_multidirectional') {
        settings.planes = indexedPlanes.map(p => computeSlicePlane(p.z, p.theta, p.phi));
      }
      
      const jobResponse = await submitJob.mutateAsync({
        mesh_id: meshResponse.id,
        machine_profile_id: machineProfileId,
        mode: jobMode,
        settings: settings
      });
      
      setStatus(`SUCCESS: JOB PENDING (ID: ${jobResponse.id})`);
      setActiveJobId(jobResponse.id);
      
    } catch (error: any) {
      console.error("Failed to slice:", error);
      const errMsg = error.response?.data?.detail || error.message || 'SLICE_FAILED';
      setStatus(`ERR: ${typeof errMsg === 'string' ? errMsg.substring(0, 30) : 'API_ERROR'}`);
      setValidationError(`Job creation failed: ${typeof errMsg === 'string' ? errMsg : JSON.stringify(errMsg)}`);
    } finally {
      setIsSlicing(false);
    }
  };

  const loadPreviewFixture = async () => {
    try {
      const res = await fetch('/preview_fixture.json');
      const data = await res.json();
      setPreviewLayers(data.layers);
      setPreviewChunkBounds(data.chunk_boundaries);
      setTotalLayers(data.layers.length);
      setMaxVisibleLayer(data.layers.length);
      setStatus('FIXTURE_LOADED');
      
      // Flatten paths to maintain compatibility with KinematicGroup tracking
      const flatPoints = { x: [], y: [], z: [], nx: [], ny: [], nz: [] } as any;
      data.layers.forEach((layer: any) => {
        layer.paths.forEach((path: any) => {
          for(let i=0; i<path.points.length; i+=3) {
            flatPoints.x.push(path.points[i]);
            flatPoints.y.push(path.points[i+1]);
            flatPoints.z.push(path.points[i+2]);
            flatPoints.nx.push(0);
            flatPoints.ny.push(0);
            flatPoints.nz.push(1);
          }
        });
      });
      setToolpathPoints(flatPoints);
    } catch (e) {
      console.error(e);
      setStatus('ERR: FIXTURE_LOAD_FAIL');
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
          {activeJobId ? (
            <JobProgress 
              jobId={activeJobId} 
              onRestart={() => {
                setActiveJobId(null);
                setStatus('SYSTEM_READY');
                setUploadProgress(0);
              }} 
            />
          ) : (
            <>
              <div className="btn-group" style={{ marginBottom: '20px' }}>
                <label style={{ display: 'block', width: '100%' }}>
              <div className="btn-secondary" style={{ width: '100%', borderColor: '#39ff14', color: '#39ff14' }}>
                [ {file ? file.name.substring(0, 20) + (file.name.length > 20 ? '...' : '') : "Upload STL File"} ]
              </div>
              <input 
                type="file" 
                accept=".stl" 
                onChange={handleFileChange} 
                ref={fileInputRef}
                style={{ display: 'none' }}
              />
            </label>
          </div>

          <div className="accent-text" style={{ marginBottom: '10px' }}>
            &gt; MACHINE CONFIGURATION
          </div>

          <div className="controls-container" style={{ marginBottom: '20px' }}>
            <div className="input-row">
              <label>MACHINE PROFILE</label>
              <select 
                className="terminal-input"
                value={machineProfileId} 
                onChange={e => setMachineProfileId(e.target.value)}
                style={{ width: '100%' }}
                disabled={isLoadingProfiles}
              >
                <option value="">-- Select Profile --</option>
                {(Array.isArray(profiles) ? profiles : (profiles as any)?.items && Array.isArray((profiles as any).items) ? (profiles as any).items : []).map((p: any) => (
                  <option key={p.id} value={p.id}>{p.name} (Rev {p.revision})</option>
                ))}
              </select>
            </div>

            <div className="input-row" style={{ marginTop: '10px' }}>
              <label>JOB MODE</label>
              <select 
                className="terminal-input"
                value={jobMode} 
                onChange={e => setJobMode(e.target.value as JobMode)}
                style={{ width: '100%' }}
              >
                <option value="three_axis">3-Axis Planar</option>
                <option value="indexed_multidirectional">5-Axis Indexed</option>
              </select>
            </div>
          </div>

          {jobMode === 'indexed_multidirectional' && (
            <>
              <div className="accent-text" style={{ marginBottom: '10px' }}>
                &gt; INDEXED PLANES (Z, θ, φ)
              </div>
              <div className="controls-container" style={{ marginBottom: '20px' }}>
                {indexedPlanes.map((plane, idx) => (
                  <div key={idx} style={{ display: 'flex', gap: '5px', marginBottom: '10px' }}>
                    <input 
                      type="number" 
                      className="terminal-input" 
                      style={{ width: '25%' }} 
                      placeholder="Z" 
                      value={plane.z} 
                      onChange={e => {
                        const newPlanes = [...indexedPlanes];
                        newPlanes[idx].z = parseFloat(e.target.value) || 0;
                        setIndexedPlanes(newPlanes);
                      }} 
                    />
                    <input 
                      type="number" 
                      className="terminal-input" 
                      style={{ width: '25%' }} 
                      placeholder="Theta" 
                      value={plane.theta} 
                      disabled={idx === 0}
                      onChange={e => {
                        const newPlanes = [...indexedPlanes];
                        newPlanes[idx].theta = parseFloat(e.target.value) || 0;
                        setIndexedPlanes(newPlanes);
                      }} 
                    />
                    <input 
                      type="number" 
                      className="terminal-input" 
                      style={{ width: '25%' }} 
                      placeholder="Phi" 
                      value={plane.phi} 
                      onChange={e => {
                        const newPlanes = [...indexedPlanes];
                        newPlanes[idx].phi = parseFloat(e.target.value) || 0;
                        setIndexedPlanes(newPlanes);
                      }} 
                    />
                    <button 
                      className="btn-secondary" 
                      style={{ width: '25%', padding: '0' }}
                      disabled={idx === 0}
                      onClick={() => setIndexedPlanes(indexedPlanes.filter((_, i) => i !== idx))}
                    >
                      X
                    </button>
                  </div>
                ))}
                <button 
                  className="btn-secondary" 
                  style={{ width: '100%' }}
                  onClick={() => setIndexedPlanes([...indexedPlanes, { z: 50, theta: 45, phi: 0 }])}
                >
                  + ADD PLANE
                </button>
              </div>
            </>
          )}

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
                    step="0.1"
                    value={previewProgress} 
                    onChange={e => setPreviewProgress(parseFloat(e.target.value))}
                    className="terminal-slider"
                  />
                </div>
                
                <div style={{ marginTop: '15px', display: 'flex', gap: '10px' }}>
                  <button 
                    className={simulationMode ? "btn-primary" : "btn-secondary"} 
                    style={{ flex: 1, padding: '5px', fontSize: '10px' }}
                    onClick={() => setSimulationMode(!simulationMode)}
                  >
                    SIMULATION: {simulationMode ? "ON" : "OFF"}
                  </button>
                  <button 
                    className={isPlaying ? "btn-primary" : "btn-secondary"} 
                    style={{ flex: 1, padding: '5px', fontSize: '10px' }}
                    onClick={() => setIsPlaying(!isPlaying)}
                    disabled={!simulationMode}
                  >
                    {isPlaying ? "PAUSE" : "PLAY"}
                  </button>
                </div>
                
                {simulationMode && (
                  <div className="input-row" style={{ marginTop: '10px' }}>
                    <label>SIMULATION SPEED</label>
                    <select 
                      className="terminal-input"
                      value={simulationSpeed} 
                      onChange={e => setSimulationSpeed(parseFloat(e.target.value))}
                      style={{ width: '80px' }}
                    >
                      <option value={0.1}>0.1x</option>
                      <option value={0.25}>0.25x</option>
                      <option value={0.5}>0.5x</option>
                      <option value={1.0}>1.0x</option>
                      <option value={2.0}>2.0x</option>
                      <option value={5.0}>5.0x</option>
                    </select>
                  </div>
                )}
                
                <div style={{ marginTop: '10px', fontSize: '10px', display: 'flex', flexDirection: 'column', gap: '5px' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                    <input type="checkbox" checked={visibleCategories.shell} onChange={e => setVisibleCategories({...visibleCategories, shell: e.target.checked})} />
                    <span style={{ color: '#00ff00' }}>■ Shells</span>
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                    <input type="checkbox" checked={visibleCategories.solid_infill} onChange={e => setVisibleCategories({...visibleCategories, solid_infill: e.target.checked})} />
                    <span style={{ color: '#ffff00' }}>■ Solid Infill</span>
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                    <input type="checkbox" checked={visibleCategories.internal_infill} onChange={e => setVisibleCategories({...visibleCategories, internal_infill: e.target.checked})} />
                    <span style={{ color: '#ff8c00' }}>■ Internal Infill</span>
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                    <input type="checkbox" checked={visibleCategories.brim} onChange={e => setVisibleCategories({...visibleCategories, brim: e.target.checked})} />
                    <span style={{ color: '#800080' }}>■ Brim</span>
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                    <input type="checkbox" checked={visibleCategories.travel} onChange={e => setVisibleCategories({...visibleCategories, travel: e.target.checked})} />
                    <span style={{ color: '#000080' }}>■ Travel (Transparent)</span>
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                    <input type="checkbox" checked={showChunkBounds} onChange={e => setShowChunkBounds(e.target.checked)} />
                    <span style={{ color: '#00ffff' }}>■ Chunk Bounds</span>
                  </label>
                </div>
                
                <div className="input-row" style={{ marginTop: '10px' }}>
                  <label>LEVEL OF DETAIL (LOD)</label>
                  <select 
                    className="terminal-input"
                    value={lodLevel} 
                    onChange={e => setLodLevel(e.target.value)}
                    style={{ width: '80px' }}
                  >
                    <option value="high">High</option>
                    <option value="medium">Medium</option>
                    <option value="low">Low</option>
                  </select>
                </div>
              </>
            )}
          </div>  
            {isSlicing && uploadProgress < 100 && (
              <div style={{ marginTop: '10px', width: '100%', height: '10px', backgroundColor: '#111', border: '1px solid #1f6b1f' }}>
                <div style={{ height: '100%', backgroundColor: '#39ff14', width: `${uploadProgress}%`, transition: 'width 0.2s' }}></div>
              </div>
            )}
            
            {validationError && (
              <div style={{ color: '#ff4500', marginBottom: '10px', fontSize: '12px' }}>
                {validationError}
              </div>
            )}
            
            <button className="btn-primary" style={{ marginTop: '10px' }} onClick={handleSlice} disabled={isSlicing || uploadMesh.isPending || submitJob.isPending || !file}>
              {isSlicing ? (uploadProgress < 100 ? `Uploading ${uploadProgress}%...` : 'Submitting Job...') : 'Submit Job'}
            </button>
            
            {gcodeData && (
              <div style={{ marginTop: '20px', padding: '10px', border: '1px solid #ff4500', backgroundColor: 'rgba(255, 69, 0, 0.1)' }}>
                <div style={{ color: '#ff4500', fontWeight: 'bold', marginBottom: '5px', fontSize: '12px' }}>
                  WARNING: EXPERIMENTAL EXPORT
                </div>
                <div style={{ fontSize: '10px', color: '#ffb347', marginBottom: '10px', lineHeight: '1.4' }}>
                  Toolpaths are generated using heuristic constraints. Machine-mapping for A/B axes, table clearance, and rotary zero conventions must be manually verified.
                </div>
                <label style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', fontSize: '10px', color: '#aaa', cursor: 'pointer', marginBottom: '15px' }}>
                  <input 
                    type="checkbox" 
                    checked={safetyAcknowledged} 
                    onChange={e => setSafetyAcknowledged(e.target.checked)} 
                    style={{ marginTop: '2px' }}
                  />
                  <span>I acknowledge this is a prototype and I have visually inspected the toolpaths.</span>
                </label>
                
                <button 
                  className="btn-secondary" 
                  onClick={handleDownload} 
                  disabled={!safetyAcknowledged}
                  style={{ 
                    width: '100%', 
                    borderColor: safetyAcknowledged ? '#39ff14' : '#555', 
                    color: safetyAcknowledged ? '#39ff14' : '#555',
                    cursor: safetyAcknowledged ? 'pointer' : 'not-allowed'
                  }}
                >
                  [ Download G-Code ]
                </button>
              </div>
            )}
            
            <button 
              className="btn-secondary" 
              onClick={loadPreviewFixture} 
              style={{ marginTop: '10px', width: '100%', borderColor: '#1f6b1f', color: '#1f6b1f' }}
            >
              [ Load Preview Fixture (F-090) ]
            </button>
        </>
        )}

          <div style={{ marginTop: '30px', borderTop: '1px solid rgba(31,107,31,0.4)', paddingTop: '20px' }}>
            <div className="stat-box">
              <div className="text-muted" style={{ fontSize: '12px' }}>GEOMETRY ENGINE</div>
              <div style={{ fontSize: '18px', fontWeight: 'bold' }}>{previewLayers ? 'ONLINE (FIXTURE)' : 'STANDBY'}</div>
            </div>
            <div className="stat-box">
              <div className="text-muted" style={{ fontSize: '12px' }}>TOOLPATH POINTS</div>
              <div style={{ fontSize: '18px', fontWeight: 'bold' }}>{toolpathPoints && toolpathPoints.x ? toolpathPoints.x.length : 0}</div>
            </div>
          </div>

          <div className="status-text">
            STATUS: {status} <span className="cursor-blink"></span>
          </div>
        </aside>

        <main className="canvas-area" style={{ position: 'relative' }}>
          <div style={{ position: 'absolute', top: 0, left: 0, right: 0, padding: '10px', backgroundColor: 'rgba(255, 69, 0, 0.8)', color: '#fff', textAlign: 'center', zIndex: 10, fontSize: '12px', fontWeight: 'bold', letterSpacing: '1px' }}>
            PROTOTYPE / INSPECT BEFORE USE. Collision-free status is heuristic and NOT guaranteed.
          </div>
          
          <Canvas shadows camera={{ position: [0, -80, 15], up: [0, 0, 1], fov: 50 }}>
            <ambientLight intensity={0.3} />
            <directionalLight position={[20, 20, 30]} intensity={1.5} castShadow shadow-mapSize={[1024, 1024]} />
            <directionalLight position={[-20, -20, 10]} intensity={0.5} />
            
            <Nozzle visible={simulationMode} />
            
            <KinematicGroup points={toolpathPoints} progress={previewProgress} simulationMode={simulationMode} isPlaying={isPlaying} simulationSpeed={simulationSpeed} setPreviewProgress={setPreviewProgress}>
              <mesh position={[0, 0, -2.5]} receiveShadow>
                <boxGeometry args={[250, 250, 5]} />
                <meshStandardMaterial color="#3a3a3a" roughness={0.8} metalness={0.2} />
              </mesh>
              
              <gridHelper 
                args={[250, 25, 0x39ff14, 0x1f6b1f]} 
                rotation={[Math.PI / 2, 0, 0]} 
                position={[0, 0, 0.01]} 
              />
              
              {!simulationMode && (
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
              )}
              
              <StlModel geometry={stlGeometry} modelScale={modelScale} rotX={rotX} rotY={rotY} rotZ={rotZ} posX={posX} posY={posY} />
              <Toolpath layers={previewLayers || []} chunkBounds={previewChunkBounds || []} progress={previewProgress} maxVisibleLayer={maxVisibleLayer} isolateLayer={isolateLayer} visibleCategories={visibleCategories} lodLevel={lodLevel} showChunkBounds={showChunkBounds} />
            </KinematicGroup>
            
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
