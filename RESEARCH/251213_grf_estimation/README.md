# 3D床反力推定モデル - IMUセンサを用いたハイブリッドモデル

Scheltinga et al. (2023) の論文「Estimating 3D ground reaction forces in running using three inertial measurement units」を再現したPython実装です。

**論文DOI**: 10.3389/fspor.2023.1176466

## 概要

このプロジェクトは、3つのIMU（慣性計測ユニット）を使用してランニング中の3次元床反力（GRF）を推定するためのモデルを実装しています。

### 実装されているモデル

1. **Physical Model（物理モデル）**: ニュートンの第二法則に基づく垂直GRF推定
2. **Direct Model（直接モデル）**: IMUデータのみを入力としたANN
3. **Hybrid Model（ハイブリッドモデル）**: 物理モデル出力をANNの追加入力として使用

## ファイル構成

```
grf_estimation/
├── hybrid_model.py           # メインモデル実装（Physical, Direct, Hybrid, Ensemble）
├── demo_data_generator.py    # デモデータ生成スクリプト
├── train_and_evaluate.py     # 学習・評価メインスクリプト
├── test_implementation.py    # 実装テスト
├── requirements.txt          # 依存パッケージ
└── demo_data/
    ├── demo_running_data.csv              # 全データ（stance + flight phase）
    ├── demo_running_data_stance_only.csv  # stance phaseのみのデータ
    └── subject_info.csv                   # 被験者情報（体重など）
```

## インストール

```bash
pip install -r requirements.txt
```

## 使用方法

### 1. デモデータの生成

```python
from demo_data_generator import generate_demo_dataset

# デモデータを生成
df, body_masses = generate_demo_dataset(
    n_subjects=6,           # 被験者数
    n_strides_per_condition=20,  # 条件ごとのストライド数
    output_dir='./demo_data',
    seed=42
)
```

### 2. データの読み込み

```python
import pandas as pd
import numpy as np

# CSVファイルを読み込み
df = pd.read_csv('demo_data/demo_running_data_stance_only.csv')

# IMU特徴量を抽出
imu_cols = [
    'pelvis_acc_x', 'pelvis_acc_y', 'pelvis_acc_z',
    'tibia_left_acc_x', 'tibia_left_acc_y', 'tibia_left_acc_z',
    'tibia_right_acc_x', 'tibia_right_acc_y', 'tibia_right_acc_z'
]

# GRFターゲットを抽出
grf_cols = ['grf_ml', 'grf_ap', 'grf_vertical']

X = df[imu_cols].values  # (n_samples, 9)
y = df[grf_cols].values  # (n_samples, 3)
subject_ids = df['subject_id'].values
```

### 3. ハイブリッドモデルの学習

```python
from hybrid_model import HybridModel

# モデルの初期化（体重を指定）
model = HybridModel(body_mass=70.0, sampling_freq=240.0)

# 学習
model.train(
    X_train, y_train,
    X_val, y_val,
    epochs=1000,
    batch_size=250,
    patience=100  # 早期停止
)

# 予測
y_pred = model.predict(X_test)
```

### 4. アンサンブルモデルの学習

```python
from hybrid_model import EnsembleModel, HybridModel

# アンサンブルモデルの初期化
ensemble = EnsembleModel(
    HybridModel, 
    n_members=7,  # アンサンブルメンバー数
    body_mass=70.0
)

# Leave-one-subject-out cross-validation用の学習
ensemble.train(
    X_train, y_train,
    subject_ids=train_subject_ids,
    test_subject=1,  # テスト被験者ID
    n_val_subjects=4  # 検証用被験者数
)

# 予測（メンバーの平均）
y_pred = ensemble.predict(X_test)

# 不確実性付きの予測
y_pred_mean, y_pred_std = ensemble.predict_with_uncertainty(X_test)
```

### 5. モデル評価

```python
from hybrid_model import ModelEvaluator

# 3D GRFの評価
evaluation = ModelEvaluator.evaluate_3d_grf(y_true, y_pred)

for direction, metrics in evaluation.items():
    print(f"{direction}:")
    print(f"  RMSE: {metrics['RMSE']:.4f} BW")
    print(f"  rRMSE: {metrics['rRMSE']:.1f}%")
    print(f"  Pearson's r: {metrics['Pearson_r']:.3f}")
```

### 6. 完全なパイプラインの実行

```bash
python train_and_evaluate.py
```

## データ形式

### 入力データ（IMU）

| 列名 | 説明 | 単位 |
|------|------|------|
| pelvis_acc_x | 骨盤のML方向加速度 | m/s² |
| pelvis_acc_y | 骨盤のAP方向加速度 | m/s² |
| pelvis_acc_z | 骨盤の垂直方向加速度 | m/s² |
| tibia_left_acc_x | 左脛のML方向加速度 | m/s² |
| tibia_left_acc_y | 左脛のAP方向加速度 | m/s² |
| tibia_left_acc_z | 左脛の垂直方向加速度 | m/s² |
| tibia_right_acc_x | 右脛のML方向加速度 | m/s² |
| tibia_right_acc_y | 右脛のAP方向加速度 | m/s² |
| tibia_right_acc_z | 右脛の垂直方向加速度 | m/s² |

**注意**: sensor-free acceleration（重力を除去した加速度）を使用してください。

### 出力データ（GRF）

| 列名 | 説明 | 単位 |
|------|------|------|
| grf_ml | 内外側方向GRF | BW (体重比) |
| grf_ap | 前後方向GRF | BW (体重比) |
| grf_vertical | 垂直方向GRF | BW (体重比) |

## モデルアーキテクチャ

### 物理モデル

```
eGRF = (m_b × g) + Σ(m_b × WF_i × a_z,i)
```

- `m_b`: 体重 [kg]
- `g`: 重力加速度 (9.81 m/s²)
- `WF_pelvis`: 0.55
- `WF_tibia`: 0.23（各脛）
- フィルタ:
  - 骨盤: 2次Butterworth, カットオフ 5.97 Hz
  - 脛: 1次Butterworth, カットオフ 8.74 Hz

### ANNアーキテクチャ

- 入力層: 9次元（Direct）/ 10次元（Hybrid = IMU + 物理モデル出力）
- 隠れ層: 2層 × 100ニューロン
- 活性化関数: ReLU
- 出力層: 3次元（ML, AP, V）
- 最適化: Adam
- 損失関数: MSE
- バッチサイズ: 250
- 早期停止: patience = 100

## 評価指標

- **RMSE**: 二乗平均平方根誤差 [BW]
- **rRMSE**: 相対RMSE（全範囲で正規化）[%]
- **Pearson's r**: ピアソン相関係数
- **Peak error**: ピーク誤差 [%]（垂直方向のみ）

## 論文との主な違い

1. デモデータは実測データではなく、物理的に妥当なシミュレーションデータです
2. 実運用時は、実測データでモデルを再学習することを推奨します
3. サンプリング周波数は240Hzを想定していますが、`sampling_freq`パラメータで変更可能です

## 実測データへの適用

実測データを使用する場合:

1. IMUデータはsensor-free acceleration（重力除去済み）を使用
2. GRFデータは体重で正規化
3. stance phaseのみのデータを使用（flight phaseはGRF=0）
4. Leave-one-subject-out cross-validationで汎化性能を評価

## 参考文献

```
Scheltinga BL, Kok JN, Buurke JH and Reenalda J (2023) 
Estimating 3D ground reaction forces in running using three inertial measurement units.
Front. Sports Act. Living 5:1176466. 
doi: 10.3389/fspor.2023.1176466
```

## ライセンス

このコードは学術目的で自由に使用できます。商用利用の場合は元論文のライセンスを確認してください。
