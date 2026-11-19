# MAIT AI Literacy · classificatiepijplijn

Mistral Studio Workflow die scrapingresultaten van aanbieders van AI-geletterdheid
classificeert volgens het classificatiesysteem van de onderzoeksgroep (prompts 1 t/m 5).

## Wat de workflow doet

Per scrape-batch, tegen één versie van het frameworkbestand:

1. **Controle op het frameworkbestand** — mislukt de hele run direct wanneer een
   vereiste sectie (Purpose and scope, Unit of analysis, Dimensions, General
   scoring rules) ontbreekt.
2. **Extractie (prompt 1)** — één aanroep per gescrapte pagina, in parallelle
   golven; elke pagina levert nul, één of meerdere aanbodsrecords op.
3. **Citaatcontrole (deterministisch)** — elk aangehaalde citaat in elk record
   moet letterlijk (karakter voor karakter) in de gescrapte tekst voorkomen;
   afwijkingen worden gerapporteerd, nooit stil hersteld.
4. **Scoring (prompt 2)** — één aanroep per geëxtraheerd aanbod, als tweede
   lezer, met het extracierecord als vergelijkingsmaat.
5. **Batchsamenvatting** — tellingen van signalen per soort en label (exact de
   taxonomie uit prompts 1 en 2), review-set, citaatfouten; klaar voor de
   bundelstap (prompt 4, nog te schrijven).

De prompts zelf (`classification/prompts/`) zijn letterlijk overgenomen uit de
promptspecificaties; de workflow past ze toe zoals ze zijn en wijzigt ze niet.

## Buiten deze workflow

- **Inventarisatie (prompt 0) en scraping** — agenttaak met webtoegang; levert
  de batch met gescrapte pagina's voor deze pijplijn (zie `docs/prompt-0-inventarisatie.md`).
- **Frameworkcyclus (prompt 3)** — human-in-the-loop: theorie-invoer → concept
  framework → beslissingen → goedkeuring. De pijplijn verwerkt uitsluitend een
  frameworkbestand dat via die cyclus is opgeleverd; een `concept`-status wordt
  in de records als trial-run gemarkeerd (`trial_run: true`).
- **Bundeling (prompt 4)** en **theory scout (prompt 5)** — nog te schrijven;
  de samenvatting in de run-output is er al op voorbereid.

## Triggers

- **Handmatig** — via de Studio console ("Start Workflow") of vanuit een Vibe-chat.
- **Webhook** — zodra de scraper zijn resultaat automatisch kan aanleveren.
- **Volgens schema (wekelijks/maandelijks)** — zodra nieuwe scrapes op een vaste
  vindplaats landen; de planning wordt dan aan de deployment gekoppeld.

## Run-input (JSON)

```json
{
  "framework": "<volledige frameworkbestand, markdown, secties 1-6>",
  "framework_name": "framework-beta-v0.1.md",
  "batch_label": "Scrape 2026-11-19",
  "pages": [
    {
      "page_id": "T01#1",
      "provider": "Bureau Tromp",
      "page_title": "Masterclass AI-geletterdheid",
      "url": "https://example.org/masterclass-ai-geletterdheid",
      "fetched_at": "2026-11-19T10:00:00+01:00",
      "text": "<gescrapte paginatekst, ongewijzigd>"
    }
  ],
  "model": "mistral-medium-latest",
  "max_concurrent": 6,
  "temperature": 0.0
}
```

Alleen `framework` en `pages` zijn verplicht; de overige velden hebben defaults.
Houd batches onder ongeveer 150 pagina's per run (activiteitenlimiet van 2 MB
per aanroep); grotere batches opsplitsen.

## Run-output (JSON)

- `batch_label`, `framework_name`, `model`
- `summary`: tellingen (pagina's, aanbiedingen, scores, trial-runs, review-set),
  signalen per soort en label, citaatproblemen (steekproef)
- `pages`: per pagina de metadata, de extractierecords (prompt 1), de
  scorerecords (prompt 2), de citaatcontrole en eventuele foutstatussen
- `error`: alleen wanneer het frameworkbestand onvolledig is (de run doet dan niets)

Fouten blijven beperkt tot één pagina of één aanbod: een mislukte extractie of
score markeert alleen dat onderdeel; de rest van de batch loopt door.

## Lokaal ontwikkelen

```bash
pip install -r requirements.txt
export MISTRAL_API_KEY=<sleutel>
python worker.py
```

Daarna de workflow starten via de console, de API, of vanuit Vibe
(Vibe zet een scrape-Excel om naar batch-JSON en start de run).

## Bouwen en deployen

Beheerde deployment vanaf de `main`-branch:

```bash
curl -X POST https://api.mistral.ai/v1/workflows/deployments \
  -H "Authorization: Bearer $MISTRAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "mait-ai-literacy-worker",
    "spec": {
      "github_url": "https://github.com/maderu82/MAIT-AI-Literacy",
      "revision": "main",
      "backend_spec": {"type": "mistral_cloud", "dockerfile_path": "Dockerfile"}
    }
  }'
```

De worker heeft geen API-key nodig: het platform injecteert een
service-account-token in de container. Zorg dat de Mistral GitHub App
(https://github.com/apps/mistralai) toegang heeft tot deze repository.
