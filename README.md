# OSC-output-parser
Python middleware that listens for a stream of OSC messages that contain a list of numeric values (such as Wekinator's `'/wek/outputs'`) and re-emits each value as its own OSC message (e.g. `'/parsed/output-1' 0.1).
