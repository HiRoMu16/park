# -*- coding: utf-8 -*-
import cv2
import mediapipe as mp
import numpy as np
from flask import Flask, request, jsonify, send_from_directory
import os
import tempfile

# Flaskアプリケーションの初期化
app = Flask(__name__, static_url_path='', static_folder='.')

# MediaPipe Poseの準備
mp_pose = mp.solutions.pose

# ルートURL ('/') で index.html を提供
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

# 動画アップロードと解析のエンドポイント
@app.route('/upload', methods=['POST'])
def upload_video():
    if 'video' not in request.files:
        return jsonify({"error": "No video file"}), 400

    file = request.files['video']
    
    # 一時ファイルとして動画を保存 (OpenCVで読み込むため)
    # 'with' を使うことで、処理終了後に自動的にファイルが削除される
    with tempfile.NamedTemporaryFile(delete=True, suffix='.mp4') as temp_file:
        file.save(temp_file.name)
        
        cap = cv2.VideoCapture(temp_file.name)
        if not cap.isOpened():
            return jsonify({"error": "Could not open video file"}), 500

        fps = cap.get(cv2.CAP_PROP_FPS)
        all_landmarks = [] # 全フレームのランドマークを格納するリスト

        # MediaPipe Poseのインスタンス化
        with mp_pose.Pose(
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
            model_complexity=1, # 精度を優先 (0: fast, 1: accurate, 2: heavy)
            static_image_mode=False # 動画モード
        ) as pose:
            
            while cap.isOpened():
                success, image = cap.read()
                if not success:
                    break # 動画の終わり

                # OpenCVはBGR、MediaPipeはRGBなので色空間を変換
                image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                
                # 姿勢推定の実行
                results = pose.process(image_rgb)

                frame_landmarks = []
                if results.pose_landmarks:
                    # 検出したランドマーク (33点) の座標をリストに追加
                    for landmark in results.pose_landmarks.landmark:
                        frame_landmarks.append({
                            "x": landmark.x,
                            "y": landmark.y,
                            "z": landmark.z,
                            "visibility": landmark.visibility
                        })
                
                # 検出結果（空の場合も含む）を全フレームリストに追加
                all_landmarks.append(frame_landmarks)

        cap.release()

        # 解析結果をJSONでフロントエンドに返す
        return jsonify({
            "fps": fps,
            "totalFrames": len(all_landmarks),
            "landmarksData": all_landmarks
        })

# サーバーの実行
if __name__ == '__main__':
    # debug=True で開発モード (コード変更時に自動リロード)
    app.run(debug=True, host='0.0.0.0', port=5000)