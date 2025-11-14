#!/usr/bin/env python3
"""
Middleware utility that collects individual OSC messages and emits a single
message containing all payloads, remembering the most recent value for every
tracked index. This reverses the splitting performed by osc_parser.py.

Example
-------
Incoming messages:
    /parsed/output-1 0.1
    /parsed/output-2 0.2
    /parsed/output-3 0.3

Outgoing message:
    /wek/outputs 0.1 0.2 0.3
"""

from __future__ import annotations

import argparse
import signal
import sys
from dataclasses import dataclass, field
from typing import Dict, Iterable, Sequence

from pythonosc import dispatcher
from pythonosc import osc_server
from pythonosc import udp_client


@dataclass(frozen=True)
class ReassemblerConfig:
    listen_host: str
    listen_port: int
    input_prefix: str
    target_host: str
    target_port: int
    output_address: str
    value_count: int
    verbose: bool


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect a set of OSC messages that share a prefix and emit them as a "
            "single OSC message (inverse of osc_parser.py)."
        )
    )
    parser.add_argument(
        "--listen-host",
        default="0.0.0.0",
        help="Host/IP to bind for incoming OSC messages (default: %(default)s).",
    )
    parser.add_argument(
        "--listen-port",
        type=int,
        default=12001,
        help="Port to bind for incoming OSC messages (default: %(default)s).",
    )
    parser.add_argument(
        "--input-prefix",
        default="/parsed/output-",
        help="Prefix of the OSC addresses that will be reassembled (default: %(default)s).",
    )
    parser.add_argument(
        "--target-host",
        default="127.0.0.1",
        help="Host/IP to forward the reassembled OSC messages to (default: %(default)s).",
    )
    parser.add_argument(
        "--target-port",
        type=int,
        default=12000,
        help="Port to forward the reassembled OSC messages to (default: %(default)s).",
    )
    parser.add_argument(
        "--output-address",
        default="/wek/outputs",
        help="OSC address used when emitting the aggregated message (default: %(default)s).",
    )
    parser.add_argument(
        "--value-count",
        type=int,
        default=5,
        help="Number of sequential inputs to collect before emitting (default: %(default)s).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-message logging.",
    )
    return parser


@dataclass
class MessageReassembler:
    config: ReassemblerConfig
    client: udp_client.SimpleUDPClient
    values: Dict[int, object] = field(default_factory=dict)

    def _log(self, level: str, message: str) -> None:
        if self.config.verbose:
            print(f"[{level}] {message}")

    def _parse_index(self, address: str) -> int | None:
        if not address.startswith(self.config.input_prefix):
            return None

        suffix = address[len(self.config.input_prefix) :]
        try:
            value = int(suffix)
        except ValueError:
            self._log("warn", f"Address '{address}' does not end with an integer index.")
            return None

        return value

    def _emit_current(self) -> None:
        ordered_values = [self.values[idx] for idx in range(1, self.config.value_count + 1)]
        self.client.send_message(self.config.output_address, ordered_values)
        self._log(
            "info",
            f"{self.config.input_prefix}[1..{self.config.value_count}] (last values) -> "
            f"{self.config.output_address} {ordered_values}",
        )

    def handle_message(self, address: str, *payload: Sequence[object]) -> None:
        if not payload:
            self._log("warn", f"Received {address} with no payload; skipping.")
            return

        if len(payload) > 1:
            self._log(
                "warn",
                f"{address} contained multiple values; only the first will be used.",
            )

        index = self._parse_index(address)
        if index is None:
            return

        if not 1 <= index <= self.config.value_count:
            self._log(
                "warn",
                f"Index {index} is outside the configured 1..{self.config.value_count} range.",
            )
            return

        self.values[index] = payload[0]

        if len(self.values) < self.config.value_count:
            missing = [idx for idx in range(1, self.config.value_count + 1) if idx not in self.values]
            self._log(
                "debug",
                f"Waiting for indexes {missing} before emitting aggregated message.",
            )
            return

        self._emit_current()


def setup_server(config: ReassemblerConfig) -> osc_server.ThreadingOSCUDPServer:
    osc_client = udp_client.SimpleUDPClient(config.target_host, config.target_port)
    reassembler = MessageReassembler(config, osc_client)

    disp = dispatcher.Dispatcher()
    disp.map(f"{config.input_prefix}*", reassembler.handle_message)

    server = osc_server.ThreadingOSCUDPServer((config.listen_host, config.listen_port), disp)
    print(
        f"[ready] Listening on {config.listen_host}:{config.listen_port} for "
        f"'{config.input_prefix}*' and forwarding complete sets to "
        f"{config.target_host}:{config.target_port} with address '{config.output_address}'"
    )
    return server


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.value_count < 1:
        print("[error] --value-count must be greater than 0.", file=sys.stderr)
        return 1

    config = ReassemblerConfig(
        listen_host=args.listen_host,
        listen_port=args.listen_port,
        input_prefix=args.input_prefix,
        target_host=args.target_host,
        target_port=args.target_port,
        output_address=args.output_address,
        value_count=args.value_count,
        verbose=not args.quiet,
    )

    server = setup_server(config)

    def _shutdown(signum, _frame):
        print(f"\n[info] Caught signal {signum}; shutting down.")
        server.server_close()
        sys.exit(0)

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _shutdown)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("[done] Server stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
