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
    
    # --- 修正箇所 ---
    
    # 1. 一時ファイルを「作成」し、すぐに「閉じる」 (Windowsの権限エラー回避)
    #    delete=False にして、ファイルハンドルを閉じてもファイルが消えないようにする
    try:
        temp_f = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
        temp_f.close() # ★重要: ファイルハンドルを一度解放する
        temp_file_path = temp_f.name # パス名だけを取得
    except Exception as e:
        app.logger.error(f"Failed to create temp file: {e}")
        return jsonify({"error": f"Failed to create temp file: {e}"}), 500

    all_landmarks = []
    fps = 30 # デフォルトFPS

    try:
        # 2. アップロードされたデータを、閉じた一時ファイルのパスに「保存」する
        file.save(temp_file_path)
        
        # 3. OpenCVで一時ファイルを開く
        cap = cv2.VideoCapture(temp_file_path)
        if not cap.isOpened():
            return jsonify({"error": "Could not open video file"}), 500

        fps = cap.get(cv2.CAP_PROP_FPS)

        # MediaPipe Poseのインスタンス化
        with mp_pose.Pose(
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
            model_complexity=1, 
            static_image_mode=False
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

        # 4. 解析結果をJSONでフロントエンドに返す
        return jsonify({
            "fps": fps,
            "totalFrames": len(all_landmarks),
            "landmarksData": all_landmarks
        })
    
    except Exception as e:
        # 処理中に何らかのエラーが発生した場合
        app.logger.error(f"Error during video processing: {e}") # サーバーログにエラーを記録
        return jsonify({"error": str(e)}), 500

    finally:
        # 5. ★重要: 処理が成功しても失敗しても、必ず一時ファイルを削除する
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
    
    # --- 修正ここまで ---

# サーバーの実行
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)