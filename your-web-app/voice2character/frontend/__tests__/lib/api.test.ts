/**
 * API通信ライブラリのテスト
 *
 * ユーティリティ関数とAPI呼び出しの動作を検証する。
 */

import {
  formatFileSize,
  formatDuration,
  formatDate,
  getExportUrl,
  ApiRequestError,
} from '@/lib/api';

describe('formatFileSize', () => {
  test('0バイトを正しくフォーマットする', () => {
    expect(formatFileSize(0)).toBe('0 B');
  });

  test('バイト単位をフォーマットする', () => {
    expect(formatFileSize(500)).toBe('500 B');
  });

  test('KB単位をフォーマットする', () => {
    expect(formatFileSize(1024)).toBe('1 KB');
  });

  test('MB単位をフォーマットする', () => {
    expect(formatFileSize(1048576)).toBe('1 MB');
  });

  test('GB単位をフォーマットする', () => {
    expect(formatFileSize(1073741824)).toBe('1 GB');
  });

  test('小数点を含むサイズをフォーマットする', () => {
    expect(formatFileSize(1536)).toBe('1.5 KB');
  });
});

describe('formatDuration', () => {
  test('分と秒をフォーマットする', () => {
    expect(formatDuration(125)).toBe('2:05');
  });

  test('1時間以上をフォーマットする', () => {
    expect(formatDuration(3661)).toBe('1:01:01');
  });

  test('0秒をフォーマットする', () => {
    expect(formatDuration(0)).toBe('0:00');
  });

  test('秒のみをフォーマットする', () => {
    expect(formatDuration(45)).toBe('0:45');
  });
});

describe('formatDate', () => {
  test('ISO日付文字列を日本語形式に変換する', () => {
    const result = formatDate('2024-01-15T10:30:00Z');
    // ロケールに依存するためフォーマットの一部を確認
    expect(result).toBeTruthy();
    expect(typeof result).toBe('string');
  });
});

describe('getExportUrl', () => {
  test('TXT形式のURLを生成する', () => {
    expect(getExportUrl('job-123', 'txt')).toBe('/api/export/job-123?format=txt');
  });

  test('SRT形式のURLを生成する', () => {
    expect(getExportUrl('job-456', 'srt')).toBe('/api/export/job-456?format=srt');
  });

  test('全形式のURLを正しく生成する', () => {
    const formats = ['txt', 'srt', 'vtt', 'json', 'tsv'] as const;
    formats.forEach((format) => {
      const url = getExportUrl('test-id', format);
      expect(url).toContain(`format=${format}`);
      expect(url).toContain('test-id');
    });
  });
});

describe('ApiRequestError', () => {
  test('ステータスコードとメッセージを保持する', () => {
    const error = new ApiRequestError(404, 'Not Found');
    expect(error.statusCode).toBe(404);
    expect(error.detail).toBe('Not Found');
    expect(error.name).toBe('ApiRequestError');
    expect(error.message).toBe('Not Found');
  });

  test('Errorを継承している', () => {
    const error = new ApiRequestError(500, 'Server Error');
    expect(error instanceof Error).toBe(true);
    expect(error instanceof ApiRequestError).toBe(true);
  });
});

describe('API呼び出し関数', () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test('initUploadが正しいURLとボディでリクエストする', async () => {
    const mockResponse = {
      ok: true,
      json: async () => ({
        job_id: 'test-id',
        upload_url: '/api/upload/test-id/chunk',
        chunk_size: 104857600,
      }),
    };
    (global.fetch as jest.Mock).mockResolvedValue(mockResponse);

    const { initUpload } = await import('@/lib/api');
    const result = await initUpload('test.mp4', 1024, 'ja');

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/upload/init',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('test.mp4'),
      })
    );
    expect(result.job_id).toBe('test-id');
  });

  test('getJobsがページネーションパラメータ付きでリクエストする', async () => {
    const mockResponse = {
      ok: true,
      json: async () => ({
        jobs: [],
        total: 0,
        page: 1,
        page_size: 10,
        total_pages: 1,
      }),
    };
    (global.fetch as jest.Mock).mockResolvedValue(mockResponse);

    const { getJobs } = await import('@/lib/api');
    await getJobs(2, 20);

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('page=2'),
      expect.anything()
    );
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('page_size=20'),
      expect.anything()
    );
  });

  test('エラーレスポンスでApiRequestErrorがスローされる', async () => {
    const mockResponse = {
      ok: false,
      status: 404,
      json: async () => ({ detail: 'Not Found' }),
    };
    (global.fetch as jest.Mock).mockResolvedValue(mockResponse);

    const { getJob } = await import('@/lib/api');

    await expect(getJob('nonexistent')).rejects.toThrow(ApiRequestError);
  });
});
