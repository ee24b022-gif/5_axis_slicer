import { describe, it, expect } from 'vitest';
import { validateSettings } from '../utils/validation';
import type { ValidationInput } from '../utils/validation';

function makeValidInput(overrides: Partial<ValidationInput> = {}): ValidationInput {
  return {
    file: new File(['dummy'], 'test.stl', { type: 'application/octet-stream' }),
    machineProfileId: 'profile-123',
    modelScale: 1.0,
    layerHeight: 0.2,
    infillDensity: 20,
    rotX: 0,
    rotY: 0,
    rotZ: 0,
    jobMode: 'three_axis',
    indexedPlanes: [{ z: 0, theta: 0, phi: 0 }],
    ...overrides,
  };
}

describe('validateSettings', () => {
  it('returns null for valid three_axis settings', () => {
    expect(validateSettings(makeValidInput())).toBeNull();
  });

  it('returns NO_FILE_SELECTED when file is null', () => {
    expect(validateSettings(makeValidInput({ file: null }))).toBe('NO_FILE_SELECTED');
  });

  it('returns NO_MACHINE_PROFILE_SELECTED when profileId is empty', () => {
    expect(validateSettings(makeValidInput({ machineProfileId: '' }))).toBe('NO_MACHINE_PROFILE_SELECTED');
  });

  it('returns INVALID_SCALE when scale is zero', () => {
    expect(validateSettings(makeValidInput({ modelScale: 0 }))).toBe('INVALID_SCALE');
  });

  it('returns INVALID_SCALE when scale is negative', () => {
    expect(validateSettings(makeValidInput({ modelScale: -1 }))).toBe('INVALID_SCALE');
  });

  it('returns INVALID_LAYER_HEIGHT when height is zero', () => {
    expect(validateSettings(makeValidInput({ layerHeight: 0 }))).toBe('INVALID_LAYER_HEIGHT');
  });

  it('returns INVALID_LAYER_HEIGHT when height exceeds 2.0', () => {
    expect(validateSettings(makeValidInput({ layerHeight: 2.5 }))).toBe('INVALID_LAYER_HEIGHT');
  });

  it('returns INVALID_INFILL_DENSITY when density is negative', () => {
    expect(validateSettings(makeValidInput({ infillDensity: -1 }))).toBe('INVALID_INFILL_DENSITY');
  });

  it('returns INVALID_INFILL_DENSITY when density exceeds 100', () => {
    expect(validateSettings(makeValidInput({ infillDensity: 101 }))).toBe('INVALID_INFILL_DENSITY');
  });

  it('returns INVALID_ROTATION_X when rotation exceeds bounds', () => {
    expect(validateSettings(makeValidInput({ rotX: 400 }))).toBe('INVALID_ROTATION_X');
    expect(validateSettings(makeValidInput({ rotX: -400 }))).toBe('INVALID_ROTATION_X');
  });

  it('returns INVALID_ROTATION_Y when rotation exceeds bounds', () => {
    expect(validateSettings(makeValidInput({ rotY: 400 }))).toBe('INVALID_ROTATION_Y');
  });

  it('returns INVALID_ROTATION_Z when rotation exceeds bounds', () => {
    expect(validateSettings(makeValidInput({ rotZ: -500 }))).toBe('INVALID_ROTATION_Z');
  });

  it('accepts boundary values', () => {
    expect(validateSettings(makeValidInput({ layerHeight: 2.0 }))).toBeNull();
    expect(validateSettings(makeValidInput({ infillDensity: 0 }))).toBeNull();
    expect(validateSettings(makeValidInput({ infillDensity: 100 }))).toBeNull();
    expect(validateSettings(makeValidInput({ rotX: 360 }))).toBeNull();
    expect(validateSettings(makeValidInput({ rotX: -360 }))).toBeNull();
  });

  // Indexed multidirectional mode
  it('returns NO_PLANES_DEFINED for indexed mode with empty planes', () => {
    expect(validateSettings(makeValidInput({
      jobMode: 'indexed_multidirectional',
      indexedPlanes: [],
    }))).toBe('NO_PLANES_DEFINED');
  });

  it('returns INITIAL_PLANE_MUST_BE_HORIZONTAL when first plane theta != 0', () => {
    expect(validateSettings(makeValidInput({
      jobMode: 'indexed_multidirectional',
      indexedPlanes: [{ z: 0, theta: 45, phi: 0 }],
    }))).toBe('INITIAL_PLANE_MUST_BE_HORIZONTAL');
  });

  it('returns INVALID_PLANE_THETA_ZERO when non-first plane has theta=0', () => {
    expect(validateSettings(makeValidInput({
      jobMode: 'indexed_multidirectional',
      indexedPlanes: [
        { z: 0, theta: 0, phi: 0 },
        { z: 50, theta: 0, phi: 0 },
      ],
    }))).toBe('INVALID_PLANE_THETA_ZERO');
  });

  it('returns null for valid indexed multidirectional settings', () => {
    expect(validateSettings(makeValidInput({
      jobMode: 'indexed_multidirectional',
      indexedPlanes: [
        { z: 0, theta: 0, phi: 0 },
        { z: 50, theta: 45, phi: 0 },
      ],
    }))).toBeNull();
  });
});
