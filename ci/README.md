# CI

`ci.yml` is the GitHub Actions workflow for hibrid (runs the decision-engine tests
on every push/PR across Python 3.10–3.12).

To enable it, move it into place:

```bash
mkdir -p .github/workflows && git mv ci/ci.yml .github/workflows/ci.yml
git commit -m "ci: enable GitHub Actions" && git push
```

Pushing files under `.github/workflows/` requires a token with the `workflow` scope
(or upload it via the GitHub web UI).
