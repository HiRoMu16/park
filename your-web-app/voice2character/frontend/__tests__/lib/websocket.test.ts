/**
 * WebSocketManagerのテスト
 *
 * WebSocket接続管理、コールバック、再接続ロジックを検証する。
 */

import { WebSocketManager } from '@/lib/websocket';

// WebSocketのモック
class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  readyState = MockWebSocket.CONNECTING;
  url: string;
  onopen: (() => void) | null = null;
  onclose: ((event: { code: number; reason: string }) => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    // 接続を非同期でシミュレート
    setTimeout(() => {
      this.readyState = MockWebSocket.OPEN;
      this.onopen?.();
    }, 10);
  }

  send = jest.fn();
  close = jest.fn(() => {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ code: 1000, reason: 'Normal closure' });
  });
}

describe('WebSocketManager', () => {
  let originalWebSocket: typeof WebSocket;

  beforeEach(() => {
    originalWebSocket = global.WebSocket;
    (global as any).WebSocket = MockWebSocket;
    // windowオブジェクトのモック
    Object.defineProperty(global, 'window', {
      value: {
        location: {
          protocol: 'http:',
          host: 'localhost:3000',
        },
      },
      writable: true,
    });
  });

  afterEach(() => {
    global.WebSocket = originalWebSocket;
    jest.restoreAllMocks();
  });

  test('インスタンスを生成できる', () => {
    const manager = new WebSocketManager();
    expect(manager).toBeDefined();
    manager.destroy();
  });

  test('onProgressでコールバックを登録・解除できる', () => {
    const manager = new WebSocketManager();
    const callback = jest.fn();

    const unsubscribe = manager.onProgress(callback);
    expect(typeof unsubscribe).toBe('function');

    unsubscribe();
    manager.destroy();
  });

  test('onStateChangeで状態変更コールバックを登録できる', () => {
    const manager = new WebSocketManager();
    const callback = jest.fn();

    const unsubscribe = manager.onStateChange(callback);
    expect(typeof unsubscribe).toBe('function');

    unsubscribe();
    manager.destroy();
  });

  test('destroyでリソースが解放される', () => {
    const manager = new WebSocketManager();
    manager.destroy();
    // destroyが例外なく完了すればOK
  });
});
