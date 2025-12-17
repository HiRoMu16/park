"""
Main Training and Evaluation Script for 3D GRF Estimation
Based on Scheltinga et al. (2023)

This script demonstrates:
1. Loading and preprocessing data
2. Training Direct, Hybrid, and Physical models
3. Leave-one-subject-out cross-validation with ensemble
4. Model evaluation and results visualization
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import json

# Import our modules
from hybrid_model import (
    DataPreprocessor, PhysicalModel, DirectModel, HybridModel,
    EnsembleModel, ModelEvaluator, run_leave_one_subject_out_cv,
    print_summary_results
)
from demo_data_generator import generate_demo_dataset


def load_data(data_path: str, stance_only: bool = True):
    """
    Load data from CSV file.
    
    Args:
        data_path: Path to CSV file
        stance_only: If True, filter to stance phase only
        
    Returns:
        X: IMU data (n_samples, 9)
        y: GRF data (n_samples, 3)
        subject_ids: Subject ID for each sample
        body_masses: Dictionary of body masses
    """
    df = pd.read_csv(data_path)
    
    if stance_only and 'phase' in df.columns:
        df = df[df['phase'] == 'stance'].copy()
    
    # Extract IMU features
    imu_cols = [
        'pelvis_acc_x', 'pelvis_acc_y', 'pelvis_acc_z',
        'tibia_left_acc_x', 'tibia_left_acc_y', 'tibia_left_acc_z',
        'tibia_right_acc_x', 'tibia_right_acc_y', 'tibia_right_acc_z'
    ]
    X = df[imu_cols].values
    
    # Extract GRF targets
    grf_cols = ['grf_ml', 'grf_ap', 'grf_vertical']
    y = df[grf_cols].values
    
    # Subject IDs
    subject_ids = df['subject_id'].values
    
    # Body masses
    body_masses = df.groupby('subject_id')['body_mass'].first().to_dict()
    
    return X, y, subject_ids, body_masses


def compare_models(X: np.ndarray, y: np.ndarray, 
                   subject_ids: np.ndarray, body_masses: dict,
                   n_ensemble_members: int = 7,
                   verbose: int = 1):
    """
    Compare Direct, Hybrid, and Physical models.
    
    Args:
        X: IMU data
        y: GRF data
        subject_ids: Subject IDs
        body_masses: Body mass dictionary
        n_ensemble_members: Number of ensemble members
        verbose: Verbosity level
        
    Returns:
        Dictionary with results for each model type
    """
    results = {}
    
    # 1. Direct Model
    print("\n" + "="*60)
    print("Training DIRECT Model (IMU only)")
    print("="*60)
    results['direct'] = run_leave_one_subject_out_cv(
        X, y, subject_ids, body_masses,
        model_type='direct',
        n_ensemble_members=n_ensemble_members,
        verbose=verbose
    )
    
    # 2. Hybrid Model
    print("\n" + "="*60)
    print("Training HYBRID Model (IMU + Physical)")
    print("="*60)
    results['hybrid'] = run_leave_one_subject_out_cv(
        X, y, subject_ids, body_masses,
        model_type='hybrid',
        n_ensemble_members=n_ensemble_members,
        verbose=verbose
    )
    
    # 3. Physical Model (for vertical direction only)
    print("\n" + "="*60)
    print("Evaluating PHYSICAL Model (Vertical only)")
    print("="*60)
    results['physical'] = evaluate_physical_model(X, y, subject_ids, body_masses)
    
    return results


def evaluate_physical_model(X: np.ndarray, y: np.ndarray,
                            subject_ids: np.ndarray, body_masses: dict):
    """
    Evaluate the physical model on all subjects.
    
    Args:
        X: IMU data
        y: GRF data (normalized by BW)
        subject_ids: Subject IDs
        body_masses: Body mass dictionary
        
    Returns:
        Dictionary with evaluation results
    """
    unique_subjects = np.unique(subject_ids)
    results = {}
    
    for subj in unique_subjects:
        mask = subject_ids == subj
        X_subj = X[mask]
        y_subj = y[mask]
        body_mass = body_masses[subj]
        
        # Create physical model
        physical_model = PhysicalModel(body_mass)
        
        # Extract vertical accelerations
        pelvis_z = X_subj[:, 2]
        tibia_left_z = X_subj[:, 5]
        tibia_right_z = X_subj[:, 8]
        
        # Estimate vertical GRF
        grf_estimated = physical_model.estimate_vertical_grf_both_legs(
            pelvis_z, tibia_left_z, tibia_right_z
        )
        
        # Normalize by body weight
        body_weight = body_mass * 9.81
        grf_estimated_bw = grf_estimated / body_weight
        
        # Evaluate (vertical direction only)
        y_true_v = y_subj[:, 2]  # Vertical GRF
        y_pred_v = grf_estimated_bw
        
        metrics = {
            'V': {
                'RMSE': ModelEvaluator.rmse(y_true_v, y_pred_v),
                'rRMSE': ModelEvaluator.rrmse(y_true_v, y_pred_v),
                'Pearson_r': ModelEvaluator.pearson_r(y_true_v, y_pred_v),
                'Peak_error': ModelEvaluator.peak_error(y_true_v, y_pred_v)
            }
        }
        
        results[subj] = {
            'metrics': metrics,
            'y_true': y_subj,
            'y_pred_v': grf_estimated_bw
        }
        
        print(f"Subject {subj}: rRMSE={metrics['V']['rRMSE']:.2f}%, r={metrics['V']['Pearson_r']:.3f}")
    
    return results


def plot_results_comparison(results: dict, output_dir: str = './results'):
    """
    Create comparison plots for model results.
    
    Args:
        results: Dictionary with results for each model
        output_dir: Directory to save plots
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    directions = ['ML', 'AP', 'V']
    models = ['direct', 'hybrid', 'physical']
    model_labels = ['Direct', 'Hybrid', 'Physical']
    colors = ['#1f77b4', '#2ca02c', '#ff7f0e']
    
    # Get subjects
    subjects = list(results['direct'].keys())
    
    # Plot 1: rRMSE comparison per direction
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    
    for ax, direction in zip(axes, directions):
        x = np.arange(len(subjects))
        width = 0.25
        
        for i, (model, label, color) in enumerate(zip(models, model_labels, colors)):
            if direction in ['ML', 'AP'] and model == 'physical':
                # Physical model only for vertical
                values = [np.nan] * len(subjects)
            else:
                values = [results[model][subj]['metrics'].get(direction, {}).get('rRMSE', np.nan) 
                         for subj in subjects]
            
            ax.bar(x + i * width, values, width, label=label, color=color, alpha=0.8)
        
        ax.set_xlabel('Subject')
        ax.set_ylabel('rRMSE (%)')
        ax.set_title(f'{direction} Direction')
        ax.set_xticks(x + width)
        ax.set_xticklabels(subjects)
        ax.legend()
        ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/rrmse_comparison.png', dpi=150)
    plt.close()
    
    # Plot 2: Pearson correlation comparison
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    
    for ax, direction in zip(axes, directions):
        x = np.arange(len(subjects))
        width = 0.25
        
        for i, (model, label, color) in enumerate(zip(models, model_labels, colors)):
            if direction in ['ML', 'AP'] and model == 'physical':
                values = [np.nan] * len(subjects)
            else:
                values = [results[model][subj]['metrics'].get(direction, {}).get('Pearson_r', np.nan)
                         for subj in subjects]
            
            ax.bar(x + i * width, values, width, label=label, color=color, alpha=0.8)
        
        ax.set_xlabel('Subject')
        ax.set_ylabel("Pearson's r")
        ax.set_title(f'{direction} Direction')
        ax.set_xticks(x + width)
        ax.set_xticklabels(subjects)
        ax.legend()
        ax.set_ylim(0, 1.1)
        ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/pearson_comparison.png', dpi=150)
    plt.close()
    
    print(f"\nPlots saved to {output_dir}/")


def plot_grf_waveforms(results: dict, subject_id: int, 
                       output_dir: str = './results'):
    """
    Plot example GRF waveforms for a single subject.
    
    Args:
        results: Results dictionary
        subject_id: Subject to plot
        output_dir: Output directory
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    fig, axes = plt.subplots(3, 1, figsize=(12, 10))
    
    directions = ['ML', 'AP', 'V']
    direction_names = ['Mediolateral', 'Anterior-Posterior', 'Vertical']
    
    # Get measured GRF
    y_true = results['direct'][subject_id]['y_true']
    y_pred_direct = results['direct'][subject_id]['y_pred']
    y_pred_hybrid = results['hybrid'][subject_id]['y_pred']
    
    # Plot only first 500 samples for clarity
    n_plot = min(500, len(y_true))
    samples = np.arange(n_plot)
    
    for ax, i, (direction, name) in zip(axes, range(3), zip(directions, direction_names)):
        ax.plot(samples, y_true[:n_plot, i], 'k-', linewidth=2, label='Measured', alpha=0.8)
        ax.plot(samples, y_pred_direct[:n_plot, i], 'b-', linewidth=1.5, label='Direct', alpha=0.7)
        ax.plot(samples, y_pred_hybrid[:n_plot, i], 'g-', linewidth=1.5, label='Hybrid', alpha=0.7)
        
        # Add physical model for vertical
        if direction == 'V' and 'y_pred_v' in results['physical'][subject_id]:
            y_pred_phys = results['physical'][subject_id]['y_pred_v']
            ax.plot(samples, y_pred_phys[:n_plot], 'r--', linewidth=1.5, label='Physical', alpha=0.7)
        
        ax.set_xlabel('Sample')
        ax.set_ylabel('Force (BW)')
        ax.set_title(f'{name} Direction')
        ax.legend()
        ax.grid(alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/grf_waveforms_subject{subject_id}.png', dpi=150)
    plt.close()
    
    print(f"Waveform plot saved for Subject {subject_id}")


def print_detailed_results(results: dict):
    """Print detailed comparison table."""
    print("\n" + "="*80)
    print("DETAILED RESULTS COMPARISON")
    print("="*80)
    
    # Collect metrics
    models = ['direct', 'hybrid', 'physical']
    directions = ['ML', 'AP', 'V']
    
    for direction in directions:
        print(f"\n{direction} Direction:")
        print("-" * 60)
        print(f"{'Model':<12} {'RMSE (BW)':<12} {'rRMSE (%)':<12} {'Pearson r':<12}")
        print("-" * 60)
        
        for model in models:
            if direction in ['ML', 'AP'] and model == 'physical':
                print(f"{model.capitalize():<12} {'N/A':<12} {'N/A':<12} {'N/A':<12}")
                continue
            
            rmse_vals = []
            rrmse_vals = []
            r_vals = []
            
            for subj in results[model]:
                metrics = results[model][subj]['metrics']
                if direction in metrics:
                    rmse_vals.append(metrics[direction]['RMSE'])
                    rrmse_vals.append(metrics[direction]['rRMSE'])
                    r_vals.append(metrics[direction]['Pearson_r'])
            
            if rmse_vals:
                print(f"{model.capitalize():<12} "
                      f"{np.mean(rmse_vals):.3f}±{np.std(rmse_vals):.3f}  "
                      f"{np.mean(rrmse_vals):.1f}±{np.std(rrmse_vals):.1f}     "
                      f"{np.mean(r_vals):.3f}±{np.std(r_vals):.3f}")
    
    # Vertical peak error
    print(f"\nVertical Peak Error:")
    print("-" * 40)
    for model in models:
        peak_errors = []
        for subj in results[model]:
            metrics = results[model][subj]['metrics']
            if 'V' in metrics and 'Peak_error' in metrics['V']:
                peak_errors.append(metrics['V']['Peak_error'])
        
        if peak_errors:
            print(f"{model.capitalize():<12}: {np.mean(peak_errors):.2f}% ± {np.std(peak_errors):.2f}%")


def save_results_to_json(results: dict, output_path: str):
    """Save results to JSON file for later analysis."""
    # Convert numpy arrays to lists for JSON serialization
    json_results = {}
    
    for model in results:
        json_results[model] = {}
        for subj in results[model]:
            json_results[model][str(subj)] = {
                'metrics': results[model][subj]['metrics']
            }
    
    with open(output_path, 'w') as f:
        json.dump(json_results, f, indent=2)
    
    print(f"\nResults saved to {output_path}")


def main():
    """Main function to run the complete pipeline."""
    
    print("="*70)
    print("3D Ground Reaction Force Estimation using IMUs")
    print("Implementation based on Scheltinga et al. (2023)")
    print("="*70)
    
    # Configuration
    DATA_DIR = './demo_data'
    RESULTS_DIR = './results'
    N_SUBJECTS = 6
    N_STRIDES = 20
    N_ENSEMBLE_MEMBERS = 7
    SEED = 42
    
    # Step 1: Generate or load demo data
    print("\n[Step 1] Preparing data...")
    data_file = Path(DATA_DIR) / 'demo_running_data_stance_only_sub1-2.csv'
    
    if not data_file.exists():
        print("Generating demo dataset...")
        generate_demo_dataset(
            n_subjects=N_SUBJECTS,
            n_strides_per_condition=N_STRIDES,
            output_dir=DATA_DIR,
            seed=SEED
        )
    else:
        print(f"Loading existing data from {data_file}")
    
    # Step 2: Load data
    print("\n[Step 2] Loading data...")
    X, y, subject_ids, body_masses = load_data(str(data_file), stance_only=True)
    
    print(f"Data loaded:")
    print(f"  - Samples: {X.shape[0]}")
    print(f"  - IMU features: {X.shape[1]}")
    print(f"  - GRF outputs: {y.shape[1]}")
    print(f"  - Subjects: {len(np.unique(subject_ids))}")
    
    # Step 3: Train and compare models
    print("\n[Step 3] Training models with Leave-One-Subject-Out CV...")
    results = compare_models(
        X, y, subject_ids, body_masses,
        n_ensemble_members=N_ENSEMBLE_MEMBERS,
        verbose=1
    )
    
    # Step 4: Print detailed results
    print_detailed_results(results)
    
    # Step 5: Create visualizations
    print("\n[Step 5] Creating visualizations...")
    Path(RESULTS_DIR).mkdir(parents=True, exist_ok=True)
    
    plot_results_comparison(results, RESULTS_DIR)
    
    # Plot waveforms for first subject
    first_subject = list(results['direct'].keys())[0]
    plot_grf_waveforms(results, first_subject, RESULTS_DIR)
    
    # Step 6: Save results
    print("\n[Step 6] Saving results...")
    save_results_to_json(results, f'{RESULTS_DIR}/evaluation_results.json')
    
    print("\n" + "="*70)
    print("Complete!")
    print("="*70)
    print(f"\nOutput files:")
    print(f"  - {RESULTS_DIR}/rrmse_comparison.png")
    print(f"  - {RESULTS_DIR}/pearson_comparison.png")
    print(f"  - {RESULTS_DIR}/grf_waveforms_subject{first_subject}.png")
    print(f"  - {RESULTS_DIR}/evaluation_results.json")


if __name__ == "__main__":
    main()
