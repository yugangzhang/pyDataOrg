# The analysis layer

> **Every analysis here is a kernel plus an adapter.** `fit_peaks(x, y, …)`
> does the arithmetic on arrays; `peak_fit(measurement, resolver, …)` finds the
> curve, calls it, and files the answer. The kernel is importable on its own
> and takes no files, no project and no registry — which is what makes a
> misbehaving fit debuggable. The rule is stated in full in
> [`kernel_adapter_rule.md`](kernel_adapter_rule.md); follow it for anything
> you add.
>
> | kernel | adapter |
> |---|---|
> | `fit_peaks(x, y, …)` | `peak_fit(measurement, resolver, …)` |
> | `measure_curve(x, y, …)` | `curve_metrics(measurement, resolver, …)` |
> | `size_from_image(image, …)`, `size_statistics(d)` | `particle_sizing(measurement, resolver, …)` |
> | `segment_particles(image, …)` | `segment_micrograph(measurement, resolver, …)` → `Segmentation` |
> | `azimuthal_average(image)`, `radius_to_q`, `weighted_mean` | — (reductions that used to hide inside plots) |
> | `plot_fit`, `plot_distribution`, `plot_outlines`, `plot_series`, `plot_marked_curve`, `plot_image` | `plot_peak_fit`, `plot_size_distribution`, `plot_segmentation`, `plot_spectra`, `plot_endpoint_spectrum` |
>
> **Analysing and drawing are never one function.** An analysis returns a
> result and draws nothing; a plot takes a result (or arrays) and computes
> nothing worth keeping. Every plot takes `ax=None` — draws there when given
> one — and returns what it drew on (`fig=None` for the Plotly figures). So:
>
> ```python
> seg = segment_micrograph(measurement, resolver, image_index=0)   # analysis
> plot_segmentation(seg, ax=ax)                                    # picture
>
> result = org.fit("S01", "waxs1d", x_range=(2.3, 3.0))            # analysis
> org.plot_fit(result, ax=ax)                                      # picture
> ```


Analyses turn measurements into **derived values** — scalars that land in the
same table as the authored parameters and can be filtered, plotted and compared
alongside them. That loop (filter → analyse → new columns → filter again) is
the point of the package.

Read [`sample_model.md`](sample_model.md) first for Project / Sample /
Measurement.

## The shape of an analysis

```python
def my_analysis(measurement, resolver, **options) -> AnalysisResult
```

An `AnalysisResult` keeps three things apart, deliberately:

| field | what it holds | stored on the sample? |
|---|---|---|
| `values` | scalars — a peak position, a mean diameter, a rate | **yes**, as `derived.*` |
| `curves` | arrays for plotting — the fit, the residuals, the frames | no |
| `diagnostics` | fit window, R², counts, settings, what was excluded | yes, inside the derived record |

Mixing them is how a results table ends up quietly comparing a well-determined
number against one fitted to four noisy points. `write_to()` skips non-finite
values: a NaN is the absence of a measurement, and storing it as one makes the
table lie.

## What ships

Three analyses, all technique-neutral:

| key | applies to | produces |
|---|---|---|
| `peak_fit` | any 1D curve | `peak<n>_center`, `peak<n>_amplitude`, `peak<n>_width`, `baseline`, `fit_r2` |
| `curve_metrics` | any 1D curve or correlation function | `y_max`, `x_at_max`, `y_min`, `area`, `x_centroid`, `y_mean`, `x_at_threshold` |
| `particle_sizing` | tem, sem, optical | `d_mean`, `d_median`, `d_std`, `d_cv`, `d_p10`, `d_p90`, `n_particles` |

Anything that assumes a chemistry belongs in a package of its own, which
registers itself on import:

```python
from NanoOrganizer.analysis import Analysis, register_analysis

# KERNEL — the science. Arrays in, result out. No files, no project.
def measure_my_assay(x, y, *, window=None):
    ...
    return MyAssayResult(...)

# ADAPTER — the plumbing. Register this one.
def my_assay(measurement, resolver, *, window=None, **io):
    from NanoOrganizer.analysis.peaks import load_curve

    try:
        x, y, info = load_curve(measurement, resolver, **io)
        found = measure_my_assay(x, y, window=window)
    except (FileNotFoundError, ValueError) as exc:
        return AnalysisResult.failure("my_assay", str(exc),
                                      sample_id=measurement.sample_id)
    result = AnalysisResult(analysis="my_assay",
                            sample_id=measurement.sample_id,
                            measurement_id=measurement.measurement_id)
    ...
    return result

register_analysis(Analysis(
    key="my_assay", func=my_assay, label="My assay",
    modalities=("uvvis",), stages=("reaction",),
    description="…",
))
```

Write the kernel first and test it on synthetic data with a known answer
(`tests/test_kernels.py` is the pattern); the adapter's own test is then only
about whether it finds the right file and reports a failure as a row rather
than an exception.

The registry is what lets a notebook and the GUI both ask "what can I run on
this?" without either keeping a list — and what lets an external package extend
both at once.

## One settings dict, three levels

Give an analysis a **method on arrays** and the same settings work everywhere.
The method takes its data positionally — the arrays, and facts about the
sample such as a trigger time — and its settings as keyword-only parameters,
and returns an `AnalysisResult`. Register it as the analysis' `kernel`; the
adapter then only loads a sample's data and calls it:

```python
def my_assay_method(x, y, *, window=(2.0, 4.0), scale=1.0) -> AnalysisResult:
    ...

def my_assay(measurement, resolver, **settings):
    x, y, info = load_curve(measurement, resolver)
    return my_assay_method(x, y, **settings)       # plus sample/measurement ids

register_analysis(Analysis(key="my_assay", func=my_assay,
                           kernel=my_assay_method, modalities=("uvvis",)))
```

```python
settings = dict(window=(2.5, 3.5), scale=2.0)
org.run_method("my_assay", x, y, settings=settings)   # arrays you hold
org.run("my_assay", "S01", settings=settings)         # one sample
org.batch("my_assay", ["S01", "S02"], settings=settings)  # a list; None = all
```

A name that is not one of the method's settings is refused, rather than run
with the default. Every result records the settings it ran with, defaults
included (`result.settings`, kept in its file).

**Done before.** `run` and `batch` look for a result kept (linked) for that
measurement with the same settings and load it instead of running again; a
batch row says `status` = `ran`, `loaded` or `failed`. Other settings, a
missing file, or a result kept before settings were recorded run again, and
`overwrite=True` runs regardless. An analysis on another one's stored result
also runs again when that input was redone with other settings.

**New data.** `wb.kept_settings(key)` is the settings dict the kept results
were made with (the most common, `{}` if none). Passing it on analyses new
samples the way the others were and loads the rest:
`wb.batch(key, settings=wb.kept_settings(key), link=True)`.
`wb.kept_settings(key, sample_id)` is the dict one sample's kept result was
made with — how a page tells a sample redone with other settings from the rest.

An analysis can also run on another analysis' stored result: declare
`modalities=("fit",), stages=("analysis",), results_of=("my_assay",)` and its
adapter is handed the linked result file of `my_assay` (read it with
`NanoOrganizer.analysis.store.load_result`). It applies to those results only
— not to its own, so running it twice does not run it on itself.

## Derived names carry the modality

An analysis that applies to more than one modality prefixes its derived values
with the modality of the measurement it ran on:

```
derived.uvvis_peak1_center       derived.waxs1d_peak1_center
derived.tem_d_mean               derived.sem_d_mean
```

Without that, peak fitting a UV-Vis band and then a diffraction peak would put
both centres in one `derived.peak1_center` column and the second would win
silently — the kind of bug that produces a plausible plot of the wrong thing.
An analysis that can only mean one thing (one declared modality) writes a bare
name; an explicit `prefix=` on the registration or on `batch()` always wins,
and `prefix=""` opts out.

`batch()` also takes `role=`, which separates two measurements of the same
technique on the same sample — an as-made and a post-reaction scan, say.

## Peak fitting

A background plus *n* Gaussian, Lorentzian or pseudo-Voigt peaks, fitted with
`scipy.optimize.curve_fit`.

`background` is `"constant"` or `"linear"`. A sloping background is the normal
case away from UV-Vis — an XPS inelastic tail, a Raman fluorescence ramp,
bremsstrahlung under an EDS line, an interband edge under a plasmon — and
fitting a flat one through it does not merely lower R²: **it drags the peak
centre up the slope.** If a fitted position looks systematically off, this is
the first thing to try. `tests/test_analysis.py` asserts both halves of that:
that the flat background biases the centre, and that the linear one recovers
it.

Initial guesses come from the data — the *n* strongest maxima, separated by at
least a tenth of the axis span. That separation matters: without it a two-peak
fit happily starts both components on the same bump and returns two identical
peaks with a meaningless width. Bounds keep peaks inside the axis and widths
positive.

When you know which peak is which, say so by name — that beats any automatic
guess:

```python
fit = fit_peaks(x, y, n_peaks=2, x_range=(260, 520),
                initial_guess={"peak1_center": 316, "peak2_center": 400},
                bounds={"peak1_center": (296, 336), "peak2_center": (380, 420)})
plot_fit(fit.x, fit.y, fit.y_fit, fit.residual, components=fit.components())
```

A named guess replaces only those parameters; the rest are still estimated. A
start outside its bounds is moved inside them. `fit.components()` is the
background and each peak on `fit.x` — they add up to `fit.y_fit` — and
`plot_fit(..., components=...)` draws them dashed, which is where a two-peak
fit shows which peak took which part of the curve.

Parameter uncertainties come from the covariance matrix. A non-finite entry
means that parameter was not actually determined, and is reported as absent
rather than as zero.

`min_r2` is a floor, not a target: a fit below it comes back with `ok=False`,
so a bad fit appears in the batch table instead of quietly contributing a
meaningless peak position.

## Curve metrics

Peak fitting answers *where is the band and how wide*. A great deal of routine
analysis needs no model at all, only a window and a question: how big is the
signal here, what is the area, where is its centre of mass, and at what x does
it cross this value?

That last one is worth noticing. It is the same operation as

* the potential at 10 mA cm⁻² — an overpotential;
* the energy at which an absorption edge reaches half height;
* the lag time at which a correlation function has half decayed.

Three techniques, three vocabularies, one question about the shape of a curve.
Writing it once, technique-independently, is the argument for the modality
registry in miniature.

The direction of the crossing is taken from the data, so a cathodic current
sweeping negative and an absorbance rising through a threshold go through the
same code. Multiple crossings are reported in the message rather than hidden,
and a threshold that is never reached produces no value and says what range
the curve actually spanned.

The centroid is taken over the positive part of the baseline-subtracted curve
only: negative lobes would otherwise drag the centre of mass outside the
feature entirely.

## Particle sizing

Otsu threshold, then watershed on the distance transform to separate particles
that touch. Classical rather than learned on purpose: particles on a support
are a high-contrast, nearly bimodal image, which is exactly the case
thresholding handles well and where a model would add a dependency and an
unaudited failure mode for nothing.

Five decisions worth knowing:

**Contrast polarity is read off the image, not assumed.** TEM particles are
dark on a light film; SEM particles are usually bright on a dark support.
Getting it backwards segments the *support* and reports its size with exactly
the same confidence — the worst available failure mode. Left as
`dark_particles=None`, the particle phase is taken to be the minority one
either side of the Otsu threshold, because a field more than half covered in
particles is not one you can size anyway. The decision is reported in
`diagnostics`.


**Sizes are in nm only when the file says so.** The pixel calibration is read
from the image's own metadata — electron microscopes commonly write it into the
TIFF description tag (`XpixCal=… Unit=um`). With no calibration and no
`nm_per_pixel=` override, diameters come back in **pixels** with
`calibrated: False`, never silently mislabelled.

**Instrument banners are cropped.** A frame taller than it is wide usually
carries an information bar below the image; it is bright, uniform, and would
otherwise segment as one enormous particle.

**Watershed seed spacing is derived from the data**, not fixed. The same grid
gets imaged across a wide range of magnifications, and a spacing that separates
touching particles at one of them bisects a single particle at another.

**Faint blobs are rejected by contrast.** A dense particle absorbs strongly, a
support's texture does not, so a particle-sized blob barely darker than the
support is texture. `min_contrast_frac=0` keeps everything.

Pooling frames of different magnification is reported, not hidden: when they
differ by more than 2×, the message says which fraction of the distribution
came from the widest field. Mean and median are both reported, because they
diverge exactly when unseparated clusters survive into the tail.

## Finding the straight part of a curve

`analysis.linear.linear_region` locates the stretch of a curve that is actually
linear and fits only that, excluding an induction period and any plateau. It is
used by kinetics analyses in downstream packages and is available to yours.

It deliberately does **not** assume the process finishes. A run stopped at 40 %
conversion has no plateau, and a detector that brackets between "left the
baseline" and "reached the plateau" returns nothing for it. The active region is
bracketed on where the *local slope* is a meaningful fraction of its own
maximum instead, which degrades gracefully to "the tail of the data".

Every result reports the window it used. **A slope without its window is not a
measurement** — it cannot be compared with another one.

## Reading frames

`analysis.frames.load_series` reads a measurement's files into a `FrameSeries`:
*n* frames on one shared axis, with a time per frame recovered from the
filenames.

A **frame grammar** does that recovery. Three general ones are registered
(`batch_time`, `time_only`, `frame_index`); an instrument with its own
convention adds one call:

```python
import re
from NanoOrganizer.analysis.frames import FrameGrammar, register_grammar

register_grammar(FrameGrammar(
    key="my_rig", label="…",
    patterns=(re.compile(r"shot(?P<t>\d+)ms"),)))
```

Detection requires a grammar to parse at least half the filenames, so a
coincidental match on a stray file cannot select the wrong one.

`FrameSeries` names its axis `x` and its data `values`, because the class has no
business knowing the technique; `wavelength` and `absorbance` are aliases for
when spectroscopy reads better. Slicing returns new instances, and per-frame
metadata is sliced along with the frames — otherwise it silently goes out of
step with what it describes.

For data that is not a time series, `analysis.reading` provides generic readers
(`load_image`, `load_volume`, `load_curve_set`) that the GUI uses to display any
modality.

## Batch

```python
frame = analysis.batch(project, "peak_fit", sample_ids=basket)
```

Runs over every matching measurement, writes the scalars back under a
modality-aware prefix, and returns one row per measurement **including the
failures**, with `ok=False` and a message.
A batch that silently skips its failures is worse than no batch at all. One
exception cannot end the run. The project is not saved — call `project.save()`
once the table looks right.

## Workbench

`Workbench` binds a project, a **basket** (the current selection) and the
analyses together. The GUI uses the same class, so a page and a notebook cannot
drift apart in behaviour.

```python
from NanoOrganizer import open_project

wb = open_project("/data/MyProject")
wb.filter("`synthesis.conditions.temperature_C` >= 90")
wb.batch("peak_fit")            # acts on the basket
wb.plot_compare("synthesis.conditions.temperature_C", "derived.peak1_center")
wb.save()
```

`notebook/` walks the whole pipeline on a generated project:

| notebook | |
|---|---|
| `00_quickstart` | build the demo project, open it, check what resolves |
| `01_explore_filter` | the table, finding columns, filtering, the basket |
| `02_visualize` | curves, series, images, segmentation |
| `03_analyze_batch` | single runs, batches, derived columns |
| `04_compare` | structure–property plots, and checking against the truth |

## Plot colours

`NanoOrganizer.viz.plots` applies one house style. Categorical hues are assigned
in fixed order and never cycled, so adding a series cannot repaint the others.
Scatter plots cap at three categories and fold the rest into a neutral "Other" —
a scatter asks the eye to separate every pair at once, not just neighbours.
Magnitude (time, temperature) uses one hue light-to-dark, so the ordering
survives greyscale and colour-blind viewing. A legend is always drawn for two or
more series.
