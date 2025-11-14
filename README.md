## OSC parser

Python middleware that listens for a stream of OSC messages that contain a list
of numeric values (such as Wekinator's `'/wek/outputs 0.1 0.2 0.3 0.4 0.5'`) and re-emits each value as its own OSC message (e.g. `'/parsed/output-1' 0.1`).

### Requirements

- Python 3.10 or newer
- [`python-osc`](https://pypi.org/project/python-osc/) (install via `pip install -r requirements.txt`)

### Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip3 install -r requirements.txt
```

### Usage

```bash
python3 osc_parser.py \
  --listen-port 12000 \
  --target-port 12001 \
  --listen-address /wek/outputs \
  --output-prefix /parsed/output-
```

Listening defaults to `0.0.0.0:12000` and forwards to `127.0.0.1:12001`. Override the
host/port/address/prefix via the CLI flags if needed (use `python osc_parser.py -h`
to see the full list). Use `--quiet` to disable per-message logging.

Once running, send the script a message such as

```
/wek/outputs 0.1 0.2 0.3 0.4 0.5
```

and it will emit (to the configured target host/port) the messages

```
/parsed/output-1 0.1
/parsed/output-2 0.2
/parsed/output-3 0.3
/parsed/output-4 0.4
/parsed/output-5 0.5
```

### Reverse usage

Use `osc_reassembler.py` to perform the opposite transformation (take sequential
messages and re-emit a single payload):

```bash
python3 osc_reassembler.py \
  --listen-port 12001 \
  --target-port 12000 \
  --input-prefix /parsed/output- \
  --output-address /wek/outputs \
  --value-count 5
```

Once running, send the script individual messages such as

```
/parsed/output-1 0.1
/parsed/output-2 0.2
/parsed/output-3 0.3
/parsed/output-4 0.4
/parsed/output-5 0.5
```

and it will emit

```
/wek/outputs 0.1 0.2 0.3 0.4 0.5
```

The reassembler remembers the most recent value for each index. After it has
seen every index at least once, any subsequent message (even if it only updates a
single index) immediately triggers a new `/wek/outputs` message containing the
latest values.
