# The kernel/adapter rule

*A design rule for scientific-software packages. Copy this file into any
project or hand it to any coding assistant as-is.*

---

## The rule

**Every operation is written twice: once as a kernel, once as an adapter.**

A **kernel** does the work on plain data.
An **adapter** finds the data, calls the kernel, and files the answer away.

They live in the same module, next to each other, and the adapter is a thin
call onto the kernel — never a copy of it.

```python
# KERNEL — the science. Arrays in, result out.
def fit_peaks(x, y, *, n_peaks=1, shape="gaussian"): ...

# ADAPTER — the plumbing. Finds data, calls the kernel, packages the answer.
def peak_fit(measurement, resolver, *, n_peaks=1, shape="gaussian", **io):
    x, y, info = load_curve(measurement, resolver, **io)
    fit = fit_peaks(x, y, n_peaks=n_peaks, shape=shape)
    return _to_analysis_result(fit, measurement, info)
```

The test of whether you have done this: **can a user call the kernel with two
numpy arrays they made up, in a fresh interpreter, with no project, no config
and no files on disk?** If not, it is not a kernel yet.

---

## Why

An integrated function is pleasant until the first time it is wrong. Then you
need to see the intermediate, change one number, and look again — and you
cannot, because the only entry point also wants a file path, a resolver and a
registry lookup. So you copy the body into a cell and edit it there, and now
the science exists in two places and one of them is not tested.

The kernel/adapter split is what keeps the convenient path convenient *without
making it the only path*. Three concrete payoffs:

- **Debugging.** `fit_peaks(x, y)` on the array in front of you, no IO.
- **Reuse.** Another package imports the kernel without inheriting your data
  model.
- **Testing.** The science is tested on synthetic arrays with a known answer;
  the adapter is tested on whether it finds the right file. Neither test is
  slow, and neither hides a failure of the other.

---

## What belongs in a kernel

| in | out |
|---|---|
| numpy arrays, scalars, strings, plain dicts | a result object or tuple of arrays |

**Must:**

- take **data**, not locators — `x, y`, not `path` or `measurement`;
- be importable on its own: `from pkg.analysis.peaks import fit_peaks`;
- be a pure function of its arguments — no reading files, no global config, no
  registry lookups, no logging to a session, no mutation of its inputs;
- **raise** on bad input (`ValueError`, `TypeError`) with a message naming the
  offending value. A kernel does not return a sentinel and does not swallow;
- return **everything it computed** — the fitted parameters *and* their
  uncertainties, the model curve, the residual, the goodness of fit, the
  settings it actually used. A kernel that returns only the headline number
  forces its caller to recompute the rest.

**Must not:**

- apply policy. `min_r2` — "is this fit good enough?" — is a decision about
  what to do with a number, not a step in computing it. The kernel reports
  R²; the adapter decides whether that passes.

---

## What belongs in an adapter

**Must:**

- do the IO: resolve paths, read frames, pick which frame;
- supply context the kernel cannot know: axis units, labels, the sample id;
- **catch what the kernel raises** and turn it into the framework's failure
  record, so one bad input cannot end a batch;
- carry provenance: what was read, which settings were used, how many points
  survived.

**Must not:**

- contain any arithmetic that a reader would want to check. If you find
  yourself computing something in the adapter, it belongs in the kernel.

---

## Naming

Make the pair obvious at a glance. Pick one convention and keep it:

| kernel | adapter |
|---|---|
| `fit_peaks(x, y, …)` | `peak_fit(measurement, resolver, …)` |
| `plot_fit(x, y, y_fit, …)` | `plot_peak_fit(result, …)` |
| `measure_curve(x, y, …)` | `curve_metrics(measurement, resolver, …)` |

The kernel's name says **what it does to the data**; the adapter's name is the
one the framework registers and the user usually types. State the pairing in
both docstrings, each pointing at the other.

---

## Plotting follows the same rule

Drawing has exactly the same problem, and it is the one people forget.

```python
# KERNEL — arrays in, Axes out.
def plot_fit(x, y, y_fit, residual=None, *, ax=None, xlabel="", title=""): ...

# ADAPTER — unwraps the result object, supplies the labels, calls the kernel.
def plot_peak_fit(result, ax=None):
    return plot_fit(result.curves["x"], result.curves["y"],
                    result.curves["y_fit"], result.curves["residual"], ax=ax,
                    xlabel=result.diagnostics.get("x_label", ""),
                    title=f"{result.sample_id} — R² = {result.values['fit_r2']:.4f}")
```

The payoff is the same: a user with their own `x, y, y_fit` from somewhere else
entirely gets your house style for free, and a user who wants to add a vertical
line to your figure gets an `Axes` back rather than a picture.

Two further rules make a plot reusable. Both are absolute.

### Rule P1 — draw where you are told, return what you drew on

**Every plotting function takes `ax=None`.**

- Given an `Axes`, it draws on that `Axes` and nowhere else — no new figure,
  no `plt.gca()`, no `plt.figure()`.
- Given nothing, it makes its own figure.
- It **returns what it drew on**: the `Axes`, or a tuple of them for a
  multi-panel plot. The figure is one attribute away (`ax.figure`).
- It never calls `plt.show()`, `plt.close()` or `savefig()` — showing and
  saving are the caller's decisions.

```python
def plot_thing(x, y, ax=None, **style):
    if ax is None:
        _, ax = plt.subplots()
    ax.plot(x, y, **style)
    return ax
```

That is what lets one function serve a quick look, a panel in someone else's
3×4 grid, and a figure that gets one more annotation before it goes in a
paper. A function that makes its own figure can only ever be the whole figure.

A multi-panel plot (a fit with its residual strip, two kinetics panels) takes
the panels it needs as a sequence — `ax=(top, bottom)` — and may also accept
one `Axes` and split it, so a fit placed in a grid keeps its residuals.

For an interactive library the same rule reads `fig=None` (with `row=`/`col=`
for a subplot grid): add the traces to the figure given, style only that
cell's axes, and return the figure. Never overwrite the caller's title, size
or legend.

### Rule P2 — never analyse and draw in one function

**A function either computes a result or draws one. Never both.**

```python
# NO — one call that fits and draws. You cannot have the fit without the
# picture, cannot redraw without refitting, cannot test either half alone.
result, axes = org.fit("S01", "waxs1d", show=True)

# YES — two calls. Each is useful without the other.
result = org.fit("S01", "waxs1d")      # the analysis: returns a result, draws nothing
org.plot_fit(result, ax=ax)            # the picture: takes the result, computes nothing
```

The same goes for a "plot" that segments the image it is about to draw, takes
a radial average on the way to plotting it, or runs an analysis because it was
handed a sample id instead of a result. Each of those hides a number nobody
can check, keep or reuse — split it: the analysis returns a result object, the
plot takes that object (or arrays).

Where the line sits: a plot may do **display arithmetic** — choose limits,
clip contrast to a percentile, take a log for display, stride forty curves out
of four hundred, mark the mean of the values it is drawing. It may not produce
**a number a reader would want to keep**: no fit, segmentation, integration,
reduction to a derived quantity, or other analysis. If you would put it in a
table, it belongs in an analysis function.

Composing the two belongs to the caller — the notebook cell, the GUI page —
not to a library function that "does both for convenience".

---

## Return a result object, not a tuple

Past about three values, a tuple stops being readable at the call site and
cannot be extended without breaking every caller. Use a small frozen
dataclass:

```python
@dataclass
class PeakFitResult:
    x: np.ndarray
    y: np.ndarray
    y_fit: np.ndarray
    residual: np.ndarray
    params: Dict[str, float]      # peak1_center, peak1_width, …
    errors: Dict[str, float]      # same keys, 1σ
    r2: float
    settings: Dict[str, Any]      # what was actually used
```

Give it an `unpack()` or `as_tuple()` if the two-value case is genuinely
common — but make the object the default, so adding a field later is additive.

---

## When *not* to split

Do not mechanically split something that has no science in it. A function that
only reads a file and returns an array is already a kernel-free adapter;
inventing a one-line kernel under it adds a name and no clarity.

The rule applies wherever there is **arithmetic worth checking**: a fit, a
metric, a transform, a segmentation, a drawing. Not to plumbing.

---

## Checklist for a reviewer

- [ ] Can the kernel be called with two made-up arrays and no files?
- [ ] Does the adapter contain any arithmetic?
- [ ] Does the kernel raise on bad input rather than returning a sentinel?
- [ ] Does the kernel return everything it computed, including uncertainties?
- [ ] Is a quality threshold applied in the adapter, not the kernel?
- [ ] Do both docstrings name their counterpart?
- [ ] Is there a kernel test using synthetic data with a known answer?
- [ ] Does every plotting function take `ax=None` (or `fig=None`), draw only
      there when given one, and return what it drew on?
- [ ] Is there any function that both computes a result and draws it? Split it.
- [ ] Does any plotting function call `plt.show()`, `savefig()` or create a
      figure when it was handed an `Axes`?
