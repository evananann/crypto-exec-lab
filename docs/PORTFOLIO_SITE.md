# Portfolio Pages publication

The site consists of an overview, the existing interactive exit-cost lab, and
synthetic maker/correlation examples. It contains no raw tapes or empirical study
outputs. The builder accepts an exact checksum-bound synthetic presentation
inventory and copies only allowlisted files. It does not install dependencies,
read archives, fit models or bypass scientific release gates.

```bash
python -S -m research.portfolio_site build --output data/raw/portfolio-site
python -m http.server 8000 --directory data/raw/portfolio-site
```

The [Pages workflow](../.github/workflows/portfolio-pages.yml) builds the preview
first and retains its artifact. Only then does it inspect/create the repository's
Pages configuration using the job token and deploy when that succeeds. Actions
are pinned to reviewed commit IDs. The Pages deployment URL comes from the actual
deployment; a successful preview build alone is not a published website.

If GitHub returns a permission/setup response, the job records the HTTP status,
leaves the preview available and skips deployment. A repository administrator
must open **Settings → Pages → Build and deployment → Source: GitHub Actions**,
then run `portfolio Pages demo` again. No token values are printed or committed.
Unexpected API/transport failures remain real failures.

The expected default URL is `https://evananann.github.io/crypto-exec-lab/`; it must
be checked after deployment before being advertised as a working demo. A custom
repository Pages configuration may produce another URL. Current publication
status is in the latest workflow deployment and the README's explicit status.
