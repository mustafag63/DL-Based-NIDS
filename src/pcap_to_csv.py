#!/usr/bin/env python3
"""
cicflowmeter offline PCAP -> CSV workaround.

Root cause: AsyncSniffer._run() (scapy 2.5+) ends with
    self.results = PacketList(lst, "Sniffed")
and NEVER calls session.toPacketList(). FlowSession.toPacketList() is therefore
never triggered, so garbage_collect(None) — the final flush — never runs and all
flows still in self.flows are silently discarded.

Fix: instantiate FlowSession directly, feed packets via PcapReader, call
toPacketList() ourselves at the end to trigger the flush.

ACTIVE/IDLE THRESHOLD (--active-timeout, default 5.0 s)
------------------------------------------------------
CRITICAL: Python cicflowmeter 0.2.0 ships ACTIVE_TIMEOUT = 0.005 s = 5 ms, while
the original Java CICFlowMeter that produced CICIDS-2017 uses 5 s. That 1000x
mismatch silently invalidates any active/idle comparison against CICIDS (see
active_idle_threshold_mismatch.md). cicflowmeter exposes NO CLI/param for this;
flow.py reads `constants.ACTIVE_TIMEOUT` at runtime (`from . import constants`),
so we override the module constant before processing. Default here is 5.0 s to
MATCH CICIDS. Pass --active-timeout 0.005 to reproduce the old (buggy) 5 ms runs.

Usage:
    python3 pcap_to_csv.py browsing.pcap  browsing.csv                 # 5 s (default)
    python3 pcap_to_csv.py browsing.pcap  browsing.csv --active-timeout 0.005
    python3 pcap_to_csv.py searching.pcap searching.csv -v
"""

import argparse
import cicflowmeter.constants as _cfm_constants
from scapy.utils import PcapReader
from scapy.layers.l2 import Ether
from cicflowmeter.flow_session import FlowSession


def pcap_to_csv(pcap_path: str, csv_path: str, verbose: bool = False,
                active_timeout: float = 5.0) -> None:
    # Match CICIDS's Java CICFlowMeter activity threshold (5 s). flow.py reads
    # constants.ACTIVE_TIMEOUT dynamically, so setting it here takes effect.
    _cfm_constants.ACTIVE_TIMEOUT = active_timeout

    # Class-level attributes read by FlowSession.__init__
    FlowSession.output_mode = "csv"
    FlowSession.output = csv_path
    FlowSession.fields = None
    FlowSession.verbose = verbose

    session = FlowSession()

    print(f"Reading {pcap_path}  →  {csv_path}  "
          f"(ACTIVE_TIMEOUT={active_timeout}s)")
    count = 0
    with PcapReader(pcap_path) as reader:
        for pkt in reader:
            session.on_packet_received(pkt)
            count += 1
            if verbose and count % 500 == 0:
                print(f"  {count} packets processed, {len(session.flows)} open flows")

    print(f"  {count} packets total — flushing {len(session.flows)} open flow(s)...")
    # This is the flush that AsyncSniffer skips — writes all remaining flows.
    #
    # NOTE: we call garbage_collect() directly instead of session.toPacketList().
    # cicflowmeter's toPacketList() does the flush (garbage_collect) but then ends
    # with `return super().toPacketList()`, and scapy >= 2.7 removed
    # DefaultSession.toPacketList — so that wrapper raises AttributeError AFTER the
    # CSV is already written, killing the whole capture loop. garbage_collect(None)
    # is the actual flush; deleting output_writer closes the CSV file (its __del__).
    session.garbage_collect(None)
    del session.output_writer
    print("Done.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Offline PCAP -> CICFlowMeter CSV.")
    ap.add_argument("pcap", help="input PCAP")
    ap.add_argument("csv", help="output CSV")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--active-timeout", type=float, default=5.0,
                    help="active/idle threshold in SECONDS (default 5.0 = CICIDS/"
                         "Java CICFlowMeter; use 0.005 for the old 5 ms behaviour)")
    args = ap.parse_args()
    pcap_to_csv(args.pcap, args.csv, verbose=args.verbose,
                active_timeout=args.active_timeout)
