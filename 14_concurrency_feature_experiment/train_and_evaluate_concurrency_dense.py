"""
Retrain Dense v1 with pencere-bazli concurrency/yogunluk feature'lari
eklenerek, 3 konfigurasyon (revize plan, kullanici onayli):

  A: 18 baseline + concurrency_src_1s_scaled                (tekli, en temiz sinyal)
  B: 18 baseline + byte_ratio_var_src_2s_wins_log_scaled     (tekli, winsorize+log ile duzeltilmis)
  C: 18 baseline + concurrency_src_1s + concurrency_dst_2s + byte_ratio_var_src_2s_wins_log_scaled
     (uc ailenin kombinasyonu, en dusuk oncelikli dst dahil ama tek radius)

Mimari/hiperparametreler/split/threshold_95 metodolojisi 13_temporal_feature_
experiment ve phase3_dense_autoencoder.ipynb ile birebir ayni; tek degisken
feature seti. 3 seed (0,1,2).

Her tekli-feature konfigurasyonu (A, B) icin knock-out ablasyonu: ayni
egitilmis modeller, inference'ta o feature(lar) benign-train ortalamasina
sabitlenerek yeniden degerlendiriliyor -- boylece performans degisiminin
gercekten o feature'dan mi, yoksa retrain jitter'indan/etkilesimden mi
geldigi ayirt ediliyor (13_temporal_feature_experiment'teki disiplin).
C icin de ayni sekilde, kombinasyondaki her feature tek tek dondurulerek
(marjinal katki) bir ablasyon tablosu uretiliyor.

Yazilanlar (13'teki gibi, sadece bu klasor icinde):
  models/{A,B,C}/autoencoder_seed{0,1,2}.keras
  results_{A,B,C}.csv (+_per_seed.csv)
  results_{A,B,C}_knockout*.csv
  training_meta.json
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd
import tensorflow as tf

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
ATTACK_TYPE_DIR = os.path.join(PROJECT_ROOT, "06_attack_type_analysis")
sys.path.insert(0, ATTACK_TYPE_DIR)
import evaluate_by_attack_type as single  # noqa: E402

FEATURES_ALL_WINDOWS = os.path.join(
    PROJECT_ROOT, "02_phase2_feature_extraction", "features_all_windows.csv")
DENSE_SPLIT_DIR = os.path.join(PROJECT_ROOT, "phase3_dense", "03_phase3_splits")
CONCURRENCY_PATH = os.path.join(HERE, "concurrency_features_all_rows.csv")
MODEL_ROOT = os.path.join(HERE, "models")

SEEDS = [0, 1, 2]

NEW_COLS = {
    "concurrency_src_1s": "concurrency_src_1s_scaled",
    "concurrency_dst_2s": "concurrency_dst_2s_scaled",
    "byte_ratio_var_src_2s_wins": "byte_ratio_var_src_2s_wins_log_scaled",
}

CONFIGS = {
    "A": ["concurrency_src_1s"],
    "B": ["byte_ratio_var_src_2s_wins"],
    "C": ["concurrency_src_1s", "concurrency_dst_2s", "byte_ratio_var_src_2s_wins"],
}


def build_model(n_features, seed):
    tf.keras.utils.set_random_seed(seed)
    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(n_features,)),
        tf.keras.layers.Dense(16, activation="relu", kernel_regularizer=tf.keras.regularizers.l2(1e-4)),
        tf.keras.layers.Dropout(0.15),
        tf.keras.layers.Dense(8, activation="relu", kernel_regularizer=tf.keras.regularizers.l2(1e-4), name="bottleneck"),
        tf.keras.layers.Dropout(0.15),
        tf.keras.layers.Dense(16, activation="relu", kernel_regularizer=tf.keras.regularizers.l2(1e-4)),
        tf.keras.layers.Dense(n_features, activation="linear"),
    ])
    model.compile(optimizer="adam", loss="mse")
    return model


def load_training_frames(feature_cols, concurrency):
    features = pd.read_csv(FEATURES_ALL_WINDOWS)
    for key, col in NEW_COLS.items():
        features[col] = concurrency.set_index("row_index").loc[features.index, col].values

    def take(name):
        idx = pd.read_csv(os.path.join(DENSE_SPLIT_DIR, f"{name}_indices.csv"))
        df = features.iloc[idx["row_index"].values].reset_index(drop=True)
        assert (df["is_attack"].values == idx["is_attack"].values).all()
        return df

    train_df, val_df = take("train"), take("val")
    assert (train_df["is_attack"] == 0).all()
    X_train = train_df[feature_cols].values.astype("float32")
    X_val_benign = val_df.loc[val_df["is_attack"] == 0, feature_cols].values.astype("float32")
    return X_train, X_val_benign, train_df


class ConcurrencyDenseBackend:
    """Same 4-method interface as before. `freeze_map` is {col_name: constant}
    for a knock-out ablation -- any subset of the model's own new columns."""

    def __init__(self, feature_cols, model_dir, val_benign_X, seeds=SEEDS, freeze_map=None):
        self.feature_cols = feature_cols
        self.model_dir = model_dir
        self.seeds = list(seeds)
        self.freeze_map = freeze_map or {}
        self.freeze_idx = {feature_cols.index(c): v for c, v in self.freeze_map.items()}
        self._val_benign_X = self._maybe_freeze(val_benign_X)

    def _maybe_freeze(self, X):
        if not self.freeze_idx:
            return X
        X = np.asarray(X).copy()
        for i, v in self.freeze_idx.items():
            X[:, i] = v
        return X

    def load(self, seed):
        return tf.keras.models.load_model(os.path.join(self.model_dir, f"autoencoder_seed{seed}.keras"))

    def errors(self, model, X, seed):
        Xf = self._maybe_freeze(np.asarray(X))
        recon = model.predict(Xf, verbose=0)
        return np.mean(np.square(Xf - recon), axis=1)

    def threshold(self, model, seed):
        val_errors = self.errors(model, self._val_benign_X, seed)
        return float(np.percentile(val_errors, 95))


def summarize(per_seed_df):
    metric_cols = ["pr_auc", "roc_auc", "f1", "benign_fpr", "attack_recall"]
    summary = per_seed_df.groupby(["attack_type", "n_benign", "n_attack"])[metric_cols].agg(["mean", "std"])
    summary.columns = [f"{c}_{s}" for c, s in summary.columns]
    return summary.reset_index()


def run_eval(feature_cols, model_dir, val_benign_X, df, freeze_map, tag):
    backend = ConcurrencyDenseBackend(feature_cols, model_dir, val_benign_X, freeze_map=freeze_map)
    print(f"\n##### evaluation: {tag} #####")
    rows = []
    for attack_type in single.ATTACK_TYPES:
        subset = df[(df["is_attack"] == 0) | (df["attack_type"] == attack_type)].copy()
        rows.extend(single.evaluate_group(subset, feature_cols, attack_type, backend=backend))
    per_seed = pd.DataFrame(rows)
    return per_seed, summarize(per_seed)


def main():
    feature_cols_18 = single.load_feature_cols()
    concurrency = pd.read_csv(CONCURRENCY_PATH)

    train_means = {}
    train_idx = pd.read_csv(os.path.join(DENSE_SPLIT_DIR, "train_indices.csv"))
    conc_idx = concurrency.set_index("row_index")
    for key, col in NEW_COLS.items():
        train_means[col] = float(conc_idx.loc[train_idx["row_index"].values, col].mean())
    print("benign-train means (knock-out constants):", train_means)

    df18 = single.assemble_labeled_features_df(feature_cols_18)
    for key, col in NEW_COLS.items():
        df18[col] = conc_idx.loc[df18["row_index"].values, col].values
        assert not df18[col].isna().any()

    all_meta = {}
    for cfg_name, keys in CONFIGS.items():
        added_cols = [NEW_COLS[k] for k in keys]
        feature_cols = feature_cols_18 + added_cols
        model_dir = os.path.join(MODEL_ROOT, cfg_name)
        os.makedirs(model_dir, exist_ok=True)

        X_train, X_val_benign, _ = load_training_frames(feature_cols, concurrency)
        print(f"\n=== config {cfg_name}: {added_cols} -> n_features={len(feature_cols)} ===")
        print(f"train={len(X_train)} (all benign), val_benign={len(X_val_benign)}")

        meta = []
        for seed in SEEDS:
            t0 = time.time()
            model = build_model(len(feature_cols), seed)
            early_stop = tf.keras.callbacks.EarlyStopping(
                monitor="val_loss", patience=12, restore_best_weights=True)
            history = model.fit(
                X_train, X_train, validation_data=(X_val_benign, X_val_benign),
                epochs=200, batch_size=128, shuffle=True, callbacks=[early_stop], verbose=0)
            model.save(os.path.join(model_dir, f"autoencoder_seed{seed}.keras"))
            meta.append({
                "seed": seed, "epochs_run": len(history.history["loss"]),
                "final_val_loss": float(np.min(history.history["val_loss"])),
                "train_time_sec": round(time.time() - t0, 1),
            })
            print(f"  seed={seed}: epochs={meta[-1]['epochs_run']} "
                  f"best_val_loss={meta[-1]['final_val_loss']:.5f} time={meta[-1]['train_time_sec']}s")
        all_meta[cfg_name] = {"feature_cols": feature_cols, "seeds": meta}

        # full-feature evaluation
        per_seed, summ = run_eval(feature_cols, model_dir, X_val_benign, df18, {}, f"{cfg_name} (full)")
        per_seed.to_csv(os.path.join(HERE, f"results_{cfg_name}_per_seed.csv"), index=False)
        summ.to_csv(os.path.join(HERE, f"results_{cfg_name}.csv"), index=False)

        # knock-out: freeze each of this config's new columns individually,
        # plus (for C) all three at once for the "fully knocked out" reference
        for col in added_cols:
            _, summ_ko = run_eval(feature_cols, model_dir, X_val_benign, df18,
                                  {col: train_means[col]}, f"{cfg_name} knockout[{col}]")
            summ_ko.to_csv(os.path.join(HERE, f"results_{cfg_name}_knockout_{col}.csv"), index=False)
        if len(added_cols) > 1:
            freeze_all = {c: train_means[c] for c in added_cols}
            _, summ_all = run_eval(feature_cols, model_dir, X_val_benign, df18,
                                   freeze_all, f"{cfg_name} knockout[ALL]")
            summ_all.to_csv(os.path.join(HERE, f"results_{cfg_name}_knockout_ALL.csv"), index=False)

    json.dump(all_meta, open(os.path.join(HERE, "training_meta.json"), "w"), indent=2)
    print("\nDone.")


if __name__ == "__main__":
    main()
