"""
Demo Data Generator for GRF Estimation
Generates synthetic IMU and GRF data that mimics real running data patterns.

The generated data follows the patterns described in biomechanics literature:
- Vertical GRF: Characteristic two-peak pattern (impact and active peak) for heel strikers
- Anterior-Posterior GRF: Braking (negative) then propulsion (positive) pattern
- Mediolateral GRF: Smaller oscillations around zero

IMU accelerations are generated to correlate with GRF based on Newton's second law
with added noise to simulate real sensor data.
"""

import numpy as np
import pandas as pd
from scipy import signal
from typing import Tuple, Dict


class RunningDataGenerator:
    """
    Generate synthetic running data for testing GRF estimation models.
    """
    
    def __init__(self, sampling_freq: float = 240.0, seed: int = None):
        """
        Initialize data generator.
        
        Args:
            sampling_freq: Sampling frequency in Hz
            seed: Random seed for reproducibility
        """
        self.fs = sampling_freq
        if seed is not None:
            np.random.seed(seed)
    
    def generate_stance_phase(self, duration: float, body_mass: float,
                               velocity: float = 3.3) -> Dict[str, np.ndarray]:
        """
        Generate synthetic data for a single stance phase.
        
        Args:
            duration: Stance duration in seconds (typically 0.2-0.3s)
            body_mass: Subject body mass in kg
            velocity: Running velocity in m/s
            
        Returns:
            Dictionary with GRF and time arrays
        """
        n_samples = int(duration * self.fs)
        t = np.linspace(0, duration, n_samples)
        
        body_weight = body_mass * 9.81
        
        # Generate vertical GRF (heel strike pattern with impact and active peaks)
        # Normalized time (0 to 1)
        t_norm = t / duration
        
        # Impact peak (early stance, ~15% of stance)
        impact_peak_time = 0.15
        impact_peak_magnitude = 2.0 + 0.3 * (velocity - 3.0)  # Increases with velocity
        impact_peak = impact_peak_magnitude * np.exp(-((t_norm - impact_peak_time) ** 2) / (2 * 0.03 ** 2))
        
        # Active peak (mid-stance, ~45% of stance)
        active_peak_time = 0.45
        active_peak_magnitude = 2.5 + 0.2 * (velocity - 3.0)
        active_peak = active_peak_magnitude * np.exp(-((t_norm - active_peak_time) ** 2) / (2 * 0.15 ** 2))
        
        # Valley between peaks
        valley_factor = 0.8 * np.ones_like(t_norm)
        
        # Combine for vertical GRF
        grf_vertical = body_weight * (impact_peak + active_peak * valley_factor)
        
        # Smooth onset and offset
        onset_ramp = 0.5 * (1 + np.tanh((t_norm - 0.05) / 0.02))
        offset_ramp = 0.5 * (1 - np.tanh((t_norm - 0.95) / 0.02))
        grf_vertical = grf_vertical * onset_ramp * offset_ramp
        
        # Generate AP GRF (braking then propulsion)
        # Braking phase (negative, early stance)
        braking = -0.3 * body_weight * np.exp(-((t_norm - 0.25) ** 2) / (2 * 0.1 ** 2))
        # Propulsion phase (positive, late stance)
        propulsion = 0.35 * body_weight * np.exp(-((t_norm - 0.75) ** 2) / (2 * 0.12 ** 2))
        grf_ap = (braking + propulsion) * onset_ramp * offset_ramp
        
        # Generate ML GRF (smaller oscillations)
        # Medial force early, then lateral
        grf_ml = 0.1 * body_weight * np.sin(2 * np.pi * t_norm) * onset_ramp * offset_ramp
        grf_ml += 0.02 * body_weight * np.random.randn(n_samples)  # Add noise
        
        return {
            'time': t,
            'grf_ml': grf_ml,
            'grf_ap': grf_ap,
            'grf_vertical': grf_vertical
        }
    
    def generate_imu_from_grf(self, grf_data: Dict[str, np.ndarray], 
                               body_mass: float) -> Dict[str, np.ndarray]:
        """
        Generate IMU acceleration data based on GRF using inverse of physical model
        with added noise and filtering effects.
        
        Args:
            grf_data: Dictionary with GRF data
            body_mass: Body mass in kg
            
        Returns:
            Dictionary with IMU accelerations for pelvis and both tibias
        """
        g = 9.81
        body_weight = body_mass * g
        
        n_samples = len(grf_data['grf_vertical'])
        
        # Weight factors (inverse of physical model)
        wf_pelvis = 0.55
        wf_tibia = 0.23
        
        # Derive accelerations from GRF (simplified inverse model)
        # GRF_z ≈ m*g + m*wf_pelvis*a_pelvis + m*wf_tibia*(a_tibia_L + a_tibia_R)
        
        # Base vertical acceleration (from GRF - body weight) / mass
        base_acc_z = (grf_data['grf_vertical'] - body_weight) / body_mass
        
        # Distribute to sensors with some variation
        # Pelvis captures smoother motion
        pelvis_acc_z = base_acc_z / (wf_pelvis + 2 * wf_tibia) * wf_pelvis
        pelvis_acc_z = self._smooth_signal(pelvis_acc_z, cutoff=8.0)
        
        # Tibias capture more impact
        tibia_acc_z = base_acc_z / (wf_pelvis + 2 * wf_tibia) * wf_tibia
        tibia_acc_z = self._smooth_signal(tibia_acc_z, cutoff=15.0)
        
        # Add realistic noise
        noise_level = 0.5  # m/s²
        pelvis_acc_z += noise_level * np.random.randn(n_samples)
        tibia_left_acc_z = tibia_acc_z + noise_level * 1.5 * np.random.randn(n_samples)
        tibia_right_acc_z = tibia_acc_z + noise_level * 1.5 * np.random.randn(n_samples)
        
        # Generate horizontal accelerations (correlated with AP GRF)
        base_acc_ap = grf_data['grf_ap'] / body_mass
        pelvis_acc_y = self._smooth_signal(base_acc_ap * 0.6, cutoff=6.0) + noise_level * 0.5 * np.random.randn(n_samples)
        tibia_left_acc_y = base_acc_ap * 0.8 + noise_level * np.random.randn(n_samples)
        tibia_right_acc_y = base_acc_ap * 0.8 + noise_level * np.random.randn(n_samples)
        
        # Generate ML accelerations (smaller)
        base_acc_ml = grf_data['grf_ml'] / body_mass
        pelvis_acc_x = self._smooth_signal(base_acc_ml * 0.5, cutoff=5.0) + noise_level * 0.3 * np.random.randn(n_samples)
        tibia_left_acc_x = base_acc_ml * 0.7 + noise_level * 0.5 * np.random.randn(n_samples)
        tibia_right_acc_x = base_acc_ml * 0.7 + noise_level * 0.5 * np.random.randn(n_samples)
        
        return {
            'pelvis_x': pelvis_acc_x,
            'pelvis_y': pelvis_acc_y,
            'pelvis_z': pelvis_acc_z,
            'tibia_left_x': tibia_left_acc_x,
            'tibia_left_y': tibia_left_acc_y,
            'tibia_left_z': tibia_left_acc_z,
            'tibia_right_x': tibia_right_acc_x,
            'tibia_right_y': tibia_right_acc_y,
            'tibia_right_z': tibia_right_acc_z
        }
    
    def _smooth_signal(self, data: np.ndarray, cutoff: float) -> np.ndarray:
        """Apply low-pass filter to smooth signal."""
        nyq = 0.5 * self.fs
        if cutoff >= nyq:
            return data
        b, a = signal.butter(2, cutoff / nyq, btype='low')
        return signal.filtfilt(b, a, data)
    
    def generate_flight_phase(self, duration: float, n_features: int = 9) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generate flight phase data (GRF = 0, small IMU noise).
        
        Args:
            duration: Flight duration in seconds
            n_features: Number of IMU features
            
        Returns:
            IMU data and GRF data for flight phase
        """
        n_samples = int(duration * self.fs)
        
        # Small accelerations during flight (mainly from body oscillation)
        imu_data = 0.5 * np.random.randn(n_samples, n_features)
        
        # GRF is zero during flight
        grf_data = np.zeros((n_samples, 3))
        
        return imu_data, grf_data
    
    def generate_subject_data(self, subject_id: int, body_mass: float,
                               n_strides: int = 40, velocity: float = 3.3,
                               stride_freq: float = None) -> pd.DataFrame:
        """
        Generate complete running data for one subject.
        
        Args:
            subject_id: Subject identifier
            body_mass: Body mass in kg
            n_strides: Number of strides to generate
            velocity: Running velocity in m/s
            stride_freq: Stride frequency in Hz (calculated if None)
            
        Returns:
            DataFrame with IMU and GRF data
        """
        # Calculate stride parameters
        if stride_freq is None:
            # Typical relationship between velocity and stride frequency
            stride_freq = 0.5 + 0.25 * velocity  # Approximate relationship
        
        stride_duration = 1.0 / stride_freq
        stance_duration = 0.35 * stride_duration  # ~35% stance phase
        flight_duration = stride_duration - stance_duration
        
        all_data = []
        sample_idx = 0
        
        for stride in range(n_strides):
            # Add some natural variation
            stance_var = stance_duration * (1 + 0.05 * np.random.randn())
            flight_var = flight_duration * (1 + 0.08 * np.random.randn())
            
            # Generate stance phase
            grf_data = self.generate_stance_phase(stance_var, body_mass, velocity)
            imu_data = self.generate_imu_from_grf(grf_data, body_mass)
            
            n_stance = len(grf_data['time'])
            
            for i in range(n_stance):
                all_data.append({
                    'sample_idx': sample_idx,
                    'subject_id': subject_id,
                    'stride_num': stride,
                    'phase': 'stance',
                    'time': grf_data['time'][i],
                    # IMU data
                    'pelvis_acc_x': imu_data['pelvis_x'][i],
                    'pelvis_acc_y': imu_data['pelvis_y'][i],
                    'pelvis_acc_z': imu_data['pelvis_z'][i],
                    'tibia_left_acc_x': imu_data['tibia_left_x'][i],
                    'tibia_left_acc_y': imu_data['tibia_left_y'][i],
                    'tibia_left_acc_z': imu_data['tibia_left_z'][i],
                    'tibia_right_acc_x': imu_data['tibia_right_x'][i],
                    'tibia_right_acc_y': imu_data['tibia_right_y'][i],
                    'tibia_right_acc_z': imu_data['tibia_right_z'][i],
                    # GRF data (normalized by body weight)
                    'grf_ml': grf_data['grf_ml'][i] / (body_mass * 9.81),
                    'grf_ap': grf_data['grf_ap'][i] / (body_mass * 9.81),
                    'grf_vertical': grf_data['grf_vertical'][i] / (body_mass * 9.81),
                    # Metadata
                    'velocity': velocity,
                    'body_mass': body_mass
                })
                sample_idx += 1
            
            # Generate flight phase
            imu_flight, grf_flight = self.generate_flight_phase(flight_var)
            n_flight = imu_flight.shape[0]
            
            for i in range(n_flight):
                all_data.append({
                    'sample_idx': sample_idx,
                    'subject_id': subject_id,
                    'stride_num': stride,
                    'phase': 'flight',
                    'time': i / self.fs,
                    'pelvis_acc_x': imu_flight[i, 0],
                    'pelvis_acc_y': imu_flight[i, 1],
                    'pelvis_acc_z': imu_flight[i, 2],
                    'tibia_left_acc_x': imu_flight[i, 3],
                    'tibia_left_acc_y': imu_flight[i, 4],
                    'tibia_left_acc_z': imu_flight[i, 5],
                    'tibia_right_acc_x': imu_flight[i, 6],
                    'tibia_right_acc_y': imu_flight[i, 7],
                    'tibia_right_acc_z': imu_flight[i, 8],
                    'grf_ml': 0.0,
                    'grf_ap': 0.0,
                    'grf_vertical': 0.0,
                    'velocity': velocity,
                    'body_mass': body_mass
                })
                sample_idx += 1
        
        return pd.DataFrame(all_data)


def generate_demo_dataset(n_subjects: int = 6, n_strides_per_condition: int = 20,
                          output_dir: str = './demo_data',
                          seed: int = 42) -> Tuple[pd.DataFrame, Dict[int, float]]:
    """
    Generate a complete demo dataset similar to the paper's protocol.
    
    Protocol:
    - Multiple subjects
    - 3 velocities: 10, 12, 14 km/h (2.78, 3.33, 3.89 m/s)
    - 3 stride frequencies: preferred, +10%, -10%
    
    Args:
        n_subjects: Number of subjects to generate
        n_strides_per_condition: Number of strides per condition
        output_dir: Directory to save CSV files
        seed: Random seed
        
    Returns:
        Combined DataFrame and dictionary of body masses
    """
    import os
    os.makedirs(output_dir, exist_ok=True)
    
    generator = RunningDataGenerator(sampling_freq=240.0, seed=seed)
    
    # Subject characteristics (similar to paper: 73.7 ± 17.5 kg)
    np.random.seed(seed)
    body_masses = {}
    for subj in range(1, n_subjects + 1):
        body_masses[subj] = 73.7 + 17.5 * np.random.randn()
        body_masses[subj] = np.clip(body_masses[subj], 50, 100)  # Reasonable range
    
    # Velocities
    velocities = [2.78, 3.33, 3.89]  # 10, 12, 14 km/h
    velocity_names = ['10kmh', '12kmh', '14kmh']
    
    # Stride frequencies (relative to preferred)
    sf_multipliers = [0.9, 1.0, 1.1]  # -10%, preferred, +10%
    sf_names = ['low', 'preferred', 'high']
    
    all_data = []
    
    for subj_id in range(1, n_subjects + 1):
        print(f"Generating data for Subject {subj_id}...")
        body_mass = body_masses[subj_id]
        
        for vel, vel_name in zip(velocities, velocity_names):
            # Calculate preferred stride frequency for this velocity
            preferred_sf = 0.5 + 0.25 * vel
            
            for sf_mult, sf_name in zip(sf_multipliers, sf_names):
                stride_freq = preferred_sf * sf_mult
                
                # Generate data for this condition
                df = generator.generate_subject_data(
                    subject_id=subj_id,
                    body_mass=body_mass,
                    n_strides=n_strides_per_condition,
                    velocity=vel,
                    stride_freq=stride_freq
                )
                
                # Add condition labels
                df['velocity_condition'] = vel_name
                df['stride_freq_condition'] = sf_name
                
                all_data.append(df)
    
    # Combine all data
    combined_df = pd.concat(all_data, ignore_index=True)
    
    # Save combined dataset
    combined_df.to_csv(f'{output_dir}/demo_running_data.csv', index=False)
    print(f"\nSaved combined dataset to {output_dir}/demo_running_data.csv")
    print(f"Total samples: {len(combined_df)}")
    print(f"Total subjects: {n_subjects}")
    
    # Save body masses
    body_mass_df = pd.DataFrame([
        {'subject_id': k, 'body_mass': v} for k, v in body_masses.items()
    ])
    body_mass_df.to_csv(f'{output_dir}/subject_info.csv', index=False)
    print(f"Saved subject info to {output_dir}/subject_info.csv")
    
    # Save stance-only data (as used in the paper for evaluation)
    stance_df = combined_df[combined_df['phase'] == 'stance'].copy()
    stance_df.to_csv(f'{output_dir}/demo_running_data_stance_only.csv', index=False)
    print(f"Saved stance-only dataset ({len(stance_df)} samples)")
    
    return combined_df, body_masses


def create_minimal_demo_csv():
    """
    Create minimal demo CSV files for quick testing.
    """
    generator = RunningDataGenerator(sampling_freq=240.0, seed=42)
    
    # Generate one subject, one condition
    df = generator.generate_subject_data(
        subject_id=1,
        body_mass=70.0,
        n_strides=5,
        velocity=3.33
    )
    
    return df


if __name__ == "__main__":
    print("="*60)
    print("Generating Demo Dataset for GRF Estimation")
    print("="*60)
    
    # Generate full demo dataset
    df, body_masses = generate_demo_dataset(
        n_subjects=6,
        n_strides_per_condition=20,
        output_dir='./demo_data',
        seed=42
    )
    
    print("\n" + "="*60)
    print("Dataset Statistics")
    print("="*60)
    print(f"\nSubject body masses:")
    for subj, mass in body_masses.items():
        print(f"  Subject {subj}: {mass:.1f} kg")
    
    print(f"\nData shape: {df.shape}")
    print(f"\nColumns: {list(df.columns)}")
    
    print("\n" + "="*60)
    print("Sample Data Preview")
    print("="*60)
    print(df.head(10))
