# Decision: reading receipts with Claude, off in the public demo

**Status:** accepted · 2026-10-13 · cella-api 0.10.0

## Context

Prices make the shopping list useful: an estimated total before leaving, the money spent per month, how the price of milk moved. Typing the price of 20 items after every trip is the step people skip, so Cella needs to read them from the receipt.

The public demo is open to anyone: recruiters, other developers, bots. Whatever runs there runs on my account.

## Options considered

| Option | Cost per receipt | Works with | Trade-offs |
|---|---|---|---|
| Type prices by hand | 0 | Anything | Nobody does it for 20 items |
| QR code of the Brazilian NFC-e | 0 | Electronic receipts from Brazil only | Exact data, but the tax office page changes per state, some have a captcha, and it does not exist in Canada or anywhere else |
| OCR library (Tesseract) + rules | 0 (server CPU) | Clean prints | Thermal paper, folds and abbreviations ("LEITE INT ITALAC 1L") break it; still needs rules to match lines to products |
| **Claude vision (Haiku)** | **≈ US$ 0.001** | **Any receipt, any language** | Costs money per call, needs an API key, the answer must be reviewed |

## Decision

Claude reads the photo **and** matches each line to a product of the household in the same request: the model receives the products bought on that trip as a numbered list and answers with a tool call (`record_receipt`), so the result is structured JSON, not free text. The hard part is the matching, not the OCR: "CAFE TORR 500G" → Coffee is easy for a language model and painful with rules.

In the public demo the feature is **off**. Visitors get a **sample receipt** generated from what they bought, with prices that moved a little since last week. The review screen and the confirmation are the same code path, so the demo shows the real flow at zero cost.

## Guardrails

- **Who can use it:** `RECEIPT_AI_ENABLED=true`, an `ANTHROPIC_API_KEY`, and the user's email in `RECEIPT_AI_EMAILS`. Demo households are always refused (`403`), even with an empty list. `GET /me` reports `features.receipt_ai`, so the app only shows the camera when it works.
- **Spend cap:** a monthly limit on the Anthropic Console is the last line of defense.
- **Image size:** the app shrinks the photo to 1568 px on the long side before sending (the largest size the model uses without downscaling); the API refuses anything over 5 MB.
- **Privacy:** the photo is never stored, only the confirmed prices. The prompt tells the model never to copy personal data (CPF, names, addresses, card numbers).
- **Prompt injection:** text on the receipt is transcribed as data. The model can only answer through the tool's schema, matches are limited to the numbered products of that trip, and the API ignores anything else (unknown numbers, a second line for the same product, prices out of range).
- **Mistakes:** nothing is saved without the review screen. Each line shows the previous price, so an odd value stands out.

## Cost

A receipt photo at 1568 px is about 1,500 image tokens; with the instructions and the answer, a request is ~2,000 input and ~1,000 output tokens. At Haiku 5.5 prices (US$ 0.10 input / US$ 0.50 output per million tokens) that is about **US$ 0.0007 per receipt**: ten trips a month cost less than one cent. Sonnet would be ~20 times more and is only worth it if Haiku misreads crumpled receipts.

## What would change it

- **Opening it to everyone:** a per-household daily limit (a `receipt_reads` table), `429` when it is reached, and billing or a free quota.
- **Brazil only:** the NFC-e QR code first (exact and free), Claude as the fallback for receipts without a readable code.
