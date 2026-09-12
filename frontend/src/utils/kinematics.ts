import type { SlicePlane, RotationConvention, AngleUnit } from '../api/models';

export function computeSlicePlane(zOrigin: number, thetaDeg: number, phiDeg: number): SlicePlane {
  const theta = (thetaDeg * Math.PI) / 180.0;
  const phi = (phiDeg * Math.PI) / 180.0;

  // Spherical coordinate normal relative to +Z axis
  // Tilt (theta) from Z-axis, rotation (phi) around Z-axis
  const nx = Math.sin(theta) * Math.cos(phi);
  const ny = Math.sin(theta) * Math.sin(phi);
  const nz = Math.cos(theta);

  // Local X: orthogonal to N and Z, laying in the XY plane.
  // This matches a robust convention for table kinematics.
  let lx;
  if (Math.abs(nz) === 1.0) {
    // Purely horizontal plane (theta = 0 or 180)
    lx = [1.0, 0.0, 0.0];
  } else {
    const lx_x = -Math.sin(phi);
    const lx_y = Math.cos(phi);
    const lx_z = 0.0;
    
    // Normalize local_x (it should already be length 1, but we do it to be safe)
    const len = Math.hypot(lx_x, lx_y);
    lx = [lx_x / len, lx_y / len, lx_z / len];
  }

  // Local Y = N x Local X
  const ly = [
    ny * lx[2] - nz * lx[1],
    nz * lx[0] - nx * lx[2],
    nx * lx[1] - ny * lx[0]
  ];

  return {
    plane_origin: [0.0, 0.0, zOrigin],
    unit_normal: [nx, ny, nz],
    angle_pair: [thetaDeg, phiDeg],
    angle_units: 'degrees' as AngleUnit,
    rotation_convention: 'BC_TABLE' as RotationConvention, // generic assumption for the UI mapping
    local_x: [lx[0], lx[1], lx[2]],
    local_y: [ly[0], ly[1], ly[2]],
    source_frame: 'canonical'
  };
}
