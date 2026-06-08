# IGVF Catalog Documentation

Documentation for the [IGVF Catalog](https://catalog.igvf.org) data model, UI, REST API, and data provenance.

**Published site:** https://igvf-dacc.github.io/igvf-catalog-docs/

## Contents

- **Nodes & regions** — genes, variants, proteins, transcripts, diseases, ontologies, and UI guides
- **API Reference** — auto-generated from the development Catalog OpenAPI spec
- **Data Sources** — IGVF/ENCODE portal file metadata and field lineage (portal → adapter → API)

## API environment

Documentation currently targets the **development** API:

- Base URL: `https://catalog-api-dev.demo.igvf.org/api`
- Swagger UI: https://catalog-api-dev.demo.igvf.org/

Configuration: [`openapi/config.json`](openapi/config.json)

## Local development

Install the [Mintlify CLI](https://www.npmjs.com/package/mintlify):

```bash
npm install -g mintlify
```

Refresh generated content and preview:

```bash
python3 scripts/fetch_openapi.py
python3 scripts/build_source_index.py
python3 scripts/build_field_lineage.py
mintlify dev
```

Open http://localhost:3000

Configuration lives in [`docs.json`](docs.json) (Mintlify v4). Site-wide styling overrides are in [`custom.css`](custom.css).

## Build scripts

| Script | Purpose |
|--------|---------|
| [`scripts/fetch_openapi.py`](scripts/fetch_openapi.py) | Download OpenAPI from dev Swagger UI |
| [`scripts/build_source_index.py`](scripts/build_source_index.py) | Resolve IGVF/ENCODE file metadata + format specs |
| [`scripts/build_field_lineage.py`](scripts/build_field_lineage.py) | Adapter → field mapping docs |
| [`scripts/sample_responses.py`](scripts/sample_responses.py) | Store example API responses |
| [`scripts/catalog_per_example_audit.py`](scripts/catalog_per_example_audit.py) | Validate doc examples against live API |

## Deployment

Pushes to `main` trigger [`.github/workflows/deploy-pages.yml`](.github/workflows/deploy-pages.yml), which exports Mintlify HTML and deploys to GitHub Pages.

Repository Settings → Pages → Source: **GitHub Actions** (one-time setup).

## License

Documentation content follows the IGVF Catalog project licenses (CC BY 4.0 for data; MIT for software where applicable).
