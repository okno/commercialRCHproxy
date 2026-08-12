# Sanitized RCH framing corpus

These hexadecimal fixtures are public, synthetic derivatives of the observed
stream shapes. They contain no original merchant, network, tax, device,
timestamp, document-counter, product, or monetary values.

The replacements use obvious placeholders (`VOCE SINTETICA`, `XX`, and zero
digits). Frame lengths, `AA`, class bytes, sequence bytes, standalone ACK
placement, legacy commercial split points (`168+106` request bytes and
`158+106` response bytes), and command layout are preserved; every XOR BCC was recomputed
after substitution. The display pair is exercised four times by the tests so
the sanitized corpus covers the same total of 77 frames and 39 ACK bytes as
the private evidence set.

The fixtures confirm parser behavior and structural regression coverage. They
do not document command semantics, fiscal outcome, printer-generated headers,
or legal status.
