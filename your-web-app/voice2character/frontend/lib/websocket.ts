/**
 * WebSocket管理モジュール
 * ジョブの進捗をリアルタイムで受信するためのWebSocket接続を管理する
 */

import type { ProgressMessage } from '@/types';

/** WebSocket接続状態 */
export type ConnectionState = 'connecting' | 'connected' | 'disconnected' | 'error';

/** 進捗更新コールバック型 */
type ProgressCallback = (message: ProgressMessage) => void;

/** 接続状態変更コールバック型 */
type StateCallback = (state: ConnectionState) => void;

/**
 * WebSocket管理クラス
 * 自動再接続機能とバックオフ付きのWebSocket接続を提供する
 */
export class WebSocketManager {
  /** WebSocketインスタンス */
  private ws: WebSocket | null = null;

  /** 進捗更新コールバック一覧 */
  private progressCallbacks: ProgressCallback[] = [];

  /** 接続状態変更コールバック一覧 */
  private stateCallbacks: StateCallback[] = [];

  /** 現在の接続状態 */
  private _state: ConnectionState = 'disconnected';

  /** 再接続試行回数 */
  private reconnectAttempts: number = 0;

  /** 最大再接続試行回数 */
  private maxReconnectAttempts: number = 10;

  /** 再接続タイマーID */
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  /** 接続先のジョブID */
  private currentJobId: string | null = null;

  /** 意図的な切断フラグ */
  private intentionalDisconnect: boolean = false;

  /** 現在の接続状態を取得 */
  get state(): ConnectionState {
    return this._state;
  }

  /**
   * 接続状態を更新し、コールバックを呼び出す
   */
  private setState(newState: ConnectionState): void {
    this._state = newState;
    this.stateCallbacks.forEach((cb) => cb(newState));
  }

  /**
   * WebSocketのURLを構築する
   * ブラウザのプロトコル（http/https）に応じてws/wssを使い分ける
   */
  private getWsUrl(jobId: string): string {
    if (typeof window === 'undefined') return '';
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    return `${protocol}//${host}/ws/${jobId}`;
  }

  /**
   * 再接続の待機時間を計算（指数バックオフ）
   * 試行回数に応じて待機時間を段階的に増やす
   *
   * @returns 待機時間（ミリ秒）
   */
  private getReconnectDelay(): number {
    // 基本待機時間: 1秒、最大待機時間: 30秒
    const baseDelay = 1000;
    const maxDelay = 30000;
    const delay = Math.min(baseDelay * Math.pow(2, this.reconnectAttempts), maxDelay);
    // ジッター（ランダムな揺らぎ）を追加して接続集中を回避
    return delay + Math.random() * 1000;
  }

  /**
   * 指定されたジョブIDのWebSocket接続を開始する
   *
   * @param jobId - 接続先のジョブID
   */
  connect(jobId: string): void {
    // 既存の接続をクリーンアップ
    this.disconnect();

    this.currentJobId = jobId;
    this.intentionalDisconnect = false;
    this.reconnectAttempts = 0;
    this.setState('connecting');

    this.createConnection(jobId);
  }

  /**
   * WebSocket接続を作成する内部メソッド
   */
  private createConnection(jobId: string): void {
    const url = this.getWsUrl(jobId);
    if (!url) return;

    try {
      this.ws = new WebSocket(url);

      // 接続成功ハンドラ
      this.ws.onopen = () => {
        this.reconnectAttempts = 0;
        this.setState('connected');
      };

      // メッセージ受信ハンドラ
      this.ws.onmessage = (event: MessageEvent) => {
        try {
          const message: ProgressMessage = JSON.parse(event.data);
          this.progressCallbacks.forEach((cb) => cb(message));
        } catch (error) {
          console.error('WebSocketメッセージの解析に失敗:', error);
        }
      };

      // 接続クローズハンドラ
      this.ws.onclose = () => {
        this.ws = null;
        if (!this.intentionalDisconnect) {
          this.setState('disconnected');
          this.attemptReconnect();
        } else {
          this.setState('disconnected');
        }
      };

      // エラーハンドラ
      this.ws.onerror = () => {
        this.setState('error');
      };
    } catch (error) {
      console.error('WebSocket接続の作成に失敗:', error);
      this.setState('error');
      this.attemptReconnect();
    }
  }

  /**
   * 自動再接続を試行する
   */
  private attemptReconnect(): void {
    if (this.intentionalDisconnect || !this.currentJobId) return;
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.warn('WebSocket再接続の最大試行回数に到達しました');
      this.setState('error');
      return;
    }

    this.reconnectAttempts++;
    const delay = this.getReconnectDelay();

    this.reconnectTimer = setTimeout(() => {
      if (this.currentJobId && !this.intentionalDisconnect) {
        this.setState('connecting');
        this.createConnection(this.currentJobId);
      }
    }, delay);
  }

  /**
   * WebSocket接続を切断する
   */
  disconnect(): void {
    this.intentionalDisconnect = true;
    this.currentJobId = null;

    // 再接続タイマーをクリア
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    // WebSocket接続を閉じる
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    this.setState('disconnected');
  }

  /**
   * 進捗更新コールバックを登録する
   *
   * @param callback - 進捗メッセージ受信時に呼び出されるコールバック
   * @returns コールバック登録解除関数
   */
  onProgress(callback: ProgressCallback): () => void {
    this.progressCallbacks.push(callback);
    // 登録解除関数を返す
    return () => {
      this.progressCallbacks = this.progressCallbacks.filter((cb) => cb !== callback);
    };
  }

  /**
   * 接続状態変更コールバックを登録する
   *
   * @param callback - 接続状態変更時に呼び出されるコールバック
   * @returns コールバック登録解除関数
   */
  onStateChange(callback: StateCallback): () => void {
    this.stateCallbacks.push(callback);
    return () => {
      this.stateCallbacks = this.stateCallbacks.filter((cb) => cb !== callback);
    };
  }

  /**
   * すべてのコールバックを解除し、リソースをクリーンアップする
   */
  destroy(): void {
    this.disconnect();
    this.progressCallbacks = [];
    this.stateCallbacks = [];
  }
}

/** シングルトンインスタンスを生成するファクトリ関数 */
export function createWebSocketManager(): WebSocketManager {
  return new WebSocketManager();
}
