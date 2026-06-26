# Contributing to hibrid

Thanks for helping make **hibrid** better. There are three ways to contribute, from easiest
to most technical.

## 1. Add your machine's benchmark 🖥️ (most valuable, and the easiest)

hibrid routes better when it knows the *real* speed of each machine. Share yours:

```bash
hibrid serve                  # starts up and benchmarks your hardware
curl localhost:8095/v1/node   # copy the JSON it prints
```

Open an issue with the **"Add my machine benchmark"** template and paste that JSON. It contains
no personal data — only hardware, models and tokens/sec. Your data point improves the routing
priors for everyone with similar hardware. This is the heart of the project.

## 2. Publish an execution profile (routing policy) 🔀

Tuned a profile for your case (say, `loop_refine` for a 16GB Mac, or a coding profile for an
RTX 4090)? Share it. See [`docs/EXECUTION_PROFILES.md`](docs/EXECUTION_PROFILES.md). A PR that
adds a well-documented profile is welcome.

## 3. Code 🛠️

```bash
git clone https://github.com/vfalbor/hibrid && cd hibrid
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 tests/test_router.py      # decision engine — should print 10/10 OK
python3 tests/test_dialects.py    # API dialect translation — 4/4 OK
```

- Keep the **tests green** and add tests for new behaviour (the decision engine is tested
  without network access).
- Commit style: `feat(scope): …`, `fix(scope): …`, `docs: …`.
- Open the PR against `main`. CI runs the tests automatically.

Look for issues labelled **`good first issue`** to get started — especially "add your machine's
benchmark."

## Code of conduct

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md). Be kind.
