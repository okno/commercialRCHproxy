# Sanitized RCH framing corpus

These hexadecimal fixtures are public, synthetic derivatives of the observed
stream shapes. They contain no original merchant, network, tax, device,
timestamp, document-counter, product, or monetary values.

The replacements use obvious placeholders (`VOCE SINTETICA`, `XX`, `*_SYN_*`,
and synthetic digits). Request and response `DATA` values were regenerated;
no complete private directional stream is retained. Frame lengths, `AA`, class bytes, sequence bytes, standalone ACK
placement, legacy commercial split points (`168+106` request bytes and
`158+106` response bytes), and command layout are preserved; every XOR BCC was recomputed
after substitution. The display pair is exercised four times by the tests so
the sanitized corpus covers the same total of 77 frames and 39 ACK bytes as
the private evidence set.

The fixtures confirm parser behavior and structural regression coverage. They
do not document command semantics, fiscal outcome, printer-generated headers,
or legal status.

`rch_synthetic_partial_transaction.*` is a separately sanitized,
shape-equivalent regression for a private partial capture: it preserves only
the aggregate 235/202-byte sizes, 10/9 frame counts, 10 ACK ordering and the
missing final response shape. All printable literals, amounts and identifiers
were replaced and every BCC was recalculated. No complete private directional
stream or private-source digest is stored in Git.
