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
def plot_peak_fit(result, axes=None):
    return plot_fit(result.curves["x"], result.curves["y"],
                    result.curves["y_fit"], result.curves["residual"],
                    xlabel=result.diagnostics.get("x_label", ""),
                    title=f"{result.sample_id} — R² = {result.values['fit_r2']:.4f}")
```

The payoff is the same: a user with their own `x, y, y_fit` from somewhere else
entirely gets your house style for free, and a user who wants to add a vertical
line to your figure gets an `Axes` back rather than a picture.

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
