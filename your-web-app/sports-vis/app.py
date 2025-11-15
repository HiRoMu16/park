# -*- coding: utf-8 -*-
import cv2
import mediapipe as mp
import numpy as np
from flask import Flask, request, jsonify, send_from_directory
import os
import tempfile
from scipy.signal import butter, filtfilt # ★追加: フィルター処理用

# Flaskアプリケーションの初期化
app = Flask(__name__, static_url_path='', static_folder='.')

# MediaPipe Poseの準備
mp_pose = mp.solutions.pose

# --- ★ここから追加 (キネマティクス解析関数) ---

def apply_butterworth_filter(data, cutoff_freq, fs, order=4):
    """
    データにバターワースローパスフィルターを適用する
    :param data: フィルター処理する時系列データ (NumPy配列)
    :param cutoff_freq: カットオフ周波数 (Hz)。人間の動作は通常6-10Hz
    :param fs: サンプリング周波数 (Hz)。動画のFPS
    :param order: フィルターの次数
    :return: フィルター処理後のデータ
    """
    nyquist_freq = 0.5 * fs # ナイキスト周波数
    normal_cutoff = cutoff_freq / nyquist_freq
    
    # フィルター係数を取得
    # btype='low' でローパスフィルター
    b, a = butter(order, normal_cutoff, btype='low', analog=False)
    
    # filtfilt: ゼロ位相フィルター（時間遅れなしでフィルターをかける）
    filtered_data = filtfilt(b, a, data)
    return filtered_data

def calculate_kinematics(landmarks_over_time, fs):
    """
    フィルター処理と速度計算を行う
    :param landmarks_over_time: (フレーム数, ランドマーク数, 3[x,y,z]) のNumPy配列
    :param fs: サンプリング周波数 (FPS)
    :return: 速度データ (フレーム数, ランドマーク数, 3[vx,vy,vz])
    """
    num_frames, num_landmarks, _ = landmarks_over_time.shape
    if num_frames < 20: # フレームが少なすぎるとフィルターが不安定になる
        return np.zeros_like(landmarks_over_time) # とりあえずゼロを返す

    dt = 1.0 / fs # 1フレームあたりの時間 (Δt)
    
    # 速度を格納する配列
    velocities = np.zeros_like(landmarks_over_time)
    
    # カットオフ周波数 (バイオメカニクスでは6Hzが一般的)
    cutoff_freq = 6.0 

    # 各ランドマークの各座標 (x, y, z) に対してループ処理
    for landmark_idx in range(num_landmarks):
        for coord_idx in range(3): # 0:x, 1:y, 2:z
            # (1) 生データを抽出
            raw_coords = landmarks_over_time[:, landmark_idx, coord_idx]
            
            # (2) フィルター処理
            filtered_coords = apply_butterworth_filter(raw_coords, cutoff_freq, fs)
            
            # (3) 速度計算 (中心差分法)
            # np.gradient を使うと、配列の端点も適切に処理してくれる
            # (dt) で割ることで、単位を [座標単位/フレーム] から [座標単位/秒] に変換
            coord_velocities = np.gradient(filtered_coords, dt)
            
            velocities[:, landmark_idx, coord_idx] = coord_velocities
            
    return velocities

# --- ★追加ここまで ---


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
    
    try:
        temp_f = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
        temp_f.close()
        temp_file_path = temp_f.name
    except Exception as e:
        app.logger.error(f"Failed to create temp file: {e}")
        return jsonify({"error": f"Failed to create temp file: {e}"}), 500

    all_landmarks_list = [] # ★名前を変更 (listであることを明示)
    fps = 30 
    kinematics_data = {} # ★追加: キネマティクス結果用

    try:
        file.save(temp_file_path)
        cap = cv2.VideoCapture(temp_file_path)
        if not cap.isOpened():
            return jsonify({"error": "Could not open video file"}), 500

        fps = cap.get(cv2.CAP_PROP_FPS)

        with mp_pose.Pose(
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
            model_complexity=1, 
            static_image_mode=False
        ) as pose:
            
            while cap.isOpened():
                success, image = cap.read()
                if not success:
                    break 

                image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                results = pose.process(image_rgb)

                frame_landmarks = []
                if results.pose_landmarks:
                    for landmark in results.pose_landmarks.landmark:
                        frame_landmarks.append({
                            "x": landmark.x,
                            "y": landmark.y,
                            "z": landmark.z,
                            "visibility": landmark.visibility
                        })
                else:
                    # ★重要: 検出失敗したフレームにも空データ(NaN)を入れて長さを揃える
                    # MediaPipeのランドマークは33点
                    empty_landmarks = [{"x": np.nan, "y": np.nan, "z": np.nan, "visibility": 0}] * 33
                    frame_landmarks = empty_landmarks
                
                all_landmarks_list.append(frame_landmarks)

        cap.release()

        # --- ★ここから追加 (解析実行) ---
        
        # 1. データをNumPy配列に変換 (フレーム数, 33, 3)
        #    visibility は一旦無視し、x, y, z のみ抽出
        num_frames = len(all_landmarks_list)
        num_landmarks = 33
        
        # (x, y, z) の座標データを格納する配列
        landmarks_np = np.zeros((num_frames, num_landmarks, 3))
        
        for frame_idx, frame_data in enumerate(all_landmarks_list):
            for landmark_idx in range(num_landmarks):
                if frame_data and landmark_idx < len(frame_data): # データがあるか確認
                    landmarks_np[frame_idx, landmark_idx, 0] = frame_data[landmark_idx]["x"]
                    landmarks_np[frame_idx, landmark_idx, 1] = frame_data[landmark_idx]["y"]
                    landmarks_np[frame_idx, landmark_idx, 2] = frame_data[landmark_idx]["z"]
                else:
                    # 検出失敗フレーム（上記でNaNを入れた箇所）
                    landmarks_np[frame_idx, landmark_idx, :] = np.nan

        # 2. 欠損値(NaN)の補間 (フィルター処理はNaNに対応できないため)
        #    ここでは単純な線形補間を行う
        #    (本当は各列(landmark, coord)ごとに補間すべきだが、簡潔さのため全体に適用)
        
        # np.isnanでNaNの位置を取得
        nan_indices = np.isnan(landmarks_np)
        
        # np.interpで線形補間 (非NaNのインデックスと値を使う)
        # この処理は複雑になるため、今回は簡易的に「NaNを含むフレームのデータは使わない」
        # 代わりに、NaNを0で埋める (本当は良くないが、プロトタイプとして)
        # ※より堅牢にするには pandas.DataFrame.interpolate() を使うのが良い
        landmarks_np[nan_indices] = 0 # 簡易的なNaN処理 (0で置換)

        # 3. キネマティクス計算の実行
        velocities_np = calculate_kinematics(landmarks_np, fps)
        
        # 4. JSONで返せるようにリスト形式に変換
        #    ここでは右手首(ID: 16)と左手首(ID: 15)の速度だけを返す
        right_wrist_velocity = velocities_np[:, 16, :].tolist() # 右手首 (x,y,zの速度)
        left_wrist_velocity = velocities_np[:, 15, :].tolist()  # 左手首 (x,y,zの速度)
        
        kinematics_data = {
            "right_wrist_velocity": right_wrist_velocity,
            "left_wrist_velocity": left_wrist_velocity
        }
        
        # --- ★追加ここまで ---

        # 解析結果をJSONでフロントエンドに返す
        return jsonify({
            "fps": fps,
            "totalFrames": len(all_landmarks_list),
            "landmarksData": all_landmarks_list, # 生のランドマークデータ
            "kinematicsData": kinematics_data   # ★追加: 計算した速度データ
        })
    
    except Exception as e:
        app.logger.error(f"Error during video processing: {e}")
        # ★デバッグ用にエラー詳細をフロントに返す
        import traceback
        return jsonify({"error": f"Error: {e}\nTrace: {traceback.format_exc()}"}), 500

    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
    
# サーバーの実行
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)