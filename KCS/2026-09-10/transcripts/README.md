# Transcripts - KCS Board Meeting 09/10/2026

Two sources, kept separate so drafting can cross-check them.

- **`plaud/`** - the Plaud device recording. One continuous end-to-end
  transcript covering the whole meeting. Arrives after adjournment.
- **`incremental/`** - laptop chunks cut during the meeting, uploaded as
  they're made. Named `YYYY-MM-DD HH_MM_SS-transcript.txt`.

The incremental chunks are the timeline: they pin when things happened and
survive if the Plaud file is late or truncated. The Plaud transcript is the
completeness backstop and catches what the laptop missed between cuts.
Where they disagree on wording, prefer Plaud; where they disagree on
ordering, prefer the chunks.

## Dropping files in

Save anywhere in `~/Downloads` (or let the local recorder write to
`data/transcripts/`), then from the repo root:

```bash
./ingest-transcripts.sh KCS/2026-09-10
```

It copies new files into the right bucket, skips anything already ingested,
and is safe to run over and over mid-meeting. Force a bucket with
`--plaud` or `--incremental` if it guesses wrong.
