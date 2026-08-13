# Receipt and photograph correlation report

## Conclusion first

The supplied evidence does **not** permit a four-document byte correlation.
There are four photographs but exactly one partial directional capture job.
Only photo label 3.1 has a strong partial content correlation to that job.
Labels 1, 2, and 3.2 have no corresponding payload in the supplied dump and
remain `NON VERIFICABILE`.

Producing four reconstructed files from this one job would require copying
photo-only data or inventing three streams. The Parser deliberately does
neither.

## Privacy and method

This public report omits merchant/address/tax/device identifiers, private
endpoints, product names, monetary values, document numbers, exact transaction
timestamps, source hashes, and private generated filenames. Photo labels are
operator annotations only and are never treated as RCH commands, document
numbers, or `CODICE_DOC` values.

Correlation uses only:

1. directional RAW frame order and offsets;
2. captured literal item/reference/total fields;
3. candidate state transitions;
4. visual document type and field order from the photos;
5. explicit negative evidence where bytes are absent.

Photographs are ground truth for comparison, never Parser input.

## Evidence labels

| Label | Meaning |
|---|---|
| `VERIFIED_PHOTO` | Directly visible in the private photograph. |
| `VERIFIED_DUMP` | Directly present in the supplied bytes. |
| `INFERRED_HIGH` | Strong multi-field/order match, but command semantics are not official. |
| `NON VERIFICABILE` | No corresponding directional bytes were supplied. |

## Required correlation matrix

| Photo label | Visual type/subtype | Supplied RAW interval | Candidate open | Candidate close | Capture time | TXT output | PDF output | Comparison result | Residual difference/confidence |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `G / COMANDA` (`VERIFIED_PHOTO`) | none | none | none | none | not produced from missing bytes | not produced from missing bytes | `NON VERIFICABILE` | Visual classification is clear; no request/response frame can be associated. |
| 2 | `G / PRECONTO` (`VERIFIED_PHOTO`) | none | none | none | none | not produced from missing bytes | not produced from missing bytes | `NON VERIFICABILE` | The photograph shows the prior item state, but the dump contains no matching management body. |
| 3.1 | `C / DOCUMENTO COMMERCIALE` (`VERIFIED_PHOTO`) | request bytes 0-234, frames 1-10; response bytes 0-201 provide incomplete ordinal evidence | frame 1 control candidate followed by exact `=K` in frame 2 | absent; capture ends after total/payment-like frame 10 | private technical timestamp withheld; clocks differ by about two minutes | private local name intentionally omitted; one partial C reconstruction is supported | private local name intentionally omitted; proxy-render check remains separate | captured item/reference/total region `INFERRED_HIGH`; document completion not verified | Printed header, legal heading, tax/payment details, number/date/footer are not all in request RAW and must stay absent. |
| 3.2 | `G / COPIA CONFORME` (`VERIFIED_PHOTO` and declared sequence) | none after the commercial candidate | none | none | none | not produced from missing bytes | not produced from missing bytes | `NON VERIFICABILE` | No distinct management envelope/body exists, so copy relationship and content cannot be reconstructed from this dump. |

`Capture time` intentionally does not require equality with the printer/POS
clock printed on paper. The available values differ by roughly two minutes.
Without a trusted clock-synchronization record this is not evidence against a
content correlation and its cause remains unknown.

## Photo 1: management command

The photograph visually shows a management command/ticket with a table-like
reference, item lines, course/covers-like operator information, and no fiscal
commercial layout (`VERIFIED_PHOTO`). This supports the expected semantic
classification `G / COMANDA` for a future corresponding stream.

The supplied request contains no management `=o` envelope or matching
printable-line body for this paper. No frame interval, output time, or Parser
file can be assigned (`NON VERIFICABILE`). The photo must not be OCR'd into a
synthetic Parser job.

## Photo 2: management pre-account

The photograph visually shows a management pre-account with item lines, a
prior item-price state, total, reference, payment/tax-style regions, and a
management heading (`VERIFIED_PHOTO`).

The single supplied request has a commercial command shape and the later
updated item state. It does not contain a separate management printable body
matching this photo. The expected `G / PRECONTO` output cannot be generated
from the evidence (`NON VERIFICABILE`).

## Photo 3.1: partial commercial correlation

The 235-byte request contains:

- an inferred commercial start sequence;
- three item-like frames whose captured descriptions/values match the visible
  updated commercial lines in order;
- three free-text candidates including the table/reference-like literal;
- one total/payment-like frame whose captured value matches the visible total.

This multi-field, ordered match supports a strong **partial** correlation to
photo 3.1 (`INFERRED_HIGH`). It does not make the capture complete.

The stream lacks the inferred close/postlude and does not contain complete
paper regions generated/configured by the physical device. In particular, the
Parser cannot source the full merchant header, legal heading, VAT summary,
explicit payment method, printer-created date/document number, or fiscal/device
footer from the request RAW. Those photo-visible fields remain absent rather
than being invented.

The response has 10 ACK events but only 9 framed responses. ACK is not treated
as a close or success. The reconstructed candidate remains incomplete.

## Photo 3.2: conforming copy

The photograph and declared operational sequence identify a management
conforming copy after the commercial document (`VERIFIED_PHOTO` for visual
form; sequence supplied by operator). A conforming-copy Parser rule must keep
that document separate and type it `G`, not merge it into the preceding `C`.

However, no second management envelope/body is present after the commercial
candidate in the supplied RAW. The literal phrase is not present, and there is
no captured item/total/payment/tax signature on which to establish a same-stream
copy relationship. A 3.2 TXT/PDF would therefore be invented and is not
produced (`NON VERIFICABILE`).

## Price-state acceptance

The intended acceptance sequence contains:

1. command/pre-account with an earlier captured item state;
2. a price change in the management application;
3. a commercial document with the updated state;
4. a separate conforming copy of that updated commercial document.

The real supplied RAW contains only one state, corresponding to the updated
commercial candidate. It cannot prove that an earlier pre-account remains
unchanged or that a later conforming copy receives the correct values.

The implementation has sanitized synthetic state-isolation tests that create
fresh models for pre-account, commercial, and conforming-copy candidates and
assert no cross-document leakage. That is an implementation regression test,
not a substitute for the missing private captures.

## TXT/PDF comparison policy

For a captured candidate:

- TXT contains only human fields reconstructed from captured `DATA` plus an
  explicit Parser metadata header;
- PDF is generated from the same `DocumentModel` and is labelled as a proxy
  reconstruction;
- normalized PDF text must remain semantically consistent with TXT;
- fields visible only in a photograph are listed as residual differences, not
  filled from the photograph;
- private output names/paths are not published in this report.

Final physical-layout fidelity, fonts, thermal paper width, and printer-created
regions cannot be established from a sidecar PDF. A proxy PDF is never an
original or signed RCH fiscal artifact.

## Acceptance status

| Acceptance item | Status | Reason |
|---|---|---|
| Four distinct real captures | `NON VERIFICABILE` | only one partial job supplied |
| Photo 1 byte mapping | `NON VERIFICABILE` | payload absent |
| Photo 2 byte mapping | `NON VERIFICABILE` | payload absent |
| Photo 3.1 partial field mapping | `COMPLETATO` | ordered captured item/reference/total region correlates |
| Photo 3.1 complete lifecycle | `NON VERIFICABILE` | close/postlude missing |
| Photo 3.2 byte/copy mapping | `NON VERIFICABILE` | distinct management payload absent |
| Synthetic four-state isolation | `COMPLETATO E TESTATO` | final Linux suite passed 215 tests; independent-model fixture verifies no state leakage |
| Private TXT/PDF visual verification | `COMPLETATO E TESTATO` | protected TXT/PDF agree semantically; one-page render shows `STATO: INCOMPLETO` and no clipping |

## Required follow-up capture

Repeat the four operations in one authorized run while preserving complete
request/response RAW, timelines, manifests, connection/session IDs, and photo
labels. Ensure the Dumper remains active through delayed response/postlude
traffic. Keep all raw/photos private. Only then can this matrix be upgraded
from `NON VERIFICABILE` to captured byte intervals and private output validation.
