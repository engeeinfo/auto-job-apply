# Architecture

```text
CLI/runner
    ↓
naukri_bot coordinator
├── Settings ──> local JSON configuration
├── ResumeParser ──> local resume files/cache
├── AI engine ──> provider APIs
├── ApplyLogger ──> local application log
└── Playwright browser ──> Naukri UI
```

The coordinator owns workflow sequencing. Provider and browser integrations
should remain behind their current modules so unit tests can exercise policy
and persistence without network access. Runtime data belongs under ignored
`data/` paths and must not be committed.
