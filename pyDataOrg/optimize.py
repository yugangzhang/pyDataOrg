#!/usr/bin/env python3
"""
Which experiments to run next: a surrogate model of the campaign so far, and
a batch of proposals from it.

One model per objective is fitted to the campaign (inputs → results), and an
*engine* proposes a batch of inputs expected to improve on what has been
measured::

    from pyDataOrg import optimize

    plan = optimize.propose(frame, variables=["x"], objectives=goals,
                            bounds={"x": (0.0, 1.0)}, n=4)
    plan.suggestions                     # inputs + predicted mean ± sd
    mean, sd = plan.predict(points)      # the surrogate, for maps
    optimize.cross_validate(frame, ...).summary()   # check before trusting

**Engines.** The built-in ``"gp"`` engine is deliberately plain: one
scikit-learn Gaussian process per objective (Matérn 5/2 + noise, inputs scaled
to the bounds) and a batch picked by *random-scalarisation upper confidence
bound* — each proposal weights the objectives at random, prefers high
predicted value plus uncertainty, and is pushed away from the proposals
already chosen. It is a sound baseline with nothing but scikit-learn. A
project that wants a stronger acquisition (qNEHVI, trust regions …) registers
its own engine with :func:`register_engine` and passes ``engine="name"``.

**Check before trusting.** :func:`cross_validate` predicts each sample from
the others; a goal whose leave-one-out error is as large as its spread is not
being learned, and proposals for it are exploration.

Everything here is a kernel: frames and arrays in, nothing read or written
except by :func:`save_proposal`, which only writes where it is told.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from pyDataOrg.campaign import Objective, pareto_mask, usable

Bounds = Mapping[str, Tuple[float, float]]


# ---------------------------------------------------------------------------
# Engines
# ---------------------------------------------------------------------------

class Engine:
    """What :func:`propose` needs from an optimiser.

    All values are in *model* space: an objective with ``log=True`` arrives
    as ``log10``. ``fit`` receives the bounds in the variables' order and
    which objectives are maximised; ``predict`` returns mean and sd of every
    objective, ``(n, m)`` each; ``suggest`` returns ``(n, d)`` inputs.
    """

    def fit(self, X: np.ndarray, Y: np.ndarray,
            bounds: Sequence[Tuple[float, float]], maximize: Sequence[bool],
            seed: int = 0) -> "Engine":                     # pragma: no cover
        raise NotImplementedError

    def predict(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        raise NotImplementedError                           # pragma: no cover

    def suggest(self, n: int, seed: int = 0) -> np.ndarray:
        raise NotImplementedError                           # pragma: no cover


class GPEngine(Engine):
    """One scikit-learn GP per objective; random-scalarisation UCB batches.

    *beta* weighs uncertainty against predicted value (larger explores
    more); *candidates* is how many quasi-random points the acquisition is
    evaluated on; *spacing* is how far apart (as a fraction of each range)
    proposals in one batch try to be.
    """

    def __init__(self, beta: float = 1.5, candidates: int = 2048,
                 spacing: float = 0.08):
        self.beta = beta
        self.candidates = candidates
        self.spacing = spacing

    def _unit(self, X) -> np.ndarray:
        X = np.atleast_2d(np.asarray(X, dtype=float))
        return (X - self._lo) / self._span

    def fit(self, X, Y, bounds, maximize, seed: int = 0) -> "GPEngine":
        try:
            from sklearn.gaussian_process import GaussianProcessRegressor
            from sklearn.gaussian_process.kernels import (
                ConstantKernel, Matern, WhiteKernel,
            )
        except ImportError as exc:                          # pragma: no cover
            raise ImportError(
                "the 'gp' engine needs scikit-learn: "
                "pip install \"pyDataOrg[optimize]\"") from exc

        bounds = np.asarray(bounds, dtype=float)
        self._lo, self._span = bounds[:, 0], np.ptp(bounds, axis=1)
        self._span[self._span == 0] = 1.0
        self.maximize = list(maximize)
        self.X = np.asarray(X, dtype=float)
        self.Y = np.asarray(Y, dtype=float)
        d = self.X.shape[1]
        self.models = []
        for j in range(self.Y.shape[1]):
            y = self.Y[:, j]
            ok = np.isfinite(y)
            kernel = (ConstantKernel(1.0, (1e-3, 1e3))
                      * Matern(length_scale=np.full(d, 0.3),
                               length_scale_bounds=(0.03, 10.0), nu=2.5)
                      + WhiteKernel(1e-2, (1e-6, 1.0)))
            model = GaussianProcessRegressor(kernel=kernel, normalize_y=True,
                                             n_restarts_optimizer=3,
                                             random_state=seed)
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")   # convergence chatter
                model.fit(self._unit(self.X[ok]), y[ok])
            self.models.append(model)
        return self

    def predict(self, X) -> Tuple[np.ndarray, np.ndarray]:
        U = self._unit(X)
        mean = np.empty((len(U), len(self.models)))
        sd = np.empty_like(mean)
        for j, model in enumerate(self.models):
            mean[:, j], sd[:, j] = model.predict(U, return_std=True)
        return mean, sd

    def suggest(self, n: int, seed: int = 0) -> np.ndarray:
        rng = np.random.default_rng(seed)
        d = len(self._lo)
        try:
            from scipy.stats import qmc
            U = qmc.Sobol(d, scramble=True, seed=seed).random(self.candidates)
        except Exception:                                   # pragma: no cover
            U = rng.random((self.candidates, d))
        X = self._lo + U * self._span
        mean, sd = self.predict(X)
        # Scale each objective by the spread of what was measured, and turn
        # minimised ones round, so "bigger is better" for every column.
        sign = np.where(self.maximize, 1.0, -1.0)
        spread = np.nanstd(self.Y, axis=0)
        spread[~np.isfinite(spread) | (spread == 0)] = 1.0
        value = (mean * sign) / spread
        doubt = sd / spread
        picked: List[np.ndarray] = []
        for _ in range(int(n)):
            weights = rng.dirichlet(np.ones(value.shape[1]))
            score = (value + self.beta * doubt) @ weights
            for chosen in picked:                   # keep the batch spread out
                distance = np.sqrt(((U - chosen) ** 2).sum(axis=1))
                score = score - np.abs(score).max() * np.exp(
                    -0.5 * (distance / self.spacing) ** 2)
            best = int(np.argmax(score))
            picked.append(U[best])
        return self._lo + np.vstack(picked) * self._span


ENGINES: Dict[str, Callable[[], Engine]] = {"gp": GPEngine}


def register_engine(name: str, factory: Callable[[], Engine]) -> None:
    """Make an optimiser available as ``engine=name``. *factory* returns a
    fresh :class:`Engine`."""
    ENGINES[name] = factory


def list_engines() -> List[str]:
    return list(ENGINES)


def make_engine(engine="gp") -> Engine:
    if isinstance(engine, Engine):
        return engine
    try:
        return ENGINES[engine]()
    except KeyError:
        raise KeyError(f"no engine {engine!r}; registered: "
                       f"{', '.join(ENGINES)}") from None


# ---------------------------------------------------------------------------
# Units: the model works on log10 for objectives that ask for it
# ---------------------------------------------------------------------------

def to_model(Y, objectives: Sequence[Objective]) -> np.ndarray:
    Y = np.array(Y, dtype=float, copy=True)
    for j, o in enumerate(objectives):
        if o.log:
            with np.errstate(divide="ignore", invalid="ignore"):
                Y[:, j] = np.where(Y[:, j] > 0, np.log10(Y[:, j]), np.nan)
    return Y


def from_model(mean, sd, objectives: Sequence[Objective]
               ) -> Tuple[np.ndarray, np.ndarray]:
    """Back to the objectives' own units (sd by the delta method)."""
    mean, sd = np.array(mean, dtype=float), np.array(sd, dtype=float)
    for j, o in enumerate(objectives):
        if o.log:
            value = 10.0 ** mean[:, j]
            sd[:, j] = value * np.log(10.0) * sd[:, j]
            mean[:, j] = value
    return mean, sd


def snap(X, variables: Sequence[str], bounds: Bounds,
         rounding: Optional[Mapping[str, float]] = None) -> np.ndarray:
    """Round proposals to the steps that can actually be set, inside the
    bounds."""
    X = np.array(X, dtype=float, copy=True)
    for j, name in enumerate(variables):
        step = (rounding or {}).get(name)
        if step:
            X[:, j] = np.round(X[:, j] / step) * step
        lo, hi = bounds[name]
        X[:, j] = np.clip(X[:, j], lo, hi)
    return X


# ---------------------------------------------------------------------------
# The proposal
# ---------------------------------------------------------------------------

@dataclass
class Proposal:
    """A fitted surrogate and the batch of inputs it proposes."""

    variables: List[str]
    objectives: List[Objective]
    bounds: Dict[str, Tuple[float, float]]
    samples: List[str]
    X: np.ndarray
    Y: np.ndarray
    suggestions: pd.DataFrame
    engine: object = field(repr=False, default=None)
    engine_name: str = "gp"
    seed: int = 0
    notes: List[str] = field(default_factory=list)

    @property
    def maximize(self) -> List[bool]:
        return [o.maximize for o in self.objectives]

    @property
    def pareto(self) -> np.ndarray:
        """Mask of the measured samples on the Pareto front."""
        return pareto_mask(self.Y, self.maximize)

    def predict(self, X) -> Tuple[np.ndarray, np.ndarray]:
        """Surrogate mean and sd, ``(n, m)`` each, in the objectives' units."""
        mean, sd = self.engine.predict(np.atleast_2d(np.asarray(X, float)))
        return from_model(mean, sd, self.objectives)

    def grid(self, n: int = 50):
        """Points over the first one or two variables.

        One variable: ``(gx, None, points)`` with ``gx`` of length *n*.
        Two: ``(gx, gy, points)`` with ``gx``/``gy`` ``n × n``. Other
        variables, if any, are held at the middle of their bounds.
        """
        if not self.variables:
            raise ValueError("no input variables")
        middle = np.array([np.mean(self.bounds[v]) for v in self.variables])
        if len(self.variables) == 1:
            lo, hi = self.bounds[self.variables[0]]
            gx = np.linspace(lo, hi, n)
            return gx, None, gx[:, None]
        (x0, x1), (y0, y1) = (self.bounds[v] for v in self.variables[:2])
        gx, gy = np.meshgrid(np.linspace(x0, x1, n), np.linspace(y0, y1, n))
        points = np.tile(middle, (gx.size, 1))
        points[:, 0], points[:, 1] = gx.ravel(), gy.ravel()
        return gx, gy, points

    def surface(self, n: int = 50):
        """``(gx, gy, mean, sd)`` on :meth:`grid` — ``gy`` is ``None`` for a
        single variable; mean/sd are ``(points, m)``."""
        gx, gy, points = self.grid(n)
        mean, sd = self.predict(points)
        return gx, gy, mean, sd


def _training(frame, variables, objectives, rows):
    names = [o.name for o in objectives]
    if rows is None:
        rows = usable(frame, list(variables) + names)
    data = frame.loc[rows]
    X = data[list(variables)].to_numpy(dtype=float)
    Y = data[names].to_numpy(dtype=float)
    samples = list(data["sample"]) if "sample" in data else \
        [str(i) for i in data.index]
    return data, X, Y, samples


def propose(frame: pd.DataFrame, *, variables: Sequence[str],
            objectives: Sequence[Objective], bounds: Bounds, n: int = 4,
            rows: Optional[pd.Series] = None, seed: int = 0,
            rounding: Optional[Mapping[str, float]] = None,
            engine="gp") -> Proposal:
    """Fit the campaign and propose *n* inputs to try next.

    *rows* selects the training rows (default: every row with all
    *variables* and objectives). Proposals are rounded to *rounding* and
    clipped to *bounds*.
    """
    variables, objectives = list(variables), list(objectives)
    missing = [v for v in variables if v not in bounds]
    if missing:
        raise ValueError(f"no bounds for {', '.join(missing)}")
    bounds = {v: (float(bounds[v][0]), float(bounds[v][1])) for v in variables}
    data, X, Y, samples = _training(frame, variables, objectives, rows)
    if len(data) < 3:
        raise ValueError(f"only {len(data)} usable samples; the surrogate "
                         f"needs at least 3")
    name = engine if isinstance(engine, str) else type(engine).__name__
    model = make_engine(engine).fit(X, to_model(Y, objectives),
                                    [bounds[v] for v in variables],
                                    [o.maximize for o in objectives], seed=seed)
    picked = snap(model.suggest(int(n), seed=seed), variables, bounds, rounding)
    mean, sd = from_model(*model.predict(picked), objectives)

    table = pd.DataFrame(picked, columns=variables)
    table.insert(0, "proposal", [f"P{i + 1}" for i in range(len(table))])
    for j, o in enumerate(objectives):
        table[f"{o.name}_pred"] = mean[:, j]
        table[f"{o.name}_sd"] = sd[:, j]
    notes = []
    duplicates = table.duplicated(subset=variables)
    if duplicates.any():
        notes.append(f"{int(duplicates.sum())} proposals coincide after "
                     f"rounding to the settable steps")
    return Proposal(variables=variables, objectives=objectives, bounds=bounds,
                    samples=samples, X=X, Y=Y, suggestions=table, engine=model,
                    engine_name=name, seed=seed, notes=notes)


def propose_for(campaign, frame: pd.DataFrame, *,
                objectives: Optional[Sequence[Objective]] = None,
                bounds: Optional[Bounds] = None, n: int = 4,
                protocol: Optional[Mapping[str, object]] = None,
                seed: int = 0, engine="gp") -> Proposal:
    """:func:`propose` with a :class:`~pyDataOrg.campaign.Campaign`'s
    inputs, objectives, bounds, rounding and comparable rows."""
    objectives = list(objectives or campaign.objectives)
    rows = campaign.comparable(frame, [o.name for o in objectives],
                               protocol=protocol)
    return propose(frame, variables=campaign.inputs, objectives=objectives,
                   bounds=bounds or campaign.bounds, n=n, rows=rows, seed=seed,
                   rounding=campaign.rounding, engine=engine)


# ---------------------------------------------------------------------------
# Can the model be trusted?
# ---------------------------------------------------------------------------

@dataclass
class CrossValidation:
    """Leave-one-out predictions of every training sample."""

    objectives: List[Objective]
    table: pd.DataFrame            # sample, <name>, <name>_pred, <name>_sd …
    score: Dict[str, float]        # name -> RMSE / sd of the observations

    def verdict(self, name: str) -> str:
        value = self.score.get(name, float("nan"))
        if not np.isfinite(value):
            return "no spread to learn"
        return ("predictive" if value < 0.8 else
                "weak" if value < 1.0 else "no better than the mean")

    def summary(self) -> str:
        return "\n".join(
            f"{name:20s} LOO error = {value:.2f} × its spread — "
            f"{self.verdict(name)}" for name, value in self.score.items())


def cross_validate(frame: pd.DataFrame, *, variables: Sequence[str],
                   objectives: Sequence[Objective], bounds: Bounds,
                   rows: Optional[pd.Series] = None, seed: int = 0,
                   engine="gp") -> CrossValidation:
    """Refit without each sample in turn and predict it.

    The score is the root-mean-square error divided by the spread of the
    observations: below ~0.8 the model has learned something about that goal;
    at 1 or above it predicts no better than the campaign average, and its
    proposals for that goal are exploration, not exploitation. One fit per
    sample.
    """
    variables, objectives = list(variables), list(objectives)
    bounds = {v: tuple(bounds[v]) for v in variables}
    data, X, Y, samples = _training(frame, variables, objectives, rows)
    names = [o.name for o in objectives]
    mean = np.full(Y.shape, np.nan)
    sd = np.full(Y.shape, np.nan)
    for i in range(len(X)):
        keep = np.arange(len(X)) != i
        model = make_engine(engine).fit(
            X[keep], to_model(Y[keep], objectives),
            [bounds[v] for v in variables], [o.maximize for o in objectives],
            seed=seed)
        m, s = from_model(*model.predict(X[i:i + 1]), objectives)
        mean[i], sd[i] = m[0], s[0]
    table = pd.DataFrame({"sample": samples})
    for j, v in enumerate(variables):
        table[v] = X[:, j]
    for j, name in enumerate(names):
        table[name] = Y[:, j]
        table[f"{name}_pred"] = mean[:, j]
        table[f"{name}_sd"] = sd[:, j]
    spread = np.nanstd(Y, axis=0)
    rmse = np.sqrt(np.nanmean((mean - Y) ** 2, axis=0))
    score = {name: float(rmse[j] / spread[j]) if spread[j] > 0 else float("nan")
             for j, name in enumerate(names)}
    return CrossValidation(objectives=objectives, table=table, score=score)


def save_proposal(plan: Proposal, folder, *,
                  settings: Optional[Mapping] = None,
                  table: Optional[pd.DataFrame] = None,
                  stamp: Optional[str] = None):
    """Write ``<stamp>_proposals.csv`` and ``<stamp>_settings.json`` to
    *folder*; returns both paths.

    The settings file records the goals, bounds, engine, seed and the
    samples the model was trained on, so a proposal can be traced back to
    its evidence. *table* replaces the suggestions (e.g. with volumes added).
    """
    import datetime as _dt
    import json
    from pathlib import Path

    folder = Path(folder).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    stamp = stamp or _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    csv = folder / f"{stamp}_proposals.csv"
    (plan.suggestions if table is None else table).to_csv(csv, index=False)
    record = {
        "goals": [{"name": o.name, "maximize": o.maximize, "log": o.log}
                  for o in plan.objectives],
        "variables": plan.variables,
        "bounds": {k: list(v) for k, v in plan.bounds.items()},
        "engine": plan.engine_name,
        "seed": plan.seed,
        "trained_on": plan.samples,
        **dict(settings or {}),
    }
    meta = folder / f"{stamp}_settings.json"
    meta.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    return csv, meta


__all__ = [
    "Engine", "GPEngine", "ENGINES", "register_engine", "list_engines",
    "make_engine", "to_model", "from_model", "snap",
    "Proposal", "propose", "propose_for",
    "CrossValidation", "cross_validate", "save_proposal",
]
