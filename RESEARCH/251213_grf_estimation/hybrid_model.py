"""
Hybrid Model for 3D Ground Reaction Force Estimation during Running
Based on: Scheltinga et al. (2023) "Estimating 3D ground reaction forces in running 
using three inertial measurement units"
DOI: 10.3389/fspor.2023.1176466

This implementation includes:
1. Physical model for vertical GRF estimation
2. Direct ANN model for 3D GRF estimation
3. Hybrid model combining physical model output with ANN
4. Ensemble model using multiple train/validation splits
"""

import numpy as np
import pandas as pd
from scipy import signal
from scipy.stats import pearsonr
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers
from sklearn.model_selection import LeaveOneGroupOut
from typing import Tuple, List, Dict, Optional
import warnings
warnings.filterwarnings('ignore')


class DataPreprocessor:
    """
    Data preprocessing class for IMU and GRF data.
    Handles filtering and normalization as described in the paper.
    """
    
    def __init__(self, sampling_freq: float = 240.0):
        """
        Initialize preprocessor.
        
        Args:
            sampling_freq: Sampling frequency in Hz (default 240Hz as in paper)
        """
        self.fs = sampling_freq
        
    def butter_lowpass_filter(self, data: np.ndarray, cutoff: float, 
                               order: int = 3) -> np.ndarray:
        """
        Apply bidirectional Butterworth low-pass filter.
        
        Args:
            data: Input signal (1D or 2D array)
            cutoff: Cutoff frequency in Hz
            order: Filter order
            
        Returns:
            Filtered signal
        """
        nyq = 0.5 * self.fs
        normalized_cutoff = cutoff / nyq
        
        # Ensure normalized cutoff is valid
        if normalized_cutoff >= 1.0:
            return data.copy()
        
        b, a = signal.butter(order, normalized_cutoff, btype='low')
        
        # Calculate minimum padlen for filtfilt
        padlen = 3 * max(len(a), len(b))
        
        # Apply filtfilt for zero-phase filtering (bidirectional)
        if data.ndim == 1:
            if len(data) <= padlen:
                # Data too short for filtering, return as-is
                return data.copy()
            return signal.filtfilt(b, a, data)
        else:
            # Apply to each column
            filtered = np.zeros_like(data)
            for i in range(data.shape[1]):
                if len(data[:, i]) <= padlen:
                    filtered[:, i] = data[:, i]
                else:
                    filtered[:, i] = signal.filtfilt(b, a, data[:, i])
            return filtered
    
    def preprocess_imu_for_ann(self, imu_data: np.ndarray) -> np.ndarray:
        """
        Preprocess IMU data for ANN input.
        Apply 3rd order Butterworth low-pass filter with 10Hz cutoff.
        
        Args:
            imu_data: IMU acceleration data (n_samples, n_features)
            
        Returns:
            Filtered IMU data
        """
        return self.butter_lowpass_filter(imu_data, cutoff=10.0, order=3)
    
    def preprocess_imu_for_physical(self, pelvis_acc_z: np.ndarray, 
                                     tibia_left_acc_z: np.ndarray,
                                     tibia_right_acc_z: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Preprocess IMU data for physical model.
        
        Args:
            pelvis_acc_z: Pelvis vertical acceleration
            tibia_left_acc_z: Left tibia vertical acceleration
            tibia_right_acc_z: Right tibia vertical acceleration
            
        Returns:
            Filtered accelerations (pelvis, left tibia, right tibia)
        """
        # Pelvis: 2nd order Butterworth, 5.97Hz cutoff
        pelvis_filtered = self.butter_lowpass_filter(pelvis_acc_z, cutoff=5.97, order=2)
        
        # Tibias: 1st order Butterworth, 8.74Hz cutoff
        tibia_left_filtered = self.butter_lowpass_filter(tibia_left_acc_z, cutoff=8.74, order=1)
        tibia_right_filtered = self.butter_lowpass_filter(tibia_right_acc_z, cutoff=8.74, order=1)
        
        return pelvis_filtered, tibia_left_filtered, tibia_right_filtered
    
    def preprocess_grf(self, grf_data: np.ndarray, cutoff: float = 30.0) -> np.ndarray:
        """
        Preprocess GRF data.
        Apply 6th order Butterworth low-pass filter with 30Hz cutoff.
        
        Args:
            grf_data: GRF data (n_samples, 3) for ML, AP, V directions
            
        Returns:
            Filtered GRF data
        """
        return self.butter_lowpass_filter(grf_data, cutoff=cutoff, order=6)
    
    def normalize_grf_by_bodyweight(self, grf_data: np.ndarray, 
                                     body_mass: float) -> np.ndarray:
        """
        Normalize GRF by body weight.
        
        Args:
            grf_data: GRF in Newtons
            body_mass: Body mass in kg
            
        Returns:
            GRF normalized by body weight (BW)
        """
        body_weight = body_mass * 9.81
        return grf_data / body_weight


class PhysicalModel:
    """
    Physical model for vertical GRF estimation based on Newton's second law.
    
    eGRF = (mb * g) + Σ(mb * WFi * az,i)
    
    Where:
    - mb: body mass
    - g: gravitational acceleration (9.81 m/s²)
    - WFi: weight factor for sensor i
    - az,i: vertical acceleration from sensor i
    """
    
    def __init__(self, body_mass: float, sampling_freq: float = 240.0):
        """
        Initialize physical model.
        
        Args:
            body_mass: Subject's body mass in kg
            sampling_freq: Sampling frequency in Hz
        """
        self.body_mass = body_mass
        self.g = 9.81
        self.fs = sampling_freq
        
        # Weight factors from the paper
        self.wf_pelvis = 0.55
        self.wf_tibia = 0.23  # Same for both tibias
        
        self.preprocessor = DataPreprocessor(sampling_freq)
    
    def estimate_vertical_grf(self, pelvis_acc_z: np.ndarray,
                               tibia_left_acc_z: np.ndarray,
                               tibia_right_acc_z: np.ndarray,
                               current_foot: str = 'left') -> np.ndarray:
        """
        Estimate vertical GRF using the physical model.
        
        Args:
            pelvis_acc_z: Pelvis sensor-free acceleration in vertical direction (m/s²)
            tibia_left_acc_z: Left tibia sensor-free acceleration in vertical direction
            tibia_right_acc_z: Right tibia sensor-free acceleration in vertical direction
            current_foot: Which foot is in stance ('left' or 'right')
            
        Returns:
            Estimated vertical GRF in Newtons
        """
        # Apply appropriate filters
        pelvis_filtered, tibia_left_filtered, tibia_right_filtered = \
            self.preprocessor.preprocess_imu_for_physical(
                pelvis_acc_z, tibia_left_acc_z, tibia_right_acc_z
            )
        
        # Calculate vertical GRF
        # Base: body weight
        grf = np.ones_like(pelvis_filtered) * self.body_mass * self.g
        
        # Add pelvis contribution
        grf += self.body_mass * self.wf_pelvis * pelvis_filtered
        
        # Add tibia contributions (use the stance leg's tibia)
        if current_foot == 'left':
            grf += self.body_mass * self.wf_tibia * tibia_left_filtered
        else:
            grf += self.body_mass * self.wf_tibia * tibia_right_filtered
        
        return grf
    
    def estimate_vertical_grf_both_legs(self, pelvis_acc_z: np.ndarray,
                                         tibia_left_acc_z: np.ndarray,
                                         tibia_right_acc_z: np.ndarray) -> np.ndarray:
        """
        Estimate vertical GRF using both tibia sensors (averaged contribution).
        This is useful when stance leg is unknown or for continuous estimation.
        
        Args:
            pelvis_acc_z: Pelvis sensor-free acceleration in vertical direction
            tibia_left_acc_z: Left tibia sensor-free acceleration
            tibia_right_acc_z: Right tibia sensor-free acceleration
            
        Returns:
            Estimated vertical GRF in Newtons
        """
        pelvis_filtered, tibia_left_filtered, tibia_right_filtered = \
            self.preprocessor.preprocess_imu_for_physical(
                pelvis_acc_z, tibia_left_acc_z, tibia_right_acc_z
            )
        
        # Calculate vertical GRF with both tibias
        grf = np.ones_like(pelvis_filtered) * self.body_mass * self.g
        grf += self.body_mass * self.wf_pelvis * pelvis_filtered
        grf += self.body_mass * self.wf_tibia * tibia_left_filtered
        grf += self.body_mass * self.wf_tibia * tibia_right_filtered
        
        return grf


class ANNModel:
    """
    Artificial Neural Network model for GRF estimation.
    
    Architecture (from paper):
    - 2 hidden layers with 100 neurons each
    - ReLU activation
    - Adam optimizer
    - MSE loss
    - 1000 epochs with early stopping (patience=100)
    - Batch size: 250
    """
    
    def __init__(self, input_dim: int, output_dim: int = 3, 
                 hidden_units: int = 100, n_layers: int = 2):
        """
        Initialize ANN model.
        
        Args:
            input_dim: Number of input features
            output_dim: Number of output features (3 for 3D GRF)
            hidden_units: Number of neurons per hidden layer
            n_layers: Number of hidden layers
        """
        self.input_dim = input_dim
        self.output_dim = output_dim
        self.hidden_units = hidden_units
        self.n_layers = n_layers
        self.model = None
        
    def build_model(self) -> keras.Model:
        """Build and compile the ANN model."""
        model = keras.Sequential()
        
        # Input layer
        model.add(layers.Input(shape=(self.input_dim,)))
        
        # Hidden layers
        for _ in range(self.n_layers):
            model.add(layers.Dense(self.hidden_units, activation='relu'))
        
        # Output layer
        model.add(layers.Dense(self.output_dim, activation='linear'))
        
        # Compile
        model.compile(
            optimizer=keras.optimizers.Adam(),
            loss='mse'
        )
        
        self.model = model
        return model
    
    def train(self, X_train: np.ndarray, y_train: np.ndarray,
              X_val: np.ndarray, y_val: np.ndarray,
              epochs: int = 1000, batch_size: int = 250,
              patience: int = 100, verbose: int = 0) -> keras.callbacks.History:
        """
        Train the model.
        
        Args:
            X_train: Training input data
            y_train: Training target data
            X_val: Validation input data
            y_val: Validation target data
            epochs: Maximum number of epochs
            batch_size: Batch size
            patience: Early stopping patience
            verbose: Verbosity level
            
        Returns:
            Training history
        """
        if self.model is None:
            self.build_model()
        
        # Early stopping callback
        early_stopping = keras.callbacks.EarlyStopping(
            monitor='val_loss',
            patience=patience,
            restore_best_weights=True
        )
        
        history = self.model.fit(
            X_train, y_train,
            validation_data=(X_val, y_val),
            epochs=epochs,
            batch_size=batch_size,
            callbacks=[early_stopping],
            verbose=verbose
        )
        
        return history
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Make predictions.
        
        Args:
            X: Input data
            
        Returns:
            Predicted GRF
        """
        if self.model is None:
            raise ValueError("Model not trained. Call train() first.")
        return self.model.predict(X, verbose=0)
    
    def get_weights(self):
        """Get model weights."""
        if self.model is None:
            return None
        return self.model.get_weights()
    
    def set_weights(self, weights):
        """Set model weights."""
        if self.model is None:
            self.build_model()
        self.model.set_weights(weights)


class DirectModel:
    """
    Direct machine learning model for 3D GRF estimation.
    Uses only IMU data as input (no physical model).
    """
    
    def __init__(self, sampling_freq: float = 240.0):
        """
        Initialize direct model.
        
        Args:
            sampling_freq: Sampling frequency in Hz
        """
        self.fs = sampling_freq
        self.preprocessor = DataPreprocessor(sampling_freq)
        self.ann = None
        
    def prepare_input(self, imu_data: np.ndarray) -> np.ndarray:
        """
        Prepare input features for the direct model.
        
        Args:
            imu_data: IMU data (n_samples, 9) 
                      [pelvis_x, pelvis_y, pelvis_z, 
                       tibia_left_x, tibia_left_y, tibia_left_z,
                       tibia_right_x, tibia_right_y, tibia_right_z]
                       
        Returns:
            Preprocessed input features
        """
        return self.preprocessor.preprocess_imu_for_ann(imu_data)
    
    def train(self, X_train: np.ndarray, y_train: np.ndarray,
              X_val: np.ndarray, y_val: np.ndarray, **kwargs):
        """Train the direct model."""
        X_train_processed = self.prepare_input(X_train)
        X_val_processed = self.prepare_input(X_val)
        
        self.ann = ANNModel(input_dim=X_train_processed.shape[1], output_dim=3)
        return self.ann.train(X_train_processed, y_train, 
                              X_val_processed, y_val, **kwargs)
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """Make predictions with the direct model."""
        X_processed = self.prepare_input(X)
        return self.ann.predict(X_processed)


class HybridModel:
    """
    Hybrid machine learning model for 3D GRF estimation.
    Combines physical model output with IMU data as input to ANN.
    """
    
    def __init__(self, body_mass: float, sampling_freq: float = 240.0):
        """
        Initialize hybrid model.
        
        Args:
            body_mass: Subject's body mass in kg
            sampling_freq: Sampling frequency in Hz
        """
        self.body_mass = body_mass
        self.fs = sampling_freq
        self.preprocessor = DataPreprocessor(sampling_freq)
        self.physical_model = PhysicalModel(body_mass, sampling_freq)
        self.ann = None
        
    def prepare_input(self, imu_data: np.ndarray) -> np.ndarray:
        """
        Prepare input features for the hybrid model.
        Adds physical model estimate as additional input.
        
        Args:
            imu_data: IMU data (n_samples, 9)
                      [pelvis_x, pelvis_y, pelvis_z, 
                       tibia_left_x, tibia_left_y, tibia_left_z,
                       tibia_right_x, tibia_right_y, tibia_right_z]
                       
        Returns:
            Preprocessed input features with physical model estimate
        """
        # Filter IMU data for ANN
        imu_filtered = self.preprocessor.preprocess_imu_for_ann(imu_data)
        
        # Extract vertical accelerations for physical model
        pelvis_acc_z = imu_data[:, 2]  # pelvis z
        tibia_left_acc_z = imu_data[:, 5]  # left tibia z
        tibia_right_acc_z = imu_data[:, 8]  # right tibia z
        
        # Get physical model estimate
        physical_grf = self.physical_model.estimate_vertical_grf_both_legs(
            pelvis_acc_z, tibia_left_acc_z, tibia_right_acc_z
        )
        
        # Normalize physical GRF by body weight for consistency
        body_weight = self.body_mass * 9.81
        physical_grf_normalized = physical_grf / body_weight
        
        # Concatenate: [filtered IMU data, physical GRF estimate]
        return np.column_stack([imu_filtered, physical_grf_normalized])
    
    def train(self, X_train: np.ndarray, y_train: np.ndarray,
              X_val: np.ndarray, y_val: np.ndarray, **kwargs):
        """Train the hybrid model."""
        X_train_processed = self.prepare_input(X_train)
        X_val_processed = self.prepare_input(X_val)
        
        # Input dim: 9 (IMU) + 1 (physical estimate) = 10
        self.ann = ANNModel(input_dim=X_train_processed.shape[1], output_dim=3)
        return self.ann.train(X_train_processed, y_train,
                              X_val_processed, y_val, **kwargs)
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """Make predictions with the hybrid model."""
        X_processed = self.prepare_input(X)
        return self.ann.predict(X_processed)


class EnsembleModel:
    """
    Ensemble model that combines multiple models trained with different 
    train/validation splits.
    
    As described in the paper:
    - 7 different models trained with random validation/training splits
    - Final prediction is the average of all ensemble members
    """
    
    def __init__(self, model_class, n_members: int = 7, **model_kwargs):
        """
        Initialize ensemble model.
        
        Args:
            model_class: Class of the base model (DirectModel or HybridModel)
            n_members: Number of ensemble members
            **model_kwargs: Keyword arguments for model initialization
        """
        self.model_class = model_class
        self.n_members = n_members
        self.model_kwargs = model_kwargs
        self.members = []
        
    def train(self, X: np.ndarray, y: np.ndarray, 
              subject_ids: np.ndarray, test_subject: int,
              n_val_subjects: int = 4, random_seed: int = 42,
              verbose: int = 0, **train_kwargs):
        """
        Train ensemble members with different train/validation splits.
        
        Args:
            X: Input data from all subjects except test subject
            y: Target data from all subjects except test subject
            subject_ids: Subject ID for each sample
            test_subject: Subject ID to hold out for testing
            n_val_subjects: Number of subjects to use for validation per member
            random_seed: Random seed for reproducibility
            verbose: Verbosity level
            **train_kwargs: Additional training arguments
        """
        self.members = []
        
        # Get unique subjects (excluding test subject)
        unique_subjects = np.unique(subject_ids[subject_ids != test_subject])
        n_train_subjects = len(unique_subjects) - n_val_subjects
        
        np.random.seed(random_seed)
        
        for i in range(self.n_members):
            if verbose:
                print(f"Training ensemble member {i+1}/{self.n_members}")
            
            # Random split of subjects into train and validation
            shuffled = np.random.permutation(unique_subjects)
            val_subjects = shuffled[:n_val_subjects]
            train_subjects = shuffled[n_val_subjects:]
            
            # Get train and validation indices
            train_mask = np.isin(subject_ids, train_subjects)
            val_mask = np.isin(subject_ids, val_subjects)
            
            X_train = X[train_mask]
            y_train = y[train_mask]
            X_val = X[val_mask]
            y_val = y[val_mask]
            
            # Create and train model
            model = self.model_class(**self.model_kwargs)
            model.train(X_train, y_train, X_val, y_val, 
                       verbose=0, **train_kwargs)
            
            self.members.append(model)
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Make predictions by averaging ensemble members.
        
        Args:
            X: Input data
            
        Returns:
            Averaged predictions from all ensemble members
        """
        if not self.members:
            raise ValueError("Ensemble not trained. Call train() first.")
        
        predictions = np.array([member.predict(X) for member in self.members])
        return np.mean(predictions, axis=0)
    
    def predict_with_uncertainty(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Make predictions with uncertainty estimation.
        
        Args:
            X: Input data
            
        Returns:
            Mean prediction and standard deviation across members
        """
        if not self.members:
            raise ValueError("Ensemble not trained. Call train() first.")
        
        predictions = np.array([member.predict(X) for member in self.members])
        return np.mean(predictions, axis=0), np.std(predictions, axis=0)


class ModelEvaluator:
    """
    Model evaluation utilities.
    Computes RMSE, rRMSE, Pearson correlation, and peak error.
    """
    
    @staticmethod
    def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
        """Calculate Root Mean Squared Error."""
        return np.sqrt(np.mean((y_true - y_pred) ** 2))
    
    @staticmethod
    def rrmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
        """
        Calculate relative RMSE (normalized by full range).
        rRMSE = RMSE / (max - min) * 100
        """
        rmse_val = ModelEvaluator.rmse(y_true, y_pred)
        range_val = np.max(y_true) - np.min(y_true)
        if range_val == 0:
            return np.inf
        return (rmse_val / range_val) * 100
    
    @staticmethod
    def pearson_r(y_true: np.ndarray, y_pred: np.ndarray) -> float:
        """Calculate Pearson correlation coefficient."""
        if len(y_true) < 2:
            return np.nan
        r, _ = pearsonr(y_true.flatten(), y_pred.flatten())
        return r
    
    @staticmethod
    def peak_error(y_true: np.ndarray, y_pred: np.ndarray) -> float:
        """
        Calculate peak error as percentage.
        |peak_pred - peak_true| / peak_true * 100
        """
        peak_true = np.max(y_true)
        peak_pred = np.max(y_pred)
        if peak_true == 0:
            return np.inf
        return np.abs(peak_pred - peak_true) / peak_true * 100
    
    @staticmethod
    def evaluate_3d_grf(y_true: np.ndarray, y_pred: np.ndarray, 
                        direction_names: List[str] = ['ML', 'AP', 'V']) -> Dict:
        """
        Evaluate 3D GRF predictions.
        
        Args:
            y_true: True GRF (n_samples, 3)
            y_pred: Predicted GRF (n_samples, 3)
            direction_names: Names for each direction
            
        Returns:
            Dictionary with evaluation metrics for each direction
        """
        results = {}
        
        for i, name in enumerate(direction_names):
            results[name] = {
                'RMSE': ModelEvaluator.rmse(y_true[:, i], y_pred[:, i]),
                'rRMSE': ModelEvaluator.rrmse(y_true[:, i], y_pred[:, i]),
                'Pearson_r': ModelEvaluator.pearson_r(y_true[:, i], y_pred[:, i])
            }
            
            # Peak error only for vertical direction
            if name == 'V':
                results[name]['Peak_error'] = ModelEvaluator.peak_error(
                    y_true[:, i], y_pred[:, i]
                )
        
        return results


def run_leave_one_subject_out_cv(X: np.ndarray, y: np.ndarray, 
                                  subject_ids: np.ndarray,
                                  body_masses: Dict[int, float],
                                  model_type: str = 'hybrid',
                                  n_ensemble_members: int = 7,
                                  verbose: int = 1) -> Dict:
    """
    Run leave-one-subject-out cross-validation.
    
    Args:
        X: Input data (n_samples, 9) - IMU data
        y: Target data (n_samples, 3) - 3D GRF
        subject_ids: Subject ID for each sample
        body_masses: Dictionary mapping subject ID to body mass
        model_type: 'direct' or 'hybrid'
        n_ensemble_members: Number of ensemble members
        verbose: Verbosity level
        
    Returns:
        Dictionary with evaluation results for each subject
    """
    unique_subjects = np.unique(subject_ids)
    results = {}
    
    logo = LeaveOneGroupOut()
    
    for train_idx, test_idx in logo.split(X, y, subject_ids):
        test_subject = subject_ids[test_idx][0]
        
        if verbose:
            print(f"\n{'='*50}")
            print(f"Testing on Subject {test_subject}")
            print(f"{'='*50}")
        
        X_train = X[train_idx]
        y_train = y[train_idx]
        X_test = X[test_idx]
        y_test = y[test_idx]
        train_subject_ids = subject_ids[train_idx]
        
        # Get body mass for test subject
        body_mass = body_masses.get(test_subject, 70.0)  # Default 70kg
        
        # Create ensemble model
        if model_type == 'hybrid':
            model_kwargs = {'body_mass': body_mass}
            ensemble = EnsembleModel(HybridModel, n_members=n_ensemble_members, 
                                     **model_kwargs)
        else:
            model_kwargs = {}
            ensemble = EnsembleModel(DirectModel, n_members=n_ensemble_members,
                                     **model_kwargs)
        
        # Train ensemble
        ensemble.train(X_train, y_train, train_subject_ids, test_subject,
                      verbose=verbose)
        
        # Make predictions
        y_pred = ensemble.predict(X_test)
        
        # Evaluate
        evaluation = ModelEvaluator.evaluate_3d_grf(y_test, y_pred)
        results[test_subject] = {
            'metrics': evaluation,
            'y_true': y_test,
            'y_pred': y_pred
        }
        
        if verbose:
            print(f"\nResults for Subject {test_subject}:")
            for direction, metrics in evaluation.items():
                print(f"  {direction}:")
                for metric_name, value in metrics.items():
                    print(f"    {metric_name}: {value:.4f}")
    
    return results


def print_summary_results(results: Dict):
    """Print summary of cross-validation results."""
    print("\n" + "="*60)
    print("SUMMARY RESULTS (Leave-One-Subject-Out Cross-Validation)")
    print("="*60)
    
    directions = ['ML', 'AP', 'V']
    metrics = ['RMSE', 'rRMSE', 'Pearson_r']
    
    for direction in directions:
        print(f"\n{direction} Direction:")
        for metric in metrics:
            values = [results[subj]['metrics'][direction][metric] 
                     for subj in results]
            mean_val = np.mean(values)
            std_val = np.std(values)
            print(f"  {metric}: {mean_val:.4f} ± {std_val:.4f}")
        
        if direction == 'V':
            peak_errors = [results[subj]['metrics'][direction]['Peak_error'] 
                          for subj in results]
            print(f"  Peak_error: {np.mean(peak_errors):.4f} ± {np.std(peak_errors):.4f}")


if __name__ == "__main__":
    # Example usage with demo data
    print("Hybrid Model for 3D GRF Estimation")
    print("Based on Scheltinga et al. (2023)")
    print("\nTo use this model, load your data and call:")
    print("  results = run_leave_one_subject_out_cv(X, y, subject_ids, body_masses)")
