# Notebooks

Four notebooks, all on **generated** data — nothing to download, nothing to
configure.

## The workflow: simulate → build → use

Start here. It is the shape a real campaign actually has — on a campaign big
enough to be worth organising: an **A–B alloy nanocatalyst library** (A and
B are fictional metals), eight alloys and one failed synthesis, **fifteen
techniques across four stages**, all following from one hidden number per
sample, the B fraction *x*.

| | |
|---|---|
| `10_simulate_data` | the campaign on disk: four metadata dicts that describe most of it, four techniques in bare folders that nobody described, a sparse matrix, and the answer key |
| `11_build_organizer` | `Organizer("demo.json")` — `ingest` the four dicts, `link` the four folders by hand |
| `12_use_organizer` | reopen it and work, in six parts |
| `13_campaign_next` | the same organizer as a campaign: rank, Pareto front, propose the next experiments and check the model; then what an AI agent and an ML model see |

Run them in order; `11` and `12` use what `10` leaves in `../OrgDemo/Demo`,
beside the repository:

```
../OrgDemo/Demo/
├── MetaData/ …    the data and the four *_dict.py   (10)
├── truth.csv      the answer key                     (10)
├── demo.json      the organizer                      (11)
└── results/       stored fits                        (12)
```

Every path in it — in the metadata, the links, the stored fits — is relative
to that folder, so it moves as one piece, and no notebook output names
anyone's home directory.

`10` calls `pyDataOrg.demo.build_showcase_project`. The same function is
behind `dataorg demo --campaign` (all of `10` in one command)
and the web app's **🎓 Demo** page, which walks `10` → `11` → `12` with
buttons — so the three routes write identical files and cannot drift apart.

`12` is laid out the way a session actually goes:

| | |
|---|---|
| **A** | load it, look at it (`describe`, `tree`, `catalog`), carve out a `subset` |
| **B** | load data — curves, images, a memory-mapped tomogram — eager, or `lazy=True` one frame at a time |
| **C** | visualise all four kinds of data — the quick call, your own figure from B, a rotatable tomogram |
| **D** | fit one diffraction pattern on arrays, turn it into a composition, *then* batch nine analyses across the campaign |
| **E** | compare: three routes to one composition, three sizes that disagree for a reason, and the Sabatier volcano straight off the table |
| **F** | reload, read the stored fits back, go round again |

Because the data is simulated, part E checks the answers: composition from
diffraction and from EDS lands on the generator's value (within 0.02), the
plasmon band within 1 nm, XPS reads the B-rich *surface* rather than the
bulk, and the P current peaks at the intermediate composition.

The through-line is that **nothing is a dead end**: every quick call has a
lower-level one underneath handing you the arrays, because the moment an
analysis gets interesting it stops fitting whatever the convenience function
assumed.

Two rules show up in every cell that draws. Analysing and drawing are **two
calls** — `fit_peaks` returns a result, `plot_fit` draws it — and every plot
takes **`ax=`**, draws into the figure you made, and returns the axes it drew
on. See [`docs/kernel_adapter_rule.md`](../docs/kernel_adapter_rule.md).

The organizer is **one JSON file you name** — not a directory layout, not a
hidden folder. A document you can copy, diff and version, holding where every
sample's data is, what it was made from, and what the analyses found. The data
itself never moves.

```python
org = Organizer(demo_root("Demo", "demo.json"))

org.ingest("MetaData/Testing_dict.py")              # what somebody wrote down
org.link("S05", "tem", "TEMData/S05")         # what nobody did — relative to demo.json
org.save()
```

**There is no auto-attach in this track, on purpose.** The four bare folders
happen to be named `<Modality>Data/<SampleID>/`, so `attach_folders()` would
find them — but almost no real campaign is laid out that way, and teaching it
as the normal route builds a habit that breaks on contact with one. These
notebooks link by hand, which is what you would actually do.

## Does this scale?

Yes — keying on `sample_id` is not a small-campaign idea. With **10 000
samples** and one measurement each, on an ordinary laptop:

| | |
|---|---|
| ingest 10 000 records | 0.15 s |
| link 10 000 measurements | 0.10 s |
| save / load | 0.9 s / 0.4 s (13 MB) |
| `table()` (10 000 × 19) | 0.3 s |
| `filter()` | 0.1 s |
| `availability()` — touches the filesystem | 0.9 s |

Nothing in the model is per-pair or per-combination, so a plate-based
high-throughput campaign uses exactly the same calls as a six-sample one.
`tests/test_organizer.py` keeps a guard on it.

## The campaign: `13`

`13` reads the organizer `12` left as a **campaign** — the demo registers
`AB-library`: one input (the B fraction the synthesis chose), three goals
(P current and P selectivity up, hydrogen down). It ranks the alloys, draws
the Pareto front, fits a Gaussian process per goal and proposes three
compositions to make next — at the P-current volcano, on its selective
shoulder, and where hydrogen is lowest — after checking by leave-one-out that
the model has learned both goals. The last cells are the same organizer as an
agent's tools (`pyDataOrg.agent`, or `dataorg mcp`) and as a samples ×
features table. See [`docs/platform.md`](../docs/platform.md).
