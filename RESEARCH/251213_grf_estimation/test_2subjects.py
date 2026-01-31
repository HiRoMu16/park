"""
2被験者データでの動作確認テスト
修正前の問題: 訓練データが空になり学習できなかった
"""

import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

import numpy as np
import pandas as pd

from hybrid_model import (
    DirectModel, HybridModel, EnsembleModel, ModelEvaluator,
    run_leave_one_subject_out_cv
)

def main():
    print("="*70)
    print("2被験者データでの動作確認テスト")
    print("="*70)
    
    # データ読み込み
    data_path = './demo_data/demo_running_data_stance_only_sub1-2.csv'
    df = pd.read_csv(data_path)
    
    print(f"\nデータ読み込み: {len(df)} サンプル")
    print(f"被験者: {sorted(df['subject_id'].unique())}")
    
    # 特徴量抽出
    imu_cols = [
        'pelvis_acc_x', 'pelvis_acc_y', 'pelvis_acc_z',
        'tibia_left_acc_x', 'tibia_left_acc_y', 'tibia_left_acc_z',
        'tibia_right_acc_x', 'tibia_right_acc_y', 'tibia_right_acc_z'
    ]
    grf_cols = ['grf_ml', 'grf_ap', 'grf_vertical']
    
    X = df[imu_cols].values
    y = df[grf_cols].values
    subject_ids = df['subject_id'].values
    body_masses = df.groupby('subject_id')['body_mass'].first().to_dict()
    
    print(f"\n被験者ごとのサンプル数:")
    for subj in sorted(df['subject_id'].unique()):
        n = (subject_ids == subj).sum()
        print(f"  Subject {subj}: {n} samples, {body_masses[subj]:.1f} kg")
    
    # Leave-one-subject-out CV実行
    print("\n" + "="*70)
    print("Leave-One-Subject-Out Cross-Validation (Direct Model)")
    print("="*70)
    
    results = run_leave_one_subject_out_cv(
        X, y, subject_ids, body_masses,
        model_type='direct',
        n_ensemble_members=3,  # 少なめに設定
        verbose=1
    )
    
    # 結果サマリー
    print("\n" + "="*70)
    print("結果サマリー")
    print("="*70)
    
    for subj in results:
        print(f"\nSubject {subj}:")
        for direction in ['ML', 'AP', 'V']:
            metrics = results[subj]['metrics'][direction]
            print(f"  {direction}: rRMSE={metrics['rRMSE']:.1f}%, r={metrics['Pearson_r']:.3f}")


if __name__ == "__main__":
    main()
