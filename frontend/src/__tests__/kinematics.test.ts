import { describe, it, expect } from 'vitest';
import { computeSlicePlane } from '../utils/kinematics';

function dot(a: number[], b: number[]): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function magnitude(v: number[]): number {
  return Math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
}

describe('computeSlicePlane', () => {
  it('produces correct horizontal plane at theta=0', () => {
    const plane = computeSlicePlane(10.0, 0, 0);

    expect(plane.plane_origin).toEqual([0.0, 0.0, 10.0]);
    expect(plane.unit_normal[0]).toBeCloseTo(0, 10);
    expect(plane.unit_normal[1]).toBeCloseTo(0, 10);
    expect(plane.unit_normal[2]).toBeCloseTo(1, 10);
    expect(plane.local_x).toEqual([1.0, 0.0, 0.0]);
    expect(plane.angle_pair).toEqual([0, 0]);
    expect(plane.angle_units).toBe('degrees');
    expect(plane.rotation_convention).toBe('BC_TABLE');
    expect(plane.source_frame).toBe('canonical');
  });

  it('produces correct 45° tilted plane', () => {
    const plane = computeSlicePlane(5.0, 45, 0);

    // Normal for theta=45, phi=0: [sin(45)*cos(0), sin(45)*sin(0), cos(45)]
    const expected_nx = Math.sin(Math.PI / 4);
    const expected_nz = Math.cos(Math.PI / 4);

    expect(plane.unit_normal[0]).toBeCloseTo(expected_nx, 6);
    expect(plane.unit_normal[1]).toBeCloseTo(0, 6);
    expect(plane.unit_normal[2]).toBeCloseTo(expected_nz, 6);

    // Normal should be unit length
    const normalLen = magnitude(Array.from(plane.unit_normal));
    expect(normalLen).toBeCloseTo(1.0, 10);
  });

  it('maintains orthogonality between local_x, local_y, and normal', () => {
    const testCases = [
      { z: 0, theta: 0, phi: 0 },
      { z: 5, theta: 45, phi: 0 },
      { z: 10, theta: 30, phi: 90 },
      { z: 0, theta: 60, phi: 45 },
      { z: 0, theta: 90, phi: 180 },
    ];

    for (const tc of testCases) {
      const plane = computeSlicePlane(tc.z, tc.theta, tc.phi);
      const n = Array.from(plane.unit_normal);
      const lx = Array.from(plane.local_x);
      const ly = Array.from(plane.local_y);

      // dot(local_x, normal) ≈ 0
      expect(dot(lx, n)).toBeCloseTo(0, 6);
      // dot(local_y, normal) ≈ 0
      expect(dot(ly, n)).toBeCloseTo(0, 6);
      // dot(local_x, local_y) ≈ 0
      expect(dot(lx, ly)).toBeCloseTo(0, 6);

      // All should be unit vectors
      expect(magnitude(n)).toBeCloseTo(1.0, 6);
      expect(magnitude(lx)).toBeCloseTo(1.0, 6);
      expect(magnitude(ly)).toBeCloseTo(1.0, 6);
    }
  });

  it('sets correct angle metadata', () => {
    const plane = computeSlicePlane(7.5, 30, 60);
    expect(plane.angle_pair).toEqual([30, 60]);
    expect(plane.angle_units).toBe('degrees');
    expect(plane.rotation_convention).toBe('BC_TABLE');
  });
});
