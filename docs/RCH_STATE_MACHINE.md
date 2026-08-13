# RCH state machine

The maintained 0.3 inferred document/worker state model is documented in
[PARSER_STATE_MACHINE.md](PARSER_STATE_MACHINE.md).

Frame boundaries are capture evidence. Command meanings, open/close roles,
subtypes, and response association are reverse-engineered and remain explicitly
labelled. `complete` means an inferred request close was captured; it never
means fiscal success.
