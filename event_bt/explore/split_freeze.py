#!/usr/bin/env python
"""split_freeze.py -- Stage 0 of PROTOCOL.md: freeze and hash the datasets.

Creates (idempotent -- refuses to overwrite an existing freeze):
  data/discovery_smallcap.csv     small/mid-cap trades, ann_date < 2025-07-01
  data/liquid_historical.csv      liquid T-14 trades (CONTAMINATED-DESCRIPTIVE)
  lockbox/validation_smallcap.csv small-cap trades ann_date >= 2025-07-01 (SEALED)
  SHA256SUMS                      manifest the eval harness enforces

Mechanical only: no statistics are computed, nothing is printed about the
contents of the validation slice beyond its row count.
"""

import hashlib
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BT = os.path.dirname(HERE)
SPLIT_DATE = "2025-07-01"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    manifest = os.path.join(HERE, "SHA256SUMS")
    if os.path.exists(manifest):
        sys.exit("freeze already exists -- refusing to re-split (delete "
                 "SHA256SUMS manually only if you understand the cost)")
    os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
    os.makedirs(os.path.join(HERE, "lockbox"), exist_ok=True)

    sc = pd.read_csv(os.path.join(BT, "results", "T14", "trades.csv"),
                     parse_dates=["ann_date"])
    cut = pd.Timestamp(SPLIT_DATE)
    disc = sc[sc["ann_date"] < cut]
    val = sc[sc["ann_date"] >= cut]
    liq = pd.read_csv(os.path.join(BT, "results_liquid_full", "T14",
                                   "trades.csv"), parse_dates=["ann_date"])

    p1 = os.path.join(HERE, "data", "discovery_smallcap.csv")
    p2 = os.path.join(HERE, "data", "liquid_historical.csv")
    p3 = os.path.join(HERE, "lockbox", "validation_smallcap.csv")
    disc.to_csv(p1, index=False)
    liq.to_csv(p2, index=False)
    val.to_csv(p3, index=False)

    with open(manifest, "w") as f:
        for p in (p1, p2, p3):
            f.write("%s  %s\n" % (sha256(p), os.path.basename(p)))
    ehash = sha256(os.path.join(HERE, "eval_harness.py"))
    with open(os.path.join(HERE, "FREEZE.txt"), "w") as f:
        f.write("frozen 2026-08-31\nsplit_date %s\n"
                "discovery_smallcap n=%d\nvalidation_smallcap n=%d (SEALED)\n"
                "liquid_historical n=%d (CONTAMINATED-DESCRIPTIVE)\n"
                "eval_harness.py sha256=%s\n"
                % (SPLIT_DATE, len(disc), len(val), len(liq), ehash))
    with open(os.path.join(HERE, "lockbox", "DO_NOT_READ.md"), "w") as f:
        f.write("# SEALED\n\nvalidation_smallcap.csv is opened ONCE, at "
                "PROTOCOL Stage 4, gated by LOCKBOX_OPEN=1 and the explicit "
                "session line 'OPEN THE LOCKBOX'. Reading it earlier burns "
                "the only honest validation this dataset will ever have.\n")
    print("frozen: discovery n=%d | validation n=%d (sealed) | liquid n=%d "
          "(descriptive) | harness hash %s..." %
          (len(disc), len(val), len(liq), ehash[:16]))


if __name__ == "__main__":
    main()
