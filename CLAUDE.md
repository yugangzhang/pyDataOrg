# Rules for working in this repository

These hold for every change, by a person or a coding assistant. The full
reasoning is in [`docs/kernel_adapter_rule.md`](docs/kernel_adapter_rule.md).

## Analysis and plotting

1. **Kernel and adapter.** Every analysis and every plot is written twice: a
   *kernel* that takes plain arrays and returns a result (no files, no
   project, no config), and a thin *adapter* that finds the data, calls the
   kernel and files the answer. The adapter contains no arithmetic.
2. **Plots take `ax=None` and return what they drew on.** Given an `Axes`,
   draw there and nowhere else; given nothing, make a figure. Return the
   `Axes` (or a tuple for multi-panel). Plotly functions take `fig=None` with
   `row=`/`col=` and return the figure. Never `plt.show()`, `savefig()` or
   `plt.close()` inside a plotting function.
3. **Never analyse and draw in one function.** A function computes a result
   *or* draws one. No `show=True` on an analysis, no plot that fits, segments,
   integrates or runs an analysis because it was handed a sample id. Display
   arithmetic (limits, contrast clip, log for display, striding) is fine; a
   number a reader would want to keep is not.

## Package

4. **Public, standalone, domain-neutral.** No dependency on a personal repo,
   project data, or beamline vocabulary — that belongs in `a project package`.
5. **Generated data goes under `demo_root()`** (`../OrgDemo` beside the
   checkout, or `$NANOORGANIZER_DEMO_ROOT`). Nothing writes into the home
   directory itself.
6. **No absolute paths in anything published.** A relative path is relative
   to the project root (the organizer's folder); generators, links and stored
   fits record relative paths when the data is inside it. Show locations with
   `core.pathmap.display_path` — in notebooks, the GUI and docs, a reader
   should see `../OrgDemo/CuAu`, never `/home/<someone>/…`.
7. **Link, don't auto-attach.** `attach_folders()` is the exception for a tidy
   `<Modality>Data/<SampleID>/` layout; documentation leads with `link()`.
8. **One generator per demo.** Notebooks and the web app call the same
   functions in `NanoOrganizer/demo/` — never a copy pasted into a cell.

## Web app

9. Only `web_app/Home.py` calls `st.set_page_config()`.
10. Pages drive the same `Workbench`/`Organizer` the notebooks use; a page
   composes analysis and plotting calls, it does not reimplement them.

## Tests

`pytest` must stay green. Kernel tests use synthetic arrays with a known
answer and touch no files; web pages are driven through `AppTest`
(assert `not app.exception` — it is an empty list, not `None`, on success).
