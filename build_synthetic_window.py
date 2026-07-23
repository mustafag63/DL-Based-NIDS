#!/usr/bin/env python3
"""
build_synthetic_window.py

Builds two resampled conn.log windows (actual_attack_pct ~= 15% and 20%) to
stand in for the two windows lost to the 2026-07-22 16:00-18:00 Pi/Zeek
capture outage (conn.log for that span is effectively empty).

No feature value is invented anywhere. Every output row is byte-for-byte
copied from an existing, already-captured conn.log, pooled across all of the
known-healthy windows (window_01_0pct, 02_3pct, 03_5pct, 04_7pct, 05_12pct,
07_17pct, 08_22pct - window_06_15pct is deliberately excluded from the source
pool since it's the direct analogue of one of the windows being rebuilt):
  - benign rows  <- id.orig_h != attacker IP, from all of the above
  - attack rows  <- id.orig_h == attacker IP,  from all of the above
Only two things are chosen: which real rows get grouped into a window, and
(if the pool is too small) how many times a given real row is drawn. Both are
a fixed-seed random draw (random.seed(42)), not a synthetic generator.

Leakage prevention: the 15% and 20% output windows draw from a single shared
allocation pass per pool (benign, attack) so the same real row is never
placed into both output windows. If the combined need (both windows) fits
within the pool, sampling is WITHOUT replacement (each real row used at most
once, disjoint between the two windows). Only if the pool is still too small
for that does it fall back to WITH replacement (random.choices) - in which
case a duplicated row gets its `uid` field suffixed ("_dupN") so downstream
tooling keyed off uid uniqueness doesn't silently collapse repeats; no other
field is touched.
"""
import argparse
import json
import random
import statistics
import time
from pathlib import Path

BASE = Path("/Users/mustafa/Desktop/NIDS/data/ids-dataset-raw-backup")

# Known-healthy source windows to pool from. window_06_15pct is excluded on
# purpose (it's the real capture being stood in for by one of these outputs).
HEALTHY_WINDOWS = [
    "window_01_0pct",
    "window_02_3pct",
    "window_03_5pct",
    "window_04_7pct",
    "window_05_12pct",
    "window_07_17pct",
    "window_08_22pct",
]

ATTACKER_IP = "192.168.10.2"
SEED = 42

# Fallback default window size if no sibling window_0*_*pct dirs can be found
# to compute a live median from (see default_target_n()). This value is the
# median n_total actually observed across window_02_3pct..window_08_22pct
# on 2026-07-22 (4127/4257/4800/4967/5749/6151/6544 -> median 4967).
FALLBACK_TARGET_N = 4967


def parse_conn_log(path: Path):
    """Returns (header_lines, field_names, data_lines) for a Zeek conn.log.
    data_lines are raw (un-split) strings, newline stripped."""
    header_lines = []
    field_names = None
    data_lines = []
    with open(path, "r") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("#"):
                header_lines.append(line)
                if line.startswith("#fields"):
                    field_names = line.split("\t")[1:]
                continue
            if line:
                data_lines.append(line)
    if field_names is None:
        raise ValueError(f"{path}: no #fields header line found")
    return header_lines, field_names, data_lines


def col_index(field_names, name):
    return field_names.index(name)


def load_pools(paths, attacker_ip: str):
    """Reads every conn.log in paths once, splitting each row into the
    benign or attack pool by id.orig_h. Returns:
      header_lines, field_names,
      benign_pool:  [(line, source_window_label), ...],
      attack_pool:  [(line, source_window_label), ...]
    """
    header_lines = None
    field_names = None
    benign_pool = []
    attack_pool = []
    for path in paths:
        h, fnames, data_lines = parse_conn_log(path)
        if header_lines is None:
            header_lines, field_names = h, fnames
        elif fnames != field_names:
            raise SystemExit(
                f"HATA: {path} #fields semasi digerlerinden farkli, "
                "guvenli birlestirme yapilamaz."
            )
        orig_h_idx = col_index(fnames, "id.orig_h")
        label = path.parent.parent.name  # .../<window_label>/zeek/conn.log
        for line in data_lines:
            if line.split("\t")[orig_h_idx] == attacker_ip:
                attack_pool.append((line, label))
            else:
                benign_pool.append((line, label))
    return header_lines, field_names, benign_pool, attack_pool


def default_target_n(base: Path) -> int:
    """Median row count across sibling window_0*_*pct dirs (excluding the
    0pct baselines), falling back to FALLBACK_TARGET_N if none are found."""
    sizes = []
    for d in sorted(base.glob("window_*pct")):
        if "_0pct" in d.name:
            continue
        f = d / "zeek" / "conn.log"
        if f.is_file():
            with open(f) as fh:
                n = sum(1 for line in fh if line and not line.startswith("#"))
            if n > 0:
                sizes.append(n)
    if not sizes:
        return FALLBACK_TARGET_N
    return round(statistics.median(sizes))


def allocate_pool(pool_labeled, needed_by_pct: dict, rng: random.Random):
    """Splits pool_labeled across the pct windows in needed_by_pct (dict
    preserves insertion order). Prefers a disjoint, without-replacement
    allocation (each real row used at most once, never in both output
    windows); falls back to WITH replacement only if the combined need
    across all windows still exceeds the pool size.
    Returns (allocation: {pct: [(line,label), ...]}, used_replacement: bool).
    """
    total_needed = sum(needed_by_pct.values())
    pool_size = len(pool_labeled)
    allocation = {}
    if pool_size >= total_needed:
        shuffled = pool_labeled[:]
        rng.shuffle(shuffled)
        idx = 0
        for pct, n in needed_by_pct.items():
            allocation[pct] = shuffled[idx:idx + n]
            idx += n
        return allocation, False
    else:
        for pct, n in needed_by_pct.items():
            allocation[pct] = rng.choices(pool_labeled, k=n)
        return allocation, True


def dedup_uid(rows_labeled, field_names):
    """Assigns a unique uid to any row drawn more than once (only actually
    changes anything when sampling was done WITH replacement). Returns
    (deduped_lines, per_source_window_counts)."""
    uid_idx = col_index(field_names, "uid")
    seen_counts = {}
    label_counts = {}
    out_lines = []
    for line, label in rows_labeled:
        seen_counts[line] = seen_counts.get(line, 0) + 1
        occurrence = seen_counts[line]
        if occurrence == 1:
            out_lines.append(line)
        else:
            fields = line.split("\t")
            fields[uid_idx] = f"{fields[uid_idx]}_dup{occurrence - 1}"
            out_lines.append("\t".join(fields))
        label_counts[label] = label_counts.get(label, 0) + 1
    return out_lines, label_counts


def ts_of(line: str, ts_idx: int) -> float:
    return float(line.split("\t")[ts_idx])


def format_zeek_open(ts: float) -> str:
    return time.strftime("%Y-%m-%d-%H-%M-%S", time.gmtime(ts))


def build_header(template_header_lines, open_ts: float):
    out = []
    for line in template_header_lines:
        if line.startswith("#open"):
            out.append(f"#open\t{format_zeek_open(open_ts)}")
        else:
            out.append(line)
    return out


def write_window(target_pct: float, benign_rows_labeled, attack_rows_labeled,
                  field_names, header_lines, out_base: Path,
                  benign_replacement: bool, attack_replacement: bool,
                  healthy_windows, all_target_pcts,
                  window_label_override: str = None, extra_meta: dict = None):
    benign_lines, benign_source_counts = dedup_uid(benign_rows_labeled, field_names)
    attack_lines, attack_source_counts = dedup_uid(attack_rows_labeled, field_names)

    all_rows = attack_lines + benign_lines
    ts_idx = col_index(field_names, "ts")
    all_rows.sort(key=lambda line: ts_of(line, ts_idx))

    min_ts = ts_of(all_rows[0], ts_idx)
    out_header = build_header(header_lines, min_ts)

    window_label = window_label_override or f"window_resampled_{int(target_pct)}pct"
    out_dir = out_base / window_label / "zeek"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "conn.log"
    with open(out_path, "w") as f:
        for line in out_header:
            f.write(line + "\n")
        for line in all_rows:
            f.write(line + "\n")

    orig_h_idx = col_index(field_names, "id.orig_h")
    actual_attack_n = sum(
        1 for line in all_rows if line.split("\t")[orig_h_idx] == ATTACKER_IP
    )
    actual_attack_pct = 100.0 * actual_attack_n / len(all_rows)

    meta = {
        "window_label": window_label,
        "target_pct": target_pct,
        "actual_attack_pct": round(actual_attack_pct, 6),
        "n_total": len(all_rows),
        "n_attack": actual_attack_n,
        "n_benign": len(all_rows) - actual_attack_n,
        "status": "collected",
        "source": "resampled",
        "source_windows": {
            "pooled_from": healthy_windows,
            "benign_draw_counts": benign_source_counts,
            "attack_draw_counts": attack_source_counts,
        },
        "sampling": {
            "benign_with_replacement": benign_replacement,
            "attack_with_replacement": attack_replacement,
            "leakage_prevention": (
                f"{', '.join(f'{int(p) if p == int(p) else p}pct' for p in all_target_pcts)} "
                "ciktilari ayni havuzdan TEK bir allocation gecisinde (bu "
                "script invocation'i icinde) ortak/kesisen satir olmadan "
                "(disjoint) boluslendi; without-replacement mumkun oldugunda "
                "hicbir gercek flow bu invocation'daki window'lardan "
                "birden fazlasinda kullanilmadi. NOT: bu garanti sadece "
                "AYNI invocation'da birlikte uretilen pct'ler arasinda "
                "gecerli - farkli bir zamanda ayrica calistirilmis "
                "window_resampled_*pct ciktilariyla (ör. once uretilmis "
                "15pct/20pct) disjointness garanti edilmez, ayrica kontrol "
                "edilmelidir (bkz. attack_with_replacement)."
            ),
        },
        "generation_method": (
            "Pi/Zeek capture kesintisi (2026-07-22, 16:00-18:00) nedeniyle, "
            "gercek flow'larin kontrollu yeniden orneklenmesi (resampling), "
            "seed=42, real captured data. Hicbir feature degeri uydurulmadi; "
            "sadece hangi gercek Zeek flow'larinin bir arada gruplandigi ve "
            "(havuz yetersiz kaldiysa) kac kez cekildigi secildi. "
            f"Bu window icin benign havuzu {'yerine koyarak (with replacement)' if benign_replacement else 'yerine KOYMADAN (without replacement)'} "
            f"orneklendi; attack havuzu {'yerine koyarak (with replacement)' if attack_replacement else 'yerine KOYMADAN (without replacement)'} "
            "orneklendi. Tekrar kullanilan satirlarin (varsa) uid alani "
            "'_dupN' ile ayristirildi, baska hicbir alan degistirilmedi."
        ),
        "generated_with": "build_synthetic_window.py",
        "seed": SEED,
    }
    if extra_meta:
        meta.update(extra_meta)
    return out_path, meta


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--healthy-windows", nargs="+", default=HEALTHY_WINDOWS,
                     help="Source window folder names to pool benign/attack "
                          "flows from")
    ap.add_argument("--attacker-ip", default=ATTACKER_IP)
    ap.add_argument("--target-pcts", type=float, nargs="+", default=[15.0, 20.0])
    ap.add_argument("--n-total", type=int, default=None,
                     help="Total flows per output window; defaults to the "
                          "median n_total across existing window_0*_*pct dirs")
    ap.add_argument("--src-base", type=Path, default=BASE,
                     help="Directory containing the healthy source windows")
    ap.add_argument("--out-base", type=Path, default=BASE,
                     help="Directory to write window_resampled_*pct/ into")
    args = ap.parse_args()

    n_total = args.n_total or default_target_n(args.src_base)

    src_paths = [args.src_base / w / "zeek" / "conn.log" for w in args.healthy_windows]
    missing = [p for p in src_paths if not p.is_file()]
    if missing:
        raise SystemExit(f"HATA: kaynak conn.log bulunamadi: {missing}")

    header_lines, field_names, benign_pool, attack_pool = load_pools(
        src_paths, args.attacker_ip)

    print(f"n_total (hedef, her window icin) = {n_total}")
    print(f"benign_pool_size = {len(benign_pool)}")
    print(f"attack_pool_size = {len(attack_pool)}")
    print()

    needed_benign = {}
    needed_attack = {}
    for pct in args.target_pcts:
        attack_n = round(n_total * pct / 100.0)
        benign_n = n_total - attack_n
        needed_attack[pct] = attack_n
        needed_benign[pct] = benign_n

    rng = random.Random(SEED)
    benign_allocation, benign_replacement = allocate_pool(
        benign_pool, needed_benign, rng)
    attack_allocation, attack_replacement = allocate_pool(
        attack_pool, needed_attack, rng)

    summaries = []
    for pct in args.target_pcts:
        out_path, meta = write_window(
            target_pct=pct,
            benign_rows_labeled=benign_allocation[pct],
            attack_rows_labeled=attack_allocation[pct],
            field_names=field_names,
            header_lines=header_lines,
            out_base=args.out_base,
            benign_replacement=benign_replacement,
            attack_replacement=attack_replacement,
            all_target_pcts=args.target_pcts,
            healthy_windows=args.healthy_windows,
        )
        meta_path = out_path.parent.parent / "window_meta.json"
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
            f.write("\n")
        summaries.append(meta)
        print(f"-> {out_path}")
        print(f"   {meta_path}")
        print()

    print("=" * 60)
    print("OZET")
    print("=" * 60)
    print(f"benign_pool_size = {len(benign_pool)}")
    print(f"attack_pool_size = {len(attack_pool)}")
    print(f"benign_with_replacement = {'evet' if benign_replacement else 'hayir'}")
    print(f"attack_with_replacement = {'evet' if attack_replacement else 'hayir'}")
    print()
    for meta in summaries:
        print(f"{meta['window_label']}:")
        print(f"  target_pct        = {meta['target_pct']}")
        print(f"  actual_attack_pct = {meta['actual_attack_pct']:.4f}")
        print(f"  n_total           = {meta['n_total']}  "
              f"(attack={meta['n_attack']}, benign={meta['n_benign']})")
        print(f"  attack kaynak dagilimi = {meta['source_windows']['attack_draw_counts']}")
        print(f"  benign kaynak dagilimi = {meta['source_windows']['benign_draw_counts']}")
        print()


if __name__ == "__main__":
    main()
