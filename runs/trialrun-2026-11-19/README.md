# Trial run 19-11-2026 · ailit-boodschap 0.1 (concept)

First real run of `ai-geletterdheid-classificatie` against the concept framework.

| | |
|---|---|
| Workflow | `ai-geletterdheid-classificatie` (deployment `mait-ai-literacy-worker`) |
| Execution | `13432667087855d3b151a578ec8c20caec502fb2d0925a57b3b34b864c9166f9` · COMPLETED in 132 s |
| Model | mistral-medium-latest · temperature 0.0 · max 6 pages tegelijk |
| Framework | ailit-boodschap 0.1, status concept → every record has `trial_run: true` |
| Input | 13 scraped pages (`batch-input.json`), from "Testresultaten scraping AI-geletterdheid.xlsx" (sheet Paginas), gescraped 16-11-2026 |

## Files

- `batch-input.json` — de 13 pagina's precies zoals aangeboden aan de workflow.
- `result.json` — machine-readable source of truth: `summary` + per pagina `extraction`, `score_records`, `quote_problems`.
- `../../docs/framework-ailit-boodschap-0.1.md` — het framework, exact de tekst die aan deze run is meegegeven.

## Uitkomst

- 17 aanbiedingen, 146 berichten (waarvan 27 in `rest`), 119 dimensiescores (78 gescoord, 39 niet vast te stellen, 0 niet te scoren).
- 134 signalen: 87 framework, 34 proces, 13 data.
- 33 citaatproblemen. Opvallend: een deel zijn de verzonnen voorbeeldcitaten uit het framework zelf (open punt 2) — die staan dus niet in de brontekst.
- Review voorgesteld door prompt 1: 5 aanbiedingen; door prompt 2: 16.
