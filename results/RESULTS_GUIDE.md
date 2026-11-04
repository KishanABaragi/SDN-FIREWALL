# Fresh test results

Use `test_results_template.csv` for measurements from your own final run. Do not overwrite historical screenshots or historical CSV data.

For each phase, keep the command, full terminal output, time of test, and whether the controller timer had expired. Repeat each phase three times where possible.

Definitions:
- `controller_rule_submission_ms`: time taken by the controller function to queue OpenFlow rule messages.
- `end_to_end_block_detection_ms`: elapsed time from issuing the block request to the first consistently failed probe. This requires an external timestamp/probe method and is not the same as rule-submission duration.
- `packet_loss_percent`: `(sent - received) / sent * 100`.
- Keep failed connection attempts distinct from packet loss; TCP connect failures are not ICMP ping packet-loss measurements.
