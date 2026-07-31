"""
Build a segmented-injection test sequence: instead of the shuffled benign+
attack test set used everywhere else, arrange the SAME flows (no new/synthetic
data, no resampling with replacement) into one ordered stream where each
attack type appears as one contiguous block, with benign segments in between
and on both ends -- so a plot of reconstruction error vs. stream position
shows clean before/after context around every block boundary.

Source data: 06_attack_type_analysis/test_with_attack_type.csv (already
carries attack_type per flow, including "benign"). This script only reorders
those existing rows; it does not touch that file, features_all_windows.*,
or any model.

Sequence layout, for BLOCK_ORDER = [t1, t2, t3] (default:
apache_bench -> slowloris -> portscan):

    benign_seg0 | attack_block(t1) | benign_seg1 | attack_block(t2) |
    benign_seg2 | attack_block(t3) | benign_seg3

- The full benign pool (all is_attack==0 rows) is split into
  len(BLOCK_ORDER)+1 contiguous, near-equal segments, in ts order.
- Each attack block uses ALL of that attack_type's existing flows from
  test_with_attack_type.csv, in ts order (no shuffling, no replacement,
  no new flows).

BLOCK_ORDER is configurable via --order (comma-separated attack_type names)
so the sequence isn't hardcoded to one ordering.

Output: 07_segmented_injection/segmented_sequence.csv, columns:
    position, segment_id, segment_label, row_index, window_id, is_attack, ts
segment_label is "benign" or the attack_type name; segment_id increments at
every block boundary (benign and attack alike) so plotting code can draw a
vertical line at each segment_id change.
"""
import argparse
import json
import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
LABELED_TEST_PATH = os.path.join(PROJECT_ROOT, "06_attack_type_analysis", "test_with_attack_type.csv")

OUT_SEQUENCE_PATH = os.path.join(HERE, "segmented_sequence.csv")
OUT_CONFIG_PATH = os.path.join(HERE, "segmented_sequence_config.json")

DEFAULT_BLOCK_ORDER = ["apache_bench", "slowloris", "portscan"]


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--order", type=str, default=",".join(DEFAULT_BLOCK_ORDER),
        help=f"Comma-separated attack_type block order (default: {','.join(DEFAULT_BLOCK_ORDER)})",
    )
    return p.parse_args()


def build_sequence(df, block_order):
    benign = df[df["attack_type"] == "benign"].sort_values("ts").reset_index(drop=True)
    n_segments = len(block_order) + 1
    benign_segments = [
        benign.iloc[chunk] for chunk in
        [range(*bounds) for bounds in
         zip(
             [len(benign) * i // n_segments for i in range(n_segments)],
             [len(benign) * i // n_segments for i in range(1, n_segments + 1)],
         )]
    ]

    attack_blocks = {}
    for atype in block_order:
        block = df[df["attack_type"] == atype].sort_values("ts").reset_index(drop=True)
        if block.empty:
            raise ValueError(f"No flows found for attack_type={atype!r} in {LABELED_TEST_PATH}")
        attack_blocks[atype] = block

    pieces = []
    segment_id = 0
    for i, atype in enumerate(block_order):
        seg = benign_segments[i].copy()
        seg["segment_label"] = "benign"
        seg["segment_id"] = segment_id
        pieces.append(seg)
        segment_id += 1

        block = attack_blocks[atype].copy()
        block["segment_label"] = atype
        block["segment_id"] = segment_id
        pieces.append(block)
        segment_id += 1

    last_seg = benign_segments[-1].copy()
    last_seg["segment_label"] = "benign"
    last_seg["segment_id"] = segment_id
    pieces.append(last_seg)

    sequence = pd.concat(pieces, ignore_index=True)
    sequence.insert(0, "position", range(len(sequence)))
    return sequence[["position", "segment_id", "segment_label", "row_index", "window_id", "is_attack", "ts"]]


def main():
    args = parse_args()
    block_order = [t.strip() for t in args.order.split(",") if t.strip()]
    print(f"Block order: {block_order}")

    print(f"Loading {LABELED_TEST_PATH} (read-only)...")
    df = pd.read_csv(LABELED_TEST_PATH)

    sequence = build_sequence(df, block_order)

    print(f"\nBuilt sequence: {len(sequence)} flows ({int((sequence['is_attack'] == 0).sum())} benign, "
          f"{int((sequence['is_attack'] == 1).sum())} attack)")
    print("\nSegment layout:")
    layout = sequence.groupby(["segment_id", "segment_label"], sort=False).size().reset_index(name="n")
    for _, r in layout.iterrows():
        print(f"  segment_id={r['segment_id']:>2d}  {r['segment_label']:<14s}  n={r['n']}")

    sequence.to_csv(OUT_SEQUENCE_PATH, index=False)
    print(f"\nWrote {OUT_SEQUENCE_PATH}")

    config = {
        "block_order": block_order,
        "n_segments": int(sequence["segment_id"].nunique()),
        "n_flows": len(sequence),
        "source": os.path.relpath(LABELED_TEST_PATH, PROJECT_ROOT),
    }
    with open(OUT_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
    print(f"Wrote {OUT_CONFIG_PATH}")


if __name__ == "__main__":
    main()
