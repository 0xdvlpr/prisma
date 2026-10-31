# Prisma Daily

The top stories from every country in the world, every day, plus a three-minute Prisma Brief.

- `site/index.html` is the coming-soon landing page. `site/app/` is the app, with today's edition in `site/app/edition.json`.
- To launch, replace `site/index.html` with the app (move `site/app/*` up one level) and change the two `site/app/edition.json` paths in the workflow back to `site/edition.json`.
- `pfp/` is the news pipeline. It collects from GDELT, Google News, publisher RSS feeds and `feeds.yaml`, ranks stories by how many independent outlets carry them, and never leaves a country blank (it widens the search, then carries over yesterday's stories).
- `.github/workflows/daily.yml` runs the pipeline every morning, saves the edition and publishes the site to GitHub Pages.

## Run it by hand

Actions tab → **Prisma Daily** → **Run workflow**. A full run takes 30 to 90 minutes.

## Run the pipeline locally

```bash
pip install -e ".[gnews]"
pfp -v run --countries AU,NZ,FJ --export --out site/app/edition.json
python -m http.server -d site 8000   # then open http://localhost:8000
```

## Add or fix a country's sources

Edit `feeds.yaml`: add RSS feeds under the country's ISO code. They're used alongside the automatic sources.

## AI features

Ask Prisma, Prisma Daily summaries, story context and translations need a Claude API key behind a small server. They show "coming soon" on the public site until that's connected.

## Notes

Prisma links to publishers and shows headlines only, never full articles. Pipeline: MIT licence. Publisher catalogue from newscatcher (MIT). Event data from the GDELT Project.
