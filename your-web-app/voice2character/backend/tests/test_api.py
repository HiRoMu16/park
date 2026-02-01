"""
API統合テスト

httpx AsyncClientを使用してFastAPIエンドポイントをテストする。
テスト用SQLiteデータベースを使用する。
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient


class TestHealthCheck:
    """ヘルスチェックエンドポイントのテスト"""

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("healthy", "degraded")
        assert data["app"] == "Voice2Character"
        assert "version" in data


class TestUploadInit:
    """アップロード初期化エンドポイントのテスト"""

    @pytest.mark.asyncio
    async def test_init_upload_success(self, client: AsyncClient):
        """正常なアップロード初期化"""
        response = await client.post(
            "/api/upload/init",
            json={
                "file_name": "test_video.mp4",
                "file_size": 1024 * 1024,
                "language": "ja",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert "job_id" in data
        assert "upload_url" in data
        assert "chunk_size" in data

    @pytest.mark.asyncio
    async def test_init_upload_invalid_extension(self, client: AsyncClient):
        """許可されていないファイル拡張子で400エラー"""
        response = await client.post(
            "/api/upload/init",
            json={
                "file_name": "test.exe",
                "file_size": 1024,
                "language": "ja",
            },
        )
        assert response.status_code == 400
        assert "許可されていないファイル形式" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_init_upload_oversized(self, client: AsyncClient):
        """ファイルサイズ上限超過で413エラー"""
        response = await client.post(
            "/api/upload/init",
            json={
                "file_name": "big.mp4",
                "file_size": 10 * 1024 * 1024 * 1024,  # 10GB
                "language": "ja",
            },
        )
        assert response.status_code == 413

    @pytest.mark.asyncio
    async def test_init_upload_with_model_selection(self, client: AsyncClient):
        """モデル・デバイス指定付きのアップロード初期化"""
        response = await client.post(
            "/api/upload/init",
            json={
                "file_name": "test.mp4",
                "file_size": 1024,
                "language": "ja",
                "whisper_model": "small",
                "whisper_device": "cpu",
            },
        )
        assert response.status_code == 201


class TestJobsApi:
    """ジョブ管理APIのテスト"""

    @pytest.mark.asyncio
    async def test_list_jobs_empty(self, client: AsyncClient):
        """ジョブが無い場合の一覧取得"""
        response = await client.get("/api/jobs")
        assert response.status_code == 200
        data = response.json()
        assert data["jobs"] == []
        assert data["total"] == 0
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_list_jobs_with_pagination(self, client: AsyncClient):
        """ページネーション付きジョブ一覧"""
        # まずジョブを作成
        for i in range(3):
            await client.post(
                "/api/upload/init",
                json={"file_name": f"test{i}.mp4", "file_size": 1024},
            )

        # ページサイズ2でページ1を取得
        response = await client.get("/api/jobs?page=1&page_size=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["jobs"]) == 2
        assert data["total"] == 3
        assert data["total_pages"] == 2

    @pytest.mark.asyncio
    async def test_get_job_not_found(self, client: AsyncClient):
        """存在しないジョブの取得で404エラー"""
        response = await client.get("/api/jobs/nonexistent-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_job_detail(self, client: AsyncClient):
        """ジョブ詳細の取得"""
        # ジョブ作成
        init_resp = await client.post(
            "/api/upload/init",
            json={"file_name": "detail_test.mp4", "file_size": 2048, "language": "en"},
        )
        job_id = init_resp.json()["job_id"]

        # 詳細取得
        response = await client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == job_id
        assert data["file_name"] == "detail_test.mp4"
        assert data["file_size"] == 2048
        assert data["language"] == "en"
        assert data["status"] == "uploading"

    @pytest.mark.asyncio
    async def test_delete_job(self, client: AsyncClient):
        """ジョブの削除"""
        # ジョブ作成
        init_resp = await client.post(
            "/api/upload/init",
            json={"file_name": "delete_test.mp4", "file_size": 1024},
        )
        job_id = init_resp.json()["job_id"]

        # 削除
        response = await client.delete(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

        # 削除確認
        response = await client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_job_not_found(self, client: AsyncClient):
        """存在しないジョブの削除で404エラー"""
        response = await client.delete("/api/jobs/nonexistent-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_transcription_not_found(self, client: AsyncClient):
        """存在しないジョブの文字起こし結果取得で404エラー"""
        response = await client.get("/api/jobs/nonexistent-id/transcription")
        assert response.status_code == 404


class TestExportApi:
    """エクスポートAPIのテスト"""

    @pytest.mark.asyncio
    async def test_export_not_found(self, client: AsyncClient):
        """存在しないジョブのエクスポートで404エラー"""
        response = await client.get("/api/export/nonexistent-id?format=txt")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_export_not_completed(self, client: AsyncClient):
        """未完了ジョブのエクスポートで400エラー"""
        # uploading状態のジョブを作成
        init_resp = await client.post(
            "/api/upload/init",
            json={"file_name": "test.mp4", "file_size": 1024},
        )
        job_id = init_resp.json()["job_id"]

        response = await client.get(f"/api/export/{job_id}?format=txt")
        assert response.status_code == 400
        assert "完了していません" in response.json()["detail"]
