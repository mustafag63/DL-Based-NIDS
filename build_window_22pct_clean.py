#!/usr/bin/env python3
"""
build_window_22pct_clean.py

Builds window_resampled_22pct_clean: a FULLY without-replacement resampled
window at ~22% attack, distinct from the earlier window_resampled_22pct
(which used with-replacement attack sampling because it was built alongside
25/28/30% in one build_synthetic_window.py call that exceeded the shared
attack pool - see phase3_vae/05_contamination_sweep/README.md's
"exploratory / with-replacement" section).

Budget check (this is the reason a *_clean variant needs its own script
instead of just re-running build_synthetic_window.py with a fresh process):
window_resampled_15pct and window_resampled_20pct were built together in a
single build_synthetic_window.py invocation and consumed 745 + 993 = 1738
attack flows without replacement, out of the 3279-flow attack pool pooled
from window_01,02,03,04,05,07,08 (window_06 excluded, same as always) -
leaving 1541 attack flows never used by any without-replacement window.
n_total=4967 at 22% needs round(4967*0.22)=1093 attack flows, which is
<= 1541, so a genuinely disjoint-from-15pct/20pct without-replacement draw
is feasible. This script explicitly excludes every uid already used by
window_resampled_15pct/20pct (both benign and attack sides) from the pool
before sampling, then asserts the result is disjoint.
"""
import json
import random
from pathlib import Path

from build_synthetic_window import (
    ATTACKER_IP, BASE, HEALTHY_WINDOWS, SEED,
    allocate_pool, col_index, load_pools, write_window,
)

TARGET_PCT = 22.0
N_TOTAL = 4967
ALREADY_USED_WINDOWS = ["window_resampled_15pct", "window_resampled_20pct"]
OUT_LABEL = "window_resampled_22pct_clean"


def used_uids(base: Path, window_labels, field_names_expected):
    """uid set of every row (benign+attack) already placed in the given
    resampled windows - both sides excluded so the new window can't reuse
    ANY real flow those windows already used, not just attack ones."""
    used = set()
    for label in window_labels:
        path = base / label / "zeek" / "conn.log"
        with open(path) as f:
            fields = None
            for line in f:
                line = line.rstrip("\n")
                if line.startswith("#fields"):
                    fields = line.split("\t")[1:]
                    assert fields == field_names_expected, (
                        f"{path}: #fields schema differs from source pool, "
                        "uid exclusion would be unsafe"
                    )
                    continue
                if line.startswith("#") or not line:
                    continue
                uid = line.split("\t")[col_index(fields, "uid")]
                assert "_dup" not in uid, (
                    f"{path}: unexpected '_dup' uid in a without-replacement "
                    f"window ({uid}) - this window may not be what it claims to be"
                )
                used.add(uid)
    return used


def main() -> None:
    src_paths = [BASE / w / "zeek" / "conn.log" for w in HEALTHY_WINDOWS]
    header_lines, field_names, benign_pool, attack_pool = load_pools(src_paths, ATTACKER_IP)
    print(f"Full pool (window_01,02,03,04,05,07,08): benign={len(benign_pool)} attack={len(attack_pool)}")

    excluded = used_uids(BASE, ALREADY_USED_WINDOWS, field_names)
    print(f"uids already used by {ALREADY_USED_WINDOWS}: {len(excluded)}")

    uid_idx = col_index(field_names, "uid")
    benign_pool_clean = [(line, label) for line, label in benign_pool if line.split("\t")[uid_idx] not in excluded]
    attack_pool_clean = [(line, label) for line, label in attack_pool if line.split("\t")[uid_idx] not in excluded]
    print(f"Pool after excluding 15pct/20pct's flows: benign={len(benign_pool_clean)} attack={len(attack_pool_clean)}")

    n_attack_removed_from_pool = len(attack_pool) - len(attack_pool_clean)
    n_benign_removed_from_pool = len(benign_pool) - len(benign_pool_clean)
    print(f"  ({n_attack_removed_from_pool} attack, {n_benign_removed_from_pool} benign rows excluded)")
    assert n_attack_removed_from_pool == 1738, (
        f"expected exactly 745+993=1738 attack flows already consumed by "
        f"15pct/20pct, got {n_attack_removed_from_pool} - investigate before continuing"
    )
    assert len(attack_pool_clean) == 1541, f"expected 1541 clean attack flows remaining, got {len(attack_pool_clean)}"

    attack_n = round(N_TOTAL * TARGET_PCT / 100.0)
    benign_n = N_TOTAL - attack_n
    print(f"\nTarget {TARGET_PCT}%: need attack_n={attack_n}, benign_n={benign_n}")
    assert attack_n <= len(attack_pool_clean), (
        f"clean attack pool too small ({len(attack_pool_clean)}) for the "
        f"without-replacement need ({attack_n})"
    )
    assert benign_n <= len(benign_pool_clean), (
        f"clean benign pool too small ({len(benign_pool_clean)}) for the "
        f"without-replacement need ({benign_n})"
    )

    rng = random.Random(SEED)
    benign_allocation, benign_replacement = allocate_pool(benign_pool_clean, {TARGET_PCT: benign_n}, rng)
    attack_allocation, attack_replacement = allocate_pool(attack_pool_clean, {TARGET_PCT: attack_n}, rng)
    assert not benign_replacement, "benign sampling unexpectedly fell back to with-replacement"
    assert not attack_replacement, "attack sampling unexpectedly fell back to with-replacement"

    # disjointness assertion: the drawn attack uids must not intersect the
    # uids already used by window_resampled_15pct/20pct
    drawn_attack_uids = {line.split("\t")[uid_idx] for line, _ in attack_allocation[TARGET_PCT]}
    drawn_benign_uids = {line.split("\t")[uid_idx] for line, _ in benign_allocation[TARGET_PCT]}
    assert not (drawn_attack_uids & excluded), "drawn attack uids overlap window_resampled_15pct/20pct"
    assert not (drawn_benign_uids & excluded), "drawn benign uids overlap window_resampled_15pct/20pct"
    print(f"\nDisjointness assertion PASSED: {len(drawn_attack_uids)} attack + "
          f"{len(drawn_benign_uids)} benign drawn uids share nothing with "
          f"{ALREADY_USED_WINDOWS}'s {len(excluded)} used uids.")

    out_path, meta = write_window(
        target_pct=TARGET_PCT,
        benign_rows_labeled=benign_allocation[TARGET_PCT],
        attack_rows_labeled=attack_allocation[TARGET_PCT],
        field_names=field_names,
        header_lines=header_lines,
        out_base=BASE,
        benign_replacement=benign_replacement,
        attack_replacement=attack_replacement,
        healthy_windows=HEALTHY_WINDOWS,
        all_target_pcts=[TARGET_PCT],
        window_label_override=OUT_LABEL,
    )

    # meta overrides/additions requested for this clean rebuild
    meta["generation_method_description"] = meta["generation_method"]
    meta["generation_method"] = "resampled_without_replacement"
    meta["disjoint_from"] = {
        "windows": ALREADY_USED_WINDOWS,
        "excluded_uid_count": len(excluded),
        "excluded_attack_count": n_attack_removed_from_pool,
        "excluded_benign_count": n_benign_removed_from_pool,
        "assertion": "PASSED - drawn uids (attack and benign) share zero elements "
                     "with uids already used by window_resampled_15pct/20pct",
    }
    meta["supersedes"] = (
        "window_resampled_22pct (the earlier with-replacement build alongside "
        "25/28/30pct) is NOT touched by this script; this is a separate, "
        "fully without-replacement window with a distinct label so the two "
        "never get confused downstream."
    )

    meta_path = out_path.parent.parent / "window_meta.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"\n-> {out_path}")
    print(f"   {meta_path}")
    print(f"\nactual_attack_pct = {meta['actual_attack_pct']:.4f}")
    print(f"n_total = {meta['n_total']} (attack={meta['n_attack']}, benign={meta['n_benign']})")
    print(f"benign_with_replacement = {benign_replacement}, attack_with_replacement = {attack_replacement}")


if __name__ == "__main__":
    main()
