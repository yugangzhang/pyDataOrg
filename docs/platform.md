# The platform: building on pyDataOrg

pyDataOrg is the foundation that project packages build on. It organises,
draws and analyses; it knows nothing about a particular material, instrument
or facility. This page is the contract between the two — what a project
package can add, and the general machinery it gets for free.

```
pyDataOrg (public, general)                    a project package (yours)
───────────────────────────                    ─────────────────────────
core/       sample model, links, paths         its file-name grammars
ingest/     records → samples                  its record formats
analysis/   kernels, registry, kept results    its analyses (+ how to draw them)
viz/        plots, interactive, campaign       its figures
campaign    inputs → results → goals           its campaign: columns, goals, bounds
optimize    surrogate + engines                its optimiser engine (optional)
snapshots   dated copies of live records       where its live records are
servers     machines and their mounts          its machines
agent       operations, tools, MCP             its own operations (optional)
export      samples × features                 —
plugins     the hook                           Plugin(pages=…, register=…)
web_app/    the GUI and shared controls        its pages
```

Nothing project-specific goes into pyDataOrg: no real data (every demo is
generated), no instrument or facility vocabulary, no dependency on a private
package. Everything below goes the other way — a project package imports
pyDataOrg and registers into it.

---

## Plugins

A plugin is a `Plugin` object exposed under the `pyDataOrg.plugins` entry
point:

```python
# setup.py of the project package
entry_points={"pyDataOrg.plugins": ["myproj = myproj.plugin:PLUGIN"]}
```

```python
# myproj/plugin.py
from pyDataOrg.plugins import Page, Plugin

def _register():
    import myproj.analyses, myproj.campaign, myproj.servers   # registration on import

def _on_page():
    from myproj.web import state
    state.open_default_project()          # e.g. open the project's organizer once

PLUGIN = Plugin(
    name="myproj", title="My project", icon="⚗️",
    register=_register,                   # runs once, when the plugin loads
    on_page=_on_page,                     # runs on every GUI page, before the page
    defaults={"campaign": "my-screen"},   # what the general pages open with
    pages=[
        Page("myproj.web:views/overview.py", "Overview", "⚗️", default=True),
        Page("myproj.web:views/screen.py", "Screen", "🧪"),
    ],
)
```

`Page` paths are files, or `"package.module:relative/file.py"` resolved beside
an installed module. A page is an ordinary Streamlit script; it gets the open
organizer from `pyDataOrg.web_app.state.get_workbench()` and must not call
`st.set_page_config()` (only the entry point does).

| | |
|---|---|
| `dataorg plugins` | what is installed, its pages, and anything that failed to load |
| `dataorg gui` | the general pages plus one section per plugin |
| `dataorg gui --app myproj` | the plugin is the app: its title and icon, its pages first with plain URLs (`/overview`), general pages that would collide move to `/general_<name>` |
| `PYDATAORG_PLUGINS=a,b` | load only these (`none` for none) |

A plugin that raises while loading is listed with its error in the sidebar
and in `dataorg plugins`; the rest of the app runs.

A project that also wants its own launcher (a fixed port, its own allowed
folders) keeps a two-line `Home.py` that registers its plugin and runs
pyDataOrg's: see `pyDataOrg/web_app/Home.py` for what it does.

### Shared page controls

`pyDataOrg.web_app.components.controls` has the pieces a project's analysis
pages keep needing, each a notebook cell's worth:

| | |
|---|---|
| `settings(wb, analysis, key, name=…)` | the analysis' settings form, starting from the settings its kept results were made with; shows the dict to paste into a notebook |
| `keep_buttons(wb, analysis, sample, chosen, key=…)` | *Keep for this sample* / *Keep for every sample* — `wb.keep_results` |
| `metadata(wb, sample, stages, key)` | the sample's record as a `dict_tree` |
| `by_sample(...)`, `axes_options(...)`, `apply_axes(...)` | options of `plot_by_sample`, axis limits |

`components.campaign_picker.pick_campaign(wb)` is the campaign chooser the
Campaign and Next-experiments pages use.

---

## Kept results, and keeping a campaign up to date

`org.run(key, sample, link=True)` and `org.batch(key, link=True)` *keep* a
result: saved as a file and linked onto its sample, with the settings it was
made with. A kept result with the same settings loads instead of running
again. On top of that:

| | |
|---|---|
| `org.kept_analyses()` | the targets with kept results, in dependency order |
| `org.status(targets)` | per target: samples with data, kept, new |
| `org.new_samples(target)` | samples it could run on with nothing kept yet |
| `org.analyse_new(targets)` | run each on its new samples, with the kept settings |
| `org.keep_results(target, samples, settings=…)` | keep with these settings (an analysis of another's results keeps that one first) |
| `org.kept_settings(key, sample="", modality="")` | the settings kept results were made with |

A *target* is an analysis key, or `key@modality` for an analysis that runs on
several techniques — fitting the diffraction peaks and fitting the plasmon
band are two things to keep up to date, with two sets of settings
(`peak_fit@waxs1d`, `peak_fit@uvvis`). The GUI's **Analyze → Up to date?** tab
is `status` and `analyse_new`.

An analysis says how its result is drawn with `Analysis(..., plot=f)`, where
`f(result, ax=None)` returns what it drew on — the Analyze page draws any
registered analysis that way.

---

## Campaigns

A `Campaign` names the columns a campaign reads and what it wants:

```python
from pyDataOrg.campaign import Campaign, Column, Objective, register_campaign

register_campaign(Campaign(
    name="my-screen",
    columns=[
        Column("T_C", "synthesis.conditions.temperature_C", "temperature", "°C", "input"),
        Column("ratio", "synthesis.conditions.ligand_ratio", "ligand : metal", "", "input"),
        Column("batch", "synthesis.batch_tag", "batch"),                    # context
        Column("protocol", "testing.method.version", "assay", kind="protocol"),
        Column("size_nm", "particle_sizing:d_median", "TEM size", "nm", "result"),
        Column("rate", "testing.performance.rate_per_s", "rate", "1/s", "objective"),
        Column("yield", "testing.performance.yield_pct", "yield", "%", "objective"),
    ],
    objectives=[Objective("rate", log=True), Objective("yield")],
    when="tested_at", done=("status", "done"), protocol=("protocol",),
    bounds={"T_C": (60, 120), "ratio": (0.5, 8)}, rounding={"T_C": 1, "ratio": 0.1},
))
```

| kind | meaning |
|---|---|
| `input` | chosen by the experimenter or an optimiser |
| `context` | recorded alongside, not chosen — batch, status, timestamps |
| `protocol` | how a measurement was made; rows that differ are not comparable |
| `result` | measured or derived |
| `objective` | a result the campaign pushes one way |

A *source* is a sample-table column, or `analysis:value` — read from that
analysis' kept result files. `spec.table(org)` is the adapter; the rest are
kernels on a plain frame: `rank`, `pareto_mask`, `comparable`, `majority`,
`chronological`, `best_so_far`. `from_columns(table, inputs, objectives)` makes
one on the spot (the GUI's *build from columns*).

## Next experiments

```python
from pyDataOrg import optimize

plan = optimize.propose_for(spec, frame, n=4)         # inputs, goals, bounds, comparable rows from the spec
plan.suggestions                                      # inputs + <goal>_pred, <goal>_sd
gx, gy, mean, sd = plan.surface(50)                   # one or two inputs; gy is None for one
cv = optimize.cross_validate(frame, variables=spec.inputs,
                             objectives=spec.objectives, bounds=spec.bounds)
optimize.save_proposal(plan, "Proposals/")            # CSV + the evidence it came from
```

The built-in `"gp"` engine is a scikit-learn Gaussian process per goal
(Matérn 5/2 plus noise, inputs scaled to the bounds) and picks a batch by
random-scalarisation upper confidence bound, pushing each proposal away from
the ones already chosen. It is a baseline that needs nothing else. A stronger
optimiser is an `Engine` — `fit(X, Y, bounds, maximize)`, `predict(X)`,
`suggest(n)`, all in model space — registered with
`optimize.register_engine("name", factory)`. Objectives with `log=True` are
modelled as log₁₀ and converted back.

**Check before trusting.** `cross_validate` predicts each sample from the
others; an error near 1 × the spread means the model has not learned that
goal, and its proposals are exploration.

---

## Records that keep changing: snapshots

Records written somewhere that keeps changing are copied into the project as
dated snapshots, so every analysis ran on a file that still exists:

```python
from pyDataOrg.snapshots import FileSource, GitSource, plan_sync, write_snapshots

source = GitSource("~/Repos/instrument-control", "origin/main",
                   {"synthesis": "records/Synthesis_dict.py"})
plan = plan_sync("~/Data/MyProj", source, tag="MyProj")   # what changed; writes nothing
print(plan.summary())
write_snapshots(plan)                 # MetaData/Synthesis_dict_MyProj_<date>.py
```

`latest_snapshots(root)` is what to ingest; `compare_records` says which
samples are new, changed or gone.

## Machines: servers

```python
from pyDataOrg.servers import Server, register_server

register_server(Server("workstation", {"/instrument/share": "/mnt/lab"}))
org = Organizer("project.json", server="workstation")    # or "auto": the one mounted here
org.local("/instrument/share/run_a/*.csv")               # '/mnt/lab/run_a/*.csv'
```

The records keep the paths the instrument wrote; a server maps them per
machine (as aliases), so nothing is rewritten.

---

## For agents

`pyDataOrg.agent` lists the organizer's operations once, with JSON schemas:

| operation | |
|---|---|
| `describe_project` | samples, stages, techniques, analyses, derived columns |
| `list_columns`, `list_samples`, `sample_table`, `sample_record`, `list_measurements` | looking |
| `list_analyses`, `analysis_settings`, `run_analysis`, `batch_analysis` | analysing (`keep=true` needs write access) |
| `kept_results`, `analysis_status`, `analyse_new` | kept results |
| `list_campaigns`, `campaign_table`, `propose_next` | campaigns |
| `save` | write the organizer (write access) |

```python
agent.call(org, "sample_table", columns=["testing.performance.FE_CO_pct"], limit=5)
agent.tool_specs("anthropic")     # [{name, description, input_schema}, …]; also "openai", "mcp"
agent.register_operation(Operation("my_op", "…", func, parameters={...}))
```

Results are plain JSON (NaN → null, paths relative); errors are
`{"error": "..."}`. Operations that change the organizer or write files are
refused unless the caller passes `allow_writes=True` — grant it deliberately.

`dataorg mcp STORE` serves the operations to any MCP client over stdio
(tools only, no dependencies):

```bash
claude mcp add myproj -- dataorg mcp /path/to/project.json
dataorg ops list_samples --store project.json --json '{"query": "`x` > 0.5"}'
```

## For machine learning

```python
from pyDataOrg.export import feature_frame, feature_table, write_table

X = feature_table(org, min_coverage=0.8)                 # every numeric field
X = feature_table(org, campaign="my-screen")             # the campaign's columns, kept results included
X = feature_frame(table, include=["synthesis"], categorical="codes")   # kernel, on any table
write_table(X, "features.parquet")                       # .csv, .parquet, .json
```

Rows are samples (`sample_id` index); text columns are dropped or coded,
constant columns removed.
