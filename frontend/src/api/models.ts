// Types
export type UserRole =
  | 'user'
  | 'operator'
  | 'validator'
  | 'admin'
  | 'service';

export type JobStatus =
  | 'pending'
  | 'running'
  | 'complete'
  | 'failed'
  | 'partial'
  | 'cancelled';

export type JobMode =
  | 'three_axis'
  | 'indexed_multidirectional';

export type RotationConvention =
  | 'AC_TABLE'
  | 'BC_TABLE'
  | 'AB_HEAD';

export type AngleUnit =
  | 'degrees'
  | 'radians';

export type MeshFormat =
  | 'stl_binary';

export type DiagnosticSeverity =
  | 'info'
  | 'warning'
  | 'error'
  | 'critical';

export type DiagnosticStatus =
  | 'pass'
  | 'warning'
  | 'fail'
  | 'not_implemented';

export type JobStage =
  | 'mesh_validation'
  | 'canonical_frame'
  | 'chunk_construction'
  | 'sectioning'
  | 'polygon_processing'
  | 'path_ordering'
  | 'validation'
  | 'post_processing'
  | 'artifact_persistence';

export type ExportStatus =
  | 'pending'
  | 'ready'
  | 'blocked'
  | 'failed'
  | 'revoked';

// Models
export interface PreviewLayerResponse {
  id: string;
  layer_idx: number;
  z_height: number;
  thickness: number;
  is_support: boolean;
  preview_uri: string | null;
}

export interface PreviewResponse {
  job_id: string;
  layers: PreviewLayerResponse[];
}

export interface DiagnosticResponse {
  id: string;
  job_id: string;
  chunk_id: string | null;
  layer_id: string | null;
  stage: JobStage;
  severity: DiagnosticSeverity;
  status: DiagnosticStatus;
  code: string;
  message: string;
  details: Record<string, any> | null;
  created_at: string;
}

export interface MeshResponse {
  id: string;
  uploader_id: string;
  content_hash: string;
  format: MeshFormat;
  size_bytes: number;
  triangle_count: number;
  bound_min_x: number;
  bound_min_y: number;
  bound_min_z: number;
  bound_max_x: number;
  bound_max_y: number;
  bound_max_z: number;
}

export interface JobCreateRequest {
  mesh_id: string;
  machine_profile_id: string;
  mode: JobMode;
  settings: Record<string, any>;
}

export interface JobResponse {
  id: string;
  creator_id: string;
  mesh_id: string;
  machine_profile_id: string;
  mode: JobMode;
  status: JobStatus;
  progress: number;
  checkpoint_data: Record<string, any> | null;
  started_at: string | null;
  completed_at: string | null;
  cancellation_requested_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExportResponse {
  id: string;
  job_id: string;
  creator_id: string;
  dialect: string;
  status: ExportStatus;
  storage_uri: string | null;
  content_hash: string | null;
  size_bytes: number | null;
  export_metadata: Record<string, any> | null;
  created_at: string;
  updated_at: string;
}

export interface MachineProfileResponse {
  id: string;
  name: string;
  revision: number;
  dialect: string;
  contract: Record<string, any>;
  limits: Record<string, any>;
  is_active: boolean;
  author_id: string;
  created_at: string;
  updated_at: string;
}

export interface SlicePlane {
  plane_origin: [number, number, number];
  unit_normal: [number, number, number];
  angle_pair: [number, number];
  angle_units: AngleUnit;
  rotation_convention: RotationConvention;
  local_x: [number, number, number];
  local_y: [number, number, number];
  source_frame: string;
}

export interface StageProgressEvent {
  job_id: string;
  stage: JobStage;
  progress: number;
  chunk_idx?: number | null;
  layer_idx?: number | null;
  severity?: DiagnosticSeverity | null;
  status?: DiagnosticStatus | null;
  code?: string | null;
  message?: string | null;
}
