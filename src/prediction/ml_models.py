"""
Machine Learning models for FPL point prediction.

Uses gradient boosting (XGBoost/LightGBM) combined with rules-based approach
for improved prediction accuracy.
"""
from typing import Dict, List, Optional, Tuple
import json
from pathlib import Path
import warnings

# Optional ML dependencies (graceful degradation if not installed)
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    warnings.warn("NumPy not installed. ML features disabled.")

try:
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import mean_absolute_error, mean_squared_error
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    warnings.warn("scikit-learn not installed. ML features disabled.")

from ..data.models import Player


class MLPredictor:
    """
    Machine Learning predictor for FPL points.

    Uses ensemble of gradient boosting + rules-based predictions.
    """

    def __init__(self, model_path: Optional[Path] = None):
        """
        Initialize ML predictor.

        Args:
            model_path: Path to saved model (if exists)
        """
        self.model = None
        self.feature_names = None
        self.is_trained = False
        self.ensemble_weights = {'ml': 0.6, 'rules': 0.4}  # 60% ML, 40% rules

        if not HAS_SKLEARN or not HAS_NUMPY:
            warnings.warn("ML dependencies not available. Using rules-based only.")
            self.ensemble_weights = {'ml': 0.0, 'rules': 1.0}
            return

        if model_path and model_path.exists():
            self._load_model(model_path)
        else:
            # Initialize gradient boosting model
            self.model = GradientBoostingRegressor(
                n_estimators=100,
                learning_rate=0.1,
                max_depth=5,
                min_samples_split=20,
                min_samples_leaf=10,
                subsample=0.8,
                random_state=42
            )

    def _extract_features(self, player: Player, gameweek_data: Dict) -> Dict[str, float]:
        """
        Extract features for ML model.

        Args:
            player: Player object
            gameweek_data: Additional gameweek context

        Returns:
            Feature dict
        """
        features = {}

        # Player stats
        features['points_per_game'] = player.points_per_game
        features['form'] = player.form
        features['minutes'] = player.minutes
        features['price'] = player.price
        features['selected_by_percent'] = player.selected_by

        # Position encoding (one-hot)
        features['is_gk'] = 1.0 if player.position == 'GK' else 0.0
        features['is_def'] = 1.0 if player.position == 'DEF' else 0.0
        features['is_mid'] = 1.0 if player.position == 'MID' else 0.0
        features['is_fwd'] = 1.0 if player.position == 'FWD' else 0.0

        # Team stats (if available)
        if 'team_strength' in gameweek_data:
            team_data = gameweek_data['team_strength'].get(player.team_id, {})
            features['team_strength_attack'] = team_data.get('attack', 1000)
            features['team_strength_defence'] = team_data.get('defence', 1000)
        else:
            features['team_strength_attack'] = 1000
            features['team_strength_defence'] = 1000

        # Fixture difficulty (if available)
        if 'fixture_difficulty' in gameweek_data:
            features['fixture_difficulty'] = gameweek_data['fixture_difficulty']
        else:
            features['fixture_difficulty'] = 3.0  # Neutral

        # Recent form features
        if 'recent_points' in gameweek_data:
            recent = gameweek_data['recent_points']
            features['points_last_1'] = recent[0] if len(recent) > 0 else 0
            features['points_last_3'] = sum(recent[:3]) / 3 if len(recent) >= 3 else 0
            features['points_last_5'] = sum(recent[:5]) / 5 if len(recent) >= 5 else 0
        else:
            features['points_last_1'] = player.form
            features['points_last_3'] = player.form
            features['points_last_5'] = player.form

        # Advanced stats (if available)
        if 'xg' in gameweek_data:
            features['xg_per_90'] = gameweek_data['xg']
            features['xa_per_90'] = gameweek_data.get('xa', 0)
        else:
            features['xg_per_90'] = 0
            features['xa_per_90'] = 0

        return features

    def _features_to_array(self, features: Dict[str, float]) -> 'np.ndarray':
        """Convert feature dict to numpy array."""
        if self.feature_names is None:
            self.feature_names = sorted(features.keys())

        return np.array([features[name] for name in self.feature_names])

    def train(
        self,
        training_data: List[Dict],
        validation_split: float = 0.2
    ) -> Dict[str, float]:
        """
        Train ML model on historical data.

        Args:
            training_data: List of training examples
                Each example: {'features': {...}, 'target': float}
            validation_split: Fraction for validation

        Returns:
            Training metrics
        """
        if not HAS_SKLEARN or not HAS_NUMPY:
            return {'error': 'ML dependencies not available'}

        # Extract features and targets
        X = []
        y = []

        for example in training_data:
            features = example['features']
            if self.feature_names is None:
                self.feature_names = sorted(features.keys())

            X.append(self._features_to_array(features))
            y.append(example['target'])

        X = np.array(X)
        y = np.array(y)

        # Split train/validation
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=validation_split, random_state=42
        )

        # Train model
        print(f"Training ML model on {len(X_train)} examples...")
        self.model.fit(X_train, y_train)
        self.is_trained = True

        # Evaluate
        train_pred = self.model.predict(X_train)
        val_pred = self.model.predict(X_val)

        metrics = {
            'train_mae': mean_absolute_error(y_train, train_pred),
            'train_rmse': np.sqrt(mean_squared_error(y_train, train_pred)),
            'val_mae': mean_absolute_error(y_val, val_pred),
            'val_rmse': np.sqrt(mean_squared_error(y_val, val_pred)),
            'num_examples': len(training_data)
        }

        print(f"Training complete!")
        print(f"  Train MAE: {metrics['train_mae']:.2f}")
        print(f"  Val MAE: {metrics['val_mae']:.2f}")

        return metrics

    def predict(
        self,
        player: Player,
        gameweek_data: Dict,
        rules_based_prediction: float
    ) -> float:
        """
        Predict points using ensemble (ML + rules-based).

        Args:
            player: Player to predict for
            gameweek_data: Gameweek context
            rules_based_prediction: Prediction from AdvancedForecaster

        Returns:
            Ensemble prediction
        """
        if not self.is_trained or not HAS_SKLEARN or not HAS_NUMPY:
            # Fallback to rules-based only
            return rules_based_prediction

        # Extract features
        features = self._extract_features(player, gameweek_data)
        X = self._features_to_array(features).reshape(1, -1)

        # ML prediction
        ml_prediction = self.model.predict(X)[0]

        # Ensemble
        ensemble_prediction = (
            self.ensemble_weights['ml'] * ml_prediction +
            self.ensemble_weights['rules'] * rules_based_prediction
        )

        return ensemble_prediction

    def save_model(self, path: Path):
        """Save trained model to disk."""
        if not self.is_trained:
            raise ValueError("Model not trained yet")

        import pickle

        model_data = {
            'model': self.model,
            'feature_names': self.feature_names,
            'ensemble_weights': self.ensemble_weights
        }

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'wb') as f:
            pickle.dump(model_data, f)

        print(f"Model saved to {path}")

    def _load_model(self, path: Path):
        """Load trained model from disk."""
        import pickle

        with open(path, 'rb') as f:
            model_data = pickle.load(f)

        self.model = model_data['model']
        self.feature_names = model_data['feature_names']
        self.ensemble_weights = model_data.get('ensemble_weights', {'ml': 0.6, 'rules': 0.4})
        self.is_trained = True

        print(f"Model loaded from {path}")


class OnlineTrainer:
    """
    Enables continuous online learning from weekly results.

    Collects actual results and incrementally updates model.
    """

    def __init__(self, data_path: Path = Path("data/ml_training")):
        self.data_path = data_path
        self.data_path.mkdir(parents=True, exist_ok=True)

    def record_gameweek_results(
        self,
        gameweek: int,
        predictions: List[Dict],
        actuals: Dict[int, float]
    ):
        """
        Record predictions and actual results for a gameweek.

        Args:
            gameweek: Gameweek number
            predictions: List of predictions made
            actuals: Dict mapping player_id -> actual points
        """
        # Create training examples
        examples = []

        for pred in predictions:
            player_id = pred['player_id']
            if player_id in actuals:
                example = {
                    'gameweek': gameweek,
                    'player_id': player_id,
                    'features': pred['features'],
                    'predicted': pred['predicted'],
                    'actual': actuals[player_id],
                    'error': abs(pred['predicted'] - actuals[player_id])
                }
                examples.append(example)

        # Save to file
        output_file = self.data_path / f"gw{gameweek}_results.json"
        with open(output_file, 'w') as f:
            json.dump(examples, f, indent=2)

        print(f"Recorded {len(examples)} examples for GW{gameweek}")

    def load_training_data(
        self,
        start_gw: int = 1,
        end_gw: int = 38
    ) -> List[Dict]:
        """
        Load accumulated training data.

        Args:
            start_gw: Start gameweek
            end_gw: End gameweek

        Returns:
            List of training examples
        """
        all_examples = []

        for gw in range(start_gw, end_gw + 1):
            file_path = self.data_path / f"gw{gw}_results.json"
            if file_path.exists():
                with open(file_path) as f:
                    examples = json.load(f)
                    all_examples.extend(examples)

        print(f"Loaded {len(all_examples)} training examples from GW{start_gw}-{end_gw}")
        return all_examples

    def retrain_model(
        self,
        model: MLPredictor,
        start_gw: int = 1,
        end_gw: int = 38
    ) -> Dict:
        """
        Retrain model on accumulated data.

        Args:
            model: MLPredictor to retrain
            start_gw: Start gameweek
            end_gw: End gameweek

        Returns:
            Training metrics
        """
        # Load data
        examples = self.load_training_data(start_gw, end_gw)

        if not examples:
            print("No training data available")
            return {}

        # Convert to training format
        training_data = [
            {'features': ex['features'], 'target': ex['actual']}
            for ex in examples
        ]

        # Train
        metrics = model.train(training_data)

        return metrics


def get_ml_predictor(model_path: Optional[Path] = None) -> MLPredictor:
    """
    Get ML predictor instance (singleton pattern).

    Args:
        model_path: Optional path to saved model

    Returns:
        MLPredictor instance
    """
    if model_path is None:
        model_path = Path("data/ml_models/fpl_predictor.pkl")

    return MLPredictor(model_path if model_path.exists() else None)
