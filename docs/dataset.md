# Offline dataset — validation only

## What it is

A public, deployment-derived online banking fraud detection
inference-log dataset. It is a research / validation resource.
It is NOT the product's transaction source, and it is never
fed into the live classifier.

## Correct citation

Fatah, H.H. and Rashid, Z.N. (2026). *A Deployment-Derived Online
Banking Fraud Detection Inference-Log Dataset from a Live
Cloud-Based Deep Learning System* [Dataset]. Zenodo.
DOI: https://doi.org/10.5281/zenodo.20030064

Zenodo record URL: https://zenodo.org/records/20777880

Note the two identifiers, so they don't get mixed up again:
- **DOI: `10.5281/zenodo.20030064`** — the citable identifier.
- **Record `20777880`** — the Zenodo record URL identifier.

Associated publication: Fatah, H.H. and Rashid, Z.N.,
"A Production-Collected Online Banking Fraud Detection Dataset
from a Live Cloud-Based Deep Learning System",
*Data in Brief* (Elsevier), Manuscript No. DIB-D-26-00984,
under review (2026).

Licence: **Creative Commons Attribution 4.0 International
(CC BY 4.0)**. You must give appropriate credit, provide a link
to the licence, and indicate if changes were made.
Full text: https://creativecommons.org/licenses/by/4.0/

## Verified characteristics

Checked against the Zenodo page and its README on Nov 5, 2026:

- 56,962 transaction records, 98 fraud-labelled (0.172%).
- 38 columns: 30 inputs (`time_value`, V1–V28, `amount`)
  + 8 outputs/metadata (`transaction_id`, `is_fraud`,
  `fraud_probability`, `risk_level`, `confidence`,
  `recommendation`, `response_time_ms`, `timestamp`, `ip_address`).
- Amount in USD, $0.01–$25,691.16, median $49.88.
- `time_value`: seconds elapsed from the first transaction.
- V1–V28: PCA-transformed, original feature identities not
  disclosed. Do not interpret them as individual behaviours.
- Collected Jan 1–31, 2026 through a proof-of-concept public
  demonstration interface (`model-test.online`), NOT through a
  licensed banking institution. These are not real customer
  banking transactions.
- Zero missing values, zero duplicate `transaction_id`s, per
  the dataset README (re-verify from the CSV before reporting).

## Verification bias — read this before using `is_fraud`

Only BLOCK-flagged transactions (`fraud_probability > 0.43`)
were manually reviewed. ALLOW transactions were automatically
assigned `is_fraud = 0` without individual review. Any fraud
the original model missed is permanently recorded as 0.
The README also notes 12 confirmed false negatives
(`is_fraud = 1` despite an ALLOW recommendation).

Account for this whenever `is_fraud` is used as ground truth.

## Leakage rule

Do NOT use `fraud_probability`, `risk_level`, `confidence`,
or `recommendation` as inputs to our classifier or evaluation.
Those are outputs from the original CNN-LSTM model — the same
model that determined which records got manually reviewed.
Using them would leak the original model's decision into an
"independent" evaluation.

## What the dataset can and cannot validate

Can test:
- Amount vs `is_fraud` (e.g. amount > $500, amount > 3x median).
- Timing / velocity, in aggregate, from `timestamp` / `time_value`.
  There is no account or payee ID in the file, so per-account
  velocity like the live classifier uses cannot be reproduced.

Cannot test:
- PayPal Sandbox failure codes (INSTRUMENT_DECLINED, etc.).
- First-time payee.
- Anything about PayPal users — do not claim results generalise
  to PayPal.

If a signal cannot be validated, document it. Do not invent a proxy.

## Handling

- File: `fraud_tests_export_20260501_080333.csv` (21.2 MB).
- Do NOT commit the CSV to this repo. Download it locally into
  `data/raw/` (gitignored) and credit it as above.
- This project's MIT licence covers this project's code only.
  It does not relicence the dataset.
