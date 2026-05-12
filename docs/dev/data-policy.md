# Data Retention and Deletion Policy for `results/`

## What lives in `results/`

The `results/` directory is the default output root for all experiment runs. It contains:

- Per-run subdirectories named by run ID (e.g., `results/<run-id>/`)
- JSON checkpoint files (`checkpoint.json`, `batch_summary.json`)
- Per-tier and per-subtest output files (logs, judge outputs, metric snapshots)
- Analysis artefacts: figures (`*.png`), tables (`*.csv`), and statistical summaries

`results/` is listed in `.gitignore` and is **never committed to version control**.

## Retention Recommendation

| Storage tier | Recommended retention |
|--------------|-----------------------|
| Local workstation | Keep the last **90 days** of run data |
| Long-term archive (e.g., S3, NAS) | Archive runs associated with published results indefinitely |

Runs older than 90 days that are not linked to a publication or active comparison study
can be deleted without loss of reproducibility, provided the corresponding experiment
YAML configs (in `config/`) are retained.

## How to Purge a Run

To delete a single run:

```bash
rm -rf results/<run-id>
```

To purge all runs older than 90 days:

```bash
find results/ -mindepth 1 -maxdepth 1 -type d -mtime +90 -exec rm -rf {} +
```

Always verify the run ID before deleting. There is no recovery path once a run directory
is removed.

## Sensitive Content

Run directories may contain:

- Prompts sent to the Anthropic API (which may include repository source code)
- Agent outputs and judge reasoning traces
- API cost/token data

These should be treated as potentially sensitive. Do not share raw `results/` directories
publicly without reviewing their contents. See [SECURITY.md](../../SECURITY.md) for the
third-party API data-flow disclosure.
