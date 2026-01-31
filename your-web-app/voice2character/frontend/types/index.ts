/**
 * 型定義ファイル
 * アプリケーション全体で使用する共通の型を定義
 */

/** ジョブのステータス一覧 */
export type JobStatus =
  | 'uploading'
  | 'queued'
  | 'extracting'
  | 'transcribing'
  | 'completed'
  | 'failed';

/** ジョブ情報 */
export interface Job {
  id: string;
  file_name: string;
  file_size: number;
  duration: number | null;
  status: JobStatus;
  progress: number;
  error_message: string | null;
  language: string;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

/** 文字起こしセグメント */
export interface TranscriptionSegment {
  id: number;
  segment_index: number;
  start_time: number;
  end_time: number;
  text: string;
  confidence: number | null;
}

/** 文字起こし結果全体 */
export interface Transcription {
  job_id: string;
  file_name: string;
  duration: number | null;
  language: string;
  status: string;
  segments: TranscriptionSegment[];
  full_text: string;
}

/** アップロード進捗情報 */
export interface UploadProgress {
  loaded: number;
  total: number;
  percentage: number;
  speed: number; // バイト/秒
  remainingTime: number; // 秒
}

/** ジョブ一覧レスポンス */
export interface JobListResponse {
  jobs: Job[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/** エクスポート形式 */
export type ExportFormat = 'txt' | 'srt' | 'vtt' | 'json' | 'tsv';

/** WebSocket進捗メッセージ */
export interface ProgressMessage {
  job_id: string;
  status: JobStatus;
  progress: number;
  message?: string;
  error_message?: string;
}

/** APIエラーレスポンス */
export interface ApiError {
  detail: string;
  status_code: number;
}

/** アップロード初期化レスポンス */
export interface UploadInitResponse {
  job_id: string;
  upload_url: string;
  chunk_size: number;
}

/** チャンクアップロードレスポンス */
export interface ChunkUploadResponse {
  status: string;
  chunk_index: number;
  total_chunks: number;
  message: string;
}

/** アップロード完了レスポンス - バックエンドのJobResponseと同じ */
export type UploadCompleteResponse = Job;
