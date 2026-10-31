# Prisma Daily

The top stories from every country in the world, every day, plus a three-minute Prisma Brief.

- `site/index.html` is the coming-soon landing page. `site/app/` is the app, with today's edition in `site/app/edition.json`.
- To launch, replace `site/index.html` with the app (move `site/app/*` up one level) and change the two `site/app/edition.json` paths in the workflow back to `site/edition.json`.
- `pfp/` is the news pipeline. It collects from GDELT, Google News, publisher RSS feeds and `feeds.yaml`, ranks stories by how many independent outlets carry them, and never leaves a country blank (it widens the search, then carries over yesterday's stories).
- `.github/workflows/daily.yml` runs the pipeline every morning, saves the edition and publishes the site to GitHub Pages. Run it with mode `deploy` to republish without collecting.
- `worker/` is the AI server and `.github/workflows/ai.yml` deploys it.

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

## AI features (Ask Prisma, Prisma Daily, story context, translations)

They run through `worker/`, a small Cloudflare Worker that keeps the Claude API key off the website. Until it's connected they show "coming soon".

1. **Cloudflare** (free): sign up, open **Workers & Pages** once to choose your workers.dev name, then **My Profile → API Tokens → Create Token → "Edit Cloudflare Workers"** template. Copy the token.
2. **Anthropic Console**: create an API key, and set a monthly spend limit under **Settings → Limits**. That limit is the hard cap on AI cost.
3. **This repo → Settings → Secrets and variables → Actions → New repository secret**: add `CLOUDFLARE_API_TOKEN` and `ANTHROPIC_API_KEY`.
4. **Actions → Prisma AI server → Run workflow.** It deploys the server, writes its address to `site/app/config.json` and republishes the site.

Guards in the server: only this site can use it, a fixed low-cost model (`MODEL` in `worker/wrangler.toml`), capped answer length, 40 requests per visitor per hour (`PER_HOUR`), and only Prisma's own story-search tool.

## Install as an app

`site/app` is an installable web app: `manifest.webmanifest`, icons, and `sw.js`, which keeps the latest edition so Prisma opens offline. Android/desktop Chrome offer "Install"; on iPhone use Share → Add to Home Screen. The You page shows the right instructions.

## Notes

Prisma links to publishers and shows headlines only, never full articles. Pipeline: MIT licence. Publisher catalogue from newscatcher (MIT). Event data from the GDELT Project.
