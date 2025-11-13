#!/usr/bin/env python3
"""
Middleware utility that splits sequential OSC messages into separate outputs.

Example
-------
Incoming message:
    /wek/outputs 0.1 0.2 0.3

Outgoing messages:
    /parsed/output-1 0.1
    /parsed/output-2 0.2
    /parsed/output-3 0.3
"""

from __future__ import annotations

import argparse
import signal
import sys
from dataclasses import dataclass
from typing import Iterable, Sequence

from pythonosc import dispatcher
from pythonosc import osc_server
from pythonosc import udp_client


@dataclass(frozen=True)
class ParserConfig:
    listen_host: str
    listen_port: int
    listen_address: str
    target_host: str
    target_port: int
    output_prefix: str
    verbose: bool


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert sequential OSC payloads into multiple OSC messages. "
            "Intended for bridging Wekinator '/wek/outputs' messages to "
            "downstream environments that expect individual values."
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
        default=12000,
        help="Port to bind for incoming OSC messages (default: %(default)s).",
    )
    parser.add_argument(
        "--listen-address",
        default="/wek/outputs",
        help="OSC address expected from the producer (default: %(default)s).",
    )
    parser.add_argument(
        "--target-host",
        default="127.0.0.1",
        help="Host/IP to forward the split OSC messages to (default: %(default)s).",
    )
    parser.add_argument(
        "--target-port",
        type=int,
        default=12001,
        help="Port to forward the split OSC messages to (default: %(default)s).",
    )
    parser.add_argument(
        "--output-prefix",
        default="/parsed/output-",
        help=(
            "Prefix used when emitting split messages. "
            "The index of the value (starting at 1) will be appended (default: %(default)s)."
        ),
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-message logging.",
    )
    return parser


def split_and_forward(
    client: udp_client.SimpleUDPClient,
    output_prefix: str,
    verbose: bool,
    address: str,
    *values: Sequence[object],
) -> None:
    if not values:
        if verbose:
            print(f"[warn] Received {address} with no payload; skipping.", file=sys.stderr)
        return

    for idx, value in enumerate(values, start=1):
        target_address = f"{output_prefix}{idx}"
        client.send_message(target_address, value)
        if verbose:
            print(f"[info] {address} -> {target_address} {value}")


def setup_server(config: ParserConfig) -> osc_server.ThreadingOSCUDPServer:
    osc_client = udp_client.SimpleUDPClient(config.target_host, config.target_port)
    disp = dispatcher.Dispatcher()
    disp.map(
        config.listen_address,
        lambda addr, *args: split_and_forward(
            osc_client, config.output_prefix, config.verbose, addr, *args
        ),
    )

    server = osc_server.ThreadingOSCUDPServer((config.listen_host, config.listen_port), disp)
    print(
        f"[ready] Listening on {config.listen_host}:{config.listen_port} for "
        f"{config.listen_address} and forwarding to "
        f"{config.target_host}:{config.target_port} with prefix '{config.output_prefix}'"
    )
    return server


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    config = ParserConfig(
        listen_host=args.listen_host,
        listen_port=args.listen_port,
        listen_address=args.listen_address,
        target_host=args.target_host,
        target_port=args.target_port,
        output_prefix=args.output_prefix,
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
