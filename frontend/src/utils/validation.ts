import type { JobMode } from '../api/models';

export interface ValidationInput {
  file: File | null;
  machineProfileId: string;
  modelScale: number;
  layerHeight: number;
  infillDensity: number;
  rotX: number;
  rotY: number;
  rotZ: number;
  jobMode: JobMode;
  indexedPlanes: Array<{ z: number; theta: number; phi: number }>;
}

export function validateSettings(input: ValidationInput): string | null {
  if (!input.file) return "NO_FILE_SELECTED";
  if (!input.machineProfileId) return "NO_MACHINE_PROFILE_SELECTED";
  if (input.modelScale <= 0) return "INVALID_SCALE";
  if (input.layerHeight <= 0 || input.layerHeight > 2.0) return "INVALID_LAYER_HEIGHT";
  if (input.infillDensity < 0 || input.infillDensity > 100) return "INVALID_INFILL_DENSITY";
  if (input.rotX < -360 || input.rotX > 360) return "INVALID_ROTATION_X";
  if (input.rotY < -360 || input.rotY > 360) return "INVALID_ROTATION_Y";
  if (input.rotZ < -360 || input.rotZ > 360) return "INVALID_ROTATION_Z";

  if (input.jobMode === 'indexed_multidirectional') {
    if (input.indexedPlanes.length === 0) return "NO_PLANES_DEFINED";
    if (input.indexedPlanes[0].theta !== 0) return "INITIAL_PLANE_MUST_BE_HORIZONTAL";
    for (let i = 1; i < input.indexedPlanes.length; i++) {
      if (input.indexedPlanes[i].theta === 0) return "INVALID_PLANE_THETA_ZERO";
    }
  }

  return null;
}
