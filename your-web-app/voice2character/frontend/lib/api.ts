/**
 * API通信ライブラリ
 * バックエンドとの通信を一元管理するモジュール
 */

import type {
  Job,
  Transcription,
  JobListResponse,
  UploadInitResponse,
  ChunkUploadResponse,
  UploadCompleteResponse,
  ExportFormat,
  ApiError,
  SystemInfo,
} from '@/types';

/** APIのベースURL（プロキシ経由のため相対パス） */
const BASE_URL = '/api';

/**
 * APIエラークラス
 * バックエンドからのエラーレスポンスをラップする
 */
export class ApiRequestError extends Error {
  public statusCode: number;
  public detail: string;

  constructor(statusCode: number, detail: string) {
    super(detail);
    this.name = 'ApiRequestError';
    this.statusCode = statusCode;
    this.detail = detail;
  }
}

/**
 * 共通のレスポンスハンドラ
 * HTTPレスポンスを検証し、JSONを返す
 */
async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = 'リクエストに失敗しました';
    try {
      const errorBody: ApiError = await response.json();
      detail = errorBody.detail || detail;
    } catch {
      // JSONパースに失敗した場合はデフォルトメッセージを使用
    }
    throw new ApiRequestError(response.status, detail);
  }
  return response.json();
}

/**
 * 共通のリクエストヘッダーを取得
 */
function getHeaders(): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  };
}

// ============================================
// アップロード関連API
// ============================================

/**
 * アップロードの初期化
 * ファイル情報を送信してジョブIDを取得する
 *
 * @param fileName - ファイル名
 * @param fileSize - ファイルサイズ（バイト）
 * @param language - 言語コード（例: "ja", "en", "auto"）
 * @param whisperModel - Whisperモデル名（オプション）
 * @param whisperDevice - 推論デバイス（オプション）
 * @returns ジョブIDとアップロードIDを含むレスポンス
 */
export async function initUpload(
  fileName: string,
  fileSize: number,
  language: string = 'auto',
  whisperModel: string | null = null,
  whisperDevice: string | null = null,
): Promise<UploadInitResponse> {
  // リクエストボディの構築（null以外のフィールドのみ含める）
  const body: Record<string, unknown> = {
    file_name: fileName,
    file_size: fileSize,
    language,
  };
  if (whisperModel) body.whisper_model = whisperModel;
  if (whisperDevice) body.whisper_device = whisperDevice;

  const response = await fetch(`${BASE_URL}/upload/init`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(body),
  });
  return handleResponse<UploadInitResponse>(response);
}

/**
 * チャンクデータの送信
 * 分割されたファイルデータを1チャンクずつ送信する
 *
 * @param jobId - ジョブID
 * @param chunkIndex - チャンクのインデックス（0始まり）
 * @param totalChunks - 総チャンク数
 * @param chunk - チャンクデータ（Blob）
 * @param onProgress - アップロード進捗コールバック（オプション）
 * @returns チャンク受信確認レスポンス
 */
export async function uploadChunk(
  jobId: string,
  chunkIndex: number,
  totalChunks: number,
  chunk: Blob,
  onProgress?: (loaded: number, total: number) => void
): Promise<ChunkUploadResponse> {
  const formData = new FormData();
  formData.append('file', chunk);  // バックエンドのUploadFileパラメータ名に合わせる

  const url = `${BASE_URL}/upload/${jobId}/chunk?chunk_index=${chunkIndex}&total_chunks=${totalChunks}`;

  // XMLHttpRequestを使用してアップロード進捗を追跡
  if (onProgress) {
    return new Promise<ChunkUploadResponse>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', url);

      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          onProgress(event.loaded, event.total);
        }
      };

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            resolve(JSON.parse(xhr.responseText));
          } catch {
            reject(new ApiRequestError(xhr.status, 'レスポンスの解析に失敗しました'));
          }
        } else {
          let detail = 'チャンクのアップロードに失敗しました';
          try {
            const errorBody = JSON.parse(xhr.responseText);
            detail = errorBody.detail || detail;
          } catch {
            // パースエラーは無視
          }
          reject(new ApiRequestError(xhr.status, detail));
        }
      };

      xhr.onerror = () => {
        reject(new ApiRequestError(0, 'ネットワークエラーが発生しました'));
      };

      xhr.onabort = () => {
        reject(new ApiRequestError(0, 'アップロードがキャンセルされました'));
      };

      xhr.send(formData);
    });
  }

  // 進捗追跡が不要な場合はfetchを使用
  const response = await fetch(url, {
    method: 'POST',
    body: formData,
  });
  return handleResponse<ChunkUploadResponse>(response);
}

/**
 * アップロードの完了通知
 * 全チャンクの送信が完了したことをバックエンドに通知する
 *
 * @param jobId - ジョブID
 * @param totalChunks - 総チャンク数
 * @returns アップロード完了レスポンス
 */
export async function completeUpload(
  jobId: string,
  totalChunks: number
): Promise<UploadCompleteResponse> {
  const response = await fetch(`${BASE_URL}/upload/${jobId}/complete?total_chunks=${totalChunks}`, {
    method: 'POST',
    headers: getHeaders(),
  });
  return handleResponse<UploadCompleteResponse>(response);
}

// ============================================
// ジョブ関連API
// ============================================

/**
 * ジョブ一覧を取得
 *
 * @param page - ページ番号（1始まり）
 * @param pageSize - 1ページあたりの件数
 * @returns ジョブ一覧レスポンス
 */
export async function getJobs(
  page: number = 1,
  pageSize: number = 10
): Promise<JobListResponse> {
  const params = new URLSearchParams({
    page: page.toString(),
    page_size: pageSize.toString(),
  });
  const response = await fetch(`${BASE_URL}/jobs?${params}`, {
    headers: getHeaders(),
  });
  return handleResponse<JobListResponse>(response);
}

/**
 * ジョブの詳細情報を取得
 *
 * @param jobId - ジョブID
 * @returns ジョブ詳細情報
 */
export async function getJob(jobId: string): Promise<Job> {
  const response = await fetch(`${BASE_URL}/jobs/${jobId}`, {
    headers: getHeaders(),
  });
  return handleResponse<Job>(response);
}

/**
 * 文字起こし結果を取得
 *
 * @param jobId - ジョブID
 * @returns 文字起こし結果（セグメント付き）
 */
export async function getTranscription(jobId: string): Promise<Transcription> {
  const response = await fetch(`${BASE_URL}/jobs/${jobId}/transcription`, {
    headers: getHeaders(),
  });
  return handleResponse<Transcription>(response);
}

/**
 * ジョブを削除
 *
 * @param jobId - ジョブID
 */
export async function deleteJob(jobId: string): Promise<void> {
  const response = await fetch(`${BASE_URL}/jobs/${jobId}`, {
    method: 'DELETE',
    headers: getHeaders(),
  });
  if (!response.ok) {
    let detail = 'ジョブの削除に失敗しました';
    try {
      const errorBody: ApiError = await response.json();
      detail = errorBody.detail || detail;
    } catch {
      // パースエラーは無視
    }
    throw new ApiRequestError(response.status, detail);
  }
}

// ============================================
// エクスポート関連API
// ============================================

/**
 * エクスポート用URLを取得
 *
 * @param jobId - ジョブID
 * @param format - エクスポート形式
 * @returns ダウンロード用URL
 */
export function getExportUrl(jobId: string, format: ExportFormat): string {
  return `${BASE_URL}/export/${jobId}?format=${format}`;
}

// ============================================
// システム情報API
// ============================================

/**
 * サーバーのシステム情報を取得
 * CPU、RAM、GPU情報とWhisperモデル推奨設定を返す
 *
 * @returns システム情報レスポンス
 */
export async function getSystemInfo(): Promise<SystemInfo> {
  const response = await fetch(`${BASE_URL}/system/info`, {
    headers: getHeaders(),
  });
  return handleResponse<SystemInfo>(response);
}

// ============================================
// ユーティリティ関数
// ============================================

/**
 * ファイルサイズを人間が読みやすい形式に変換
 *
 * @param bytes - バイト数
 * @returns フォーマットされたサイズ文字列
 */
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}

/**
 * 秒数を時間:分:秒の形式に変換
 *
 * @param seconds - 秒数
 * @returns フォーマットされた時間文字列
 */
export function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) {
    return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  }
  return `${m}:${s.toString().padStart(2, '0')}`;
}

/**
 * 日付文字列を日本語形式に変換
 *
 * @param dateStr - ISO形式の日付文字列
 * @returns 日本語形式の日付文字列
 */
export function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleString('ja-JP', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}
