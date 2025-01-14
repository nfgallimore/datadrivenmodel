import logging
import os
import pathlib
import hydra
import numpy as np
import pandas as pd
from math import floor
from omegaconf import DictConfig, ListConfig, OmegaConf
from sklearn.metrics import r2_score

# TODO: use the model yaml to get the metric
# use the other metrics: MAE and MADE

logger = logging.getLogger("datamodeler")
dir_path = os.path.dirname(os.path.realpath(__file__))


# helper function that return None if element is not present in config
def hydra_read_config_var(cfg: DictConfig, level: str, key_name: str):
    """Reads the config file and returns the config as a dictionary"""

    return cfg[level][key_name] if key_name in cfg[level] else None


@hydra.main(config_path="conf", config_name="config")
def main(cfg: DictConfig) -> None:
    logger.info("Configuration: ")
    logger.info(f"\n{OmegaConf.to_yaml(cfg)}")

    # for readability, read common data args into variables
    input_cols = hydra_read_config_var(cfg, "data", "inputs")
    output_cols = hydra_read_config_var(cfg, "data", "outputs")
    augmented_cols = hydra_read_config_var(cfg, "data", "augmented_cols")

    iteration_order = hydra_read_config_var(cfg, "data", "iteration_order")
    episode_col = hydra_read_config_var(cfg, "data", "episode_col")
    iteration_col = hydra_read_config_var(cfg, "data", "iteration_col")
    dataset_path = hydra_read_config_var(cfg, "data", "path")
    max_rows = hydra_read_config_var(cfg, "data", "max_rows")
    test_perc = hydra_read_config_var(cfg, "data", "test_perc")

    diff_state = hydra_read_config_var(cfg, "data", "diff_state")
    concatenated_steps = hydra_read_config_var(cfg, "data", "concatenated_steps")
    concatenated_zero_padding = hydra_read_config_var(
        cfg, "data", "concatenated_zero_padding"
    )
    concatenate_var_length = hydra_read_config_var(cfg, "data", "concatenate_length")
    preprocess = hydra_read_config_var(cfg, "data", "preprocess")
    var_rename = hydra_read_config_var(cfg, "data", "var_rename")
    exogeneous_variables = hydra_read_config_var(cfg, "data", "exogeneous_variables")
    exogeneous_save_path = hydra_read_config_var(cfg, "data", "exogeneous_save_path")
    initial_values_save_path = hydra_read_config_var(
        cfg, "data", "initial_values_save_path"
    )

    # common model args
    save_path = cfg["model"]["saver"]["filename"]
    model_name = cfg["model"]["name"]
    run_sweep = cfg["model"]["sweep"]["run"]
    split_strategy = cfg["model"]["sweep"]["split_strategy"]
    results_csv_path = cfg["model"]["sweep"]["results_csv_path"]

    ts_model = False
    if model_name.lower() == "pytorch":
        from all_models import available_models
    elif model_name.lower() in ["nhits", "tftmodel", "varima", "ets", "sfarima"]:
        from timeseriesclass import darts_models as available_models

        ts_model = True
    else:
        from model_loader import available_models

    if ts_model:
        from timeseriesclass import TimeSeriesDarts

        Model = TimeSeriesDarts
        fit_params = cfg["model"]["fit_params"]
    else:
        Model = available_models[model_name]
        fit_params = None

    # TODO, decide whether to always save to outputs directory
    if cfg["data"]["full_or_relative"] == "relative":
        dataset_path = os.path.join(dir_path, dataset_path)

    save_path = os.path.join(dir_path, save_path)

    if type(input_cols) == ListConfig:
        input_cols = list(input_cols)
    if type(output_cols) == ListConfig:
        output_cols = list(output_cols)
    elif type(output_cols) == DictConfig:
        output_cols = list(output_cols.keys())
    if type(augmented_cols) == ListConfig:
        augmented_cols = list(augmented_cols)

    model = Model()

    # Add extra preprocessing step inside load_csv
    # should be done before concatenate_steps
    if ts_model:
        feature_cols = augmented_cols
        label_cols = output_cols
        train_df, test_df = model.load_from_csv(
            dataset_path,
            episode_col,
            iteration_col,
            label_cols,
            feature_cols,
            test_perc,
            return_ts=False,
            var_rename=var_rename,
            exogeneous_variables=exogeneous_variables,
            exogeneous_path=exogeneous_save_path,
        )
    else:
        X_train, y_train, X_test, y_test = model.load_csv(
            dataset_path=dataset_path,
            input_cols=input_cols,
            augm_cols=augmented_cols,
            output_cols=output_cols,
            iteration_order=iteration_order,
            episode_col=episode_col,
            iteration_col=iteration_col,
            # drop_nulls: bool = True,
            max_rows=max_rows,
            test_perc=test_perc,
            diff_state=diff_state,
            prep_pipeline=preprocess,
            var_rename=var_rename,
            concatenated_steps=concatenated_steps,
            concatenated_zero_padding=concatenated_zero_padding,
            concatenate_var_length=concatenate_var_length,
            exogeneous_variables=exogeneous_variables,
            exogeneous_save_path=exogeneous_save_path,
            initial_values_save_path=initial_values_save_path,
        )

    logger.info(
        f"From the full dataset, {test_perc * 100}% will be used for test, while {(1 - test_perc) * 100}% for training/sweeping"
    )
    # X_train, y_train = model.get_train_set(grouped_per_episode=False)
    # X_test, y_test = model.get_test_set(grouped_per_episode=False)

    # save training and test sets
    save_data_path = os.path.join(os.getcwd(), "data")
    if not os.path.exists(save_data_path):
        pathlib.Path(save_data_path).mkdir(parents=True, exist_ok=True)
    if not ts_model:
        logger.info(f"Saving data to {os.path.abspath(save_data_path)}")
        np.save(os.path.join(save_data_path, "x_train.npy"), X_train)
        np.save(os.path.join(save_data_path, "y_train.npy"), y_train)
        np.save(os.path.join(save_data_path, "x_test.npy"), X_test)
        np.save(os.path.join(save_data_path, "y_test.npy"), y_test)

    logger.info("Building model...")
    if ts_model:
        model.build_model(
            model_type=cfg["model"]["name"],
            scale_data=cfg["model"]["scale_data"],
            build_params=cfg["model"]["build_params"],
        )
    else:
        model.build_model(**cfg["model"]["build_params"])

    if run_sweep:
        # TODO: implement sweep for darts class
        params = OmegaConf.to_container(cfg["model"]["sweep"]["params"])
        logger.info(f"Sweeping with parameters: {params}")

        sweep_df = model.sweep(
            params=params,
            X=X_train,
            y=y_train,
            search_algorithm=cfg["model"]["sweep"]["search_algorithm"],
            num_trials=cfg["model"]["sweep"]["num_trials"],
            scoring_func=cfg["model"]["sweep"]["scoring_func"],
            results_csv_path=results_csv_path,
            splitting_criteria=split_strategy,
        )
        logger.info(f"Sweep results: {sweep_df}")
    else:
        logger.info("Fitting model...")
        if not ts_model:
            model.fit(X_train, y_train)
        else:
            model.fit(train_df, fit_params)

    if not ts_model:
        y_pred = model.predict(X_test)
        logger.info(f"R^2 score is {r2_score(y_test,y_pred)} for test set.")
        logger.info(f"Saving model to {save_path}")
        model.save_model(filename=save_path)

        ## save datasets
        pd.DataFrame(X_train, columns=model.feature_cols).to_csv(
            os.path.join(save_data_path, "x_train.csv")
        )
        pd.DataFrame(X_test, columns=model.feature_cols).to_csv(
            os.path.join(save_data_path, "x_test.csv")
        )
        pd.DataFrame(y_train, columns=model.label_cols).to_csv(
            os.path.join(save_data_path, "y_train.csv")
        )
        pd.DataFrame(y_test, columns=model.label_cols).to_csv(
            os.path.join(save_data_path, "y_test.csv")
        )

    else:
        y_pred = model.predict(test_df, {"n": 1})
        # ts_preds = model.predict(test_df, {"n": 1})
        # y_pred = []
        # for i in range(len(ts_preds)):
        #     y_pred.append(ts_preds[i].all_values().flatten())


if __name__ == "__main__":
    main()
