import abc
import logging
import os
import sys
import numpy as np
import pandas as pd

from typing import Tuple, List
from sklearn.preprocessing import StandardScaler


# Add stdout handler, with level INFO
console = logging.StreamHandler(sys.stdout)
console.setLevel(logging.DEBUG)
formater = logging.Formatter("%(name)-13s: %(levelname)-8s %(message)s")
console.setFormatter(formater)
logging.getLogger(__name__).addHandler(console)


class BaseModel(abc.ABC):
    def __init__(self, log_dirs: str = "logs"):

        self.logs_dir = log_dirs
        self.model = None

    def load_csv(
        self, dataset_path: str, feature_columns: List[str], label_columns: List[str]
    ) -> Tuple[np.array, np.array]:

        if not os.path.exists(dataset_path):
            raise ValueError(f"No data found at {dataset_path}")
        else:
            df = pd.read_csv(dataset_path)
            X = df[feature_columns].values
            y = df[label_columns].values

        self.input_dim = X.shape[1]
        self.output_dim = y.shape[1]

        return X, y

    def load_numpy(self, dataset_path: str) -> Tuple[np.array, np.array]:

        X = np.load(os.path.join(dataset_path, "x_set.npy"))
        y = np.load(os.path.join(dataset_path, "y_set.npy"))
        self.input_dim = X.shape[1]
        self.output_dim = y.shape[1]

        return X, y

    def scale_data(self, X, y):

        self.xscalar = StandardScaler()
        self.yscalar = StandardScaler()

        X_scaled = self.xscalar.fit_transform(X)
        y_scaled = self.yscalar.fit_transform(y)

        return X_scaled, y_scaled

    def build_model(self):

        raise NotImplementedError

    def fit(self, X, y, scale_data: bool = False):

        if not self.model:
            raise ValueError("Please build the model first")

        if scale_data:
            X, y = self.scale_data(X, y)
        self.model.fit(X, y)

    def predict(self, inverse_transform: bool = False):


        if not self.model:
            raise ValueError("Please build the model first")
        
        else:
            preds = self.model.predict(X, y)
            if inverse_transform:
                preds = self.yscalar(preds)

            return preds

    def evaluate(self, test_data: np.array):

        if not self.model:
            raise Exception("No model found, please run fit first")