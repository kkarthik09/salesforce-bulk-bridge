# Salesforce Bulk Bridge

Bulk API 2.0 upsert reference with CSV validation, destination-bound checkpoints, bounded polling, conservative retries and ambiguous-outcome recovery. Python 3.12+, standard library only.

## Offline demo
```sh
python -m unittest -v
python bridge.py --checkpoint demo-checkpoint.json
```
Default transport is a deterministic fake. It does not contact Salesforce.

## Optional sandbox integration
Create an External ID field, assign minimal object/field permissions, and obtain a short-lived token through your approved OAuth flow. Set `SF_INSTANCE_URL` to the HTTPS My Domain origin and `SF_ACCESS_TOKEN` in your environment. Do not commit tokens.

```sh
python bridge.py --live --csv sample.csv --object Account \
  --external-id External_Id__c --api-version v66.0 \
  --checkpoint sandbox-checkpoint.json
```
`--live` writes records to the selected org. Use a disposable sandbox and choose an API version supported by it. OAuth acquisition and refresh are not implemented.

## Recovery contract
Create → upload → close with UploadComplete → poll → terminal state. A fingerprint binds the checkpoint to destination, API version, input and object/field config. Atomic replace protects JSON integrity. Create/upload phases are persisted before requests: an ambiguous outcome halts for reconciliation instead of blindly repeating a mutation. Lost close responses recover by reading job state. Poll timeouts resume without another upload.

## Boundaries
One process per checkpoint; no concurrent-writer lock or remote checkpoint service. CSV is in memory and not split. No result-file downloader, failed-row replay, OAuth refresh, or live-org verification. JobComplete can contain row failures: inspect `failed` and Salesforce's failed/unprocessed results before replaying. External-ID upsert does not make triggers exactly-once.

GET retries cover HTTP 429 and selected 5xx statuses, at most three attempts. Numeric Retry-After is capped at 60 seconds. Network errors surface to the caller. Mutations are not retried automatically. Redirects are refused to protect bearer credentials; HTTP errors omit tokens and response bodies.

## Validation
Fake-transport tests cover lifecycle, replay, changed data/destination, ambiguous creation, poll recovery, invalid CSV and origins. **No live Salesforce org testing has been performed.**

## References
- [Bulk API 2.0 ingest](https://developer.salesforce.com/docs/platform/api-asynch/guide/bulk-api-2-0-ingest.html)
- [Upsert walkthrough](https://developer.salesforce.com/docs/platform/api-asynch/guide/walkthrough-upsert.html)
- [Job states](https://developer.salesforce.com/docs/platform/api-asynch/guide/bulk-api-2-job-states.html)

Interview extensions: HTTP contract server, OAuth refresh coordination, failed-row classification, reconciliation CLI and multi-worker checkpoint storage.

New portfolio reference developed with AI assistance. No deployed-customer impact claimed.
