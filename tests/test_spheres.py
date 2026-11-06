"""The sphere kernels on synthetic curves with a known answer (no files)."""

import numpy as np
import pytest

from pyDataOrg.analysis import (
    fit_spheres, median_curve, sphere_amplitude, sphere_intensity,
    tabulated_profile,
)

Q = np.geomspace(0.006, 0.3, 900)                 # 1/Å


def solvent(q):
    """A solvent-and-cell background: a little low-q rise over a flat floor."""
    return 30.0 + 0.004 * q ** -1.5


def curve(radius=60.0, rel_sigma=0.1, *, scale=2000.0, background=1.0,
          power=0.0, noise=0.01, seed=0):
    rng = np.random.default_rng(seed)
    y = (scale * sphere_intensity(Q, radius, rel_sigma)
         + power * (Q / Q[0]) ** -3.0 + background * solvent(Q))
    return y * np.exp(rng.normal(0.0, noise, Q.size))


def test_the_amplitude_is_one_at_zero_and_vanishes_at_the_first_zero():
    assert sphere_amplitude(0.0) == pytest.approx(1.0)
    assert sphere_amplitude(1e-5) == pytest.approx(1.0)
    assert sphere_amplitude(4.4934) == pytest.approx(0.0, abs=1e-4)


def test_a_spread_of_radii_fills_the_minima_and_keeps_the_forward_value():
    sharp = sphere_intensity(Q, 50.0, 0.0)
    smeared = sphere_intensity(Q, 50.0, 0.15)
    first_zero = np.argmin(np.abs(Q * 50.0 - 4.4934))
    assert sphere_intensity([1e-6], 50.0, 0.15)[0] == pytest.approx(1.0)
    assert sharp[0] == pytest.approx(1 - (Q[0] * 50.0) ** 2 / 5, rel=1e-3)
    assert smeared[first_zero] > 100 * sharp[first_zero]


def test_a_tabulated_sphere_is_the_sphere():
    """A shape's profile from a table stands in for the sphere's: the
    sphere's own, tabulated, gives the sphere's intensity back; beyond the
    table it falls as Porod's x^-4, below it it is 1."""
    x = np.geomspace(1e-2, 300.0, 3000)
    table = tabulated_profile(x, 7.0 * sphere_amplitude(x) ** 2 + 1e-30)
    smeared = sphere_intensity(Q, 50.0, 0.15)
    assert sphere_intensity(Q, 50.0, 0.15, profile=table) == pytest.approx(
        smeared, rel=2e-3)
    assert table(np.array([1e-4]))[0] == 1.0
    far = table(np.array([600.0, 1200.0]))
    assert far[0] / far[1] == pytest.approx(16.0)
    assert far[0] == pytest.approx(9.0 / 600.0 ** 4 / 2, rel=0.1)   # ⟨F²⟩ ≈ 9/(2x⁴)
    with pytest.raises(ValueError, match="increasing"):
        tabulated_profile(x[::-1], x)


def test_another_shape_is_fitted_as_the_sphere_is():
    """A cube (its ⟨F²⟩ averaged over orientations, tabulated) is fitted by
    the same fit with its profile — and the size found is the cube's."""
    x = np.geomspace(1e-2, 300.0, 1500)
    k = np.random.default_rng(1).normal(size=(4000, 3))
    k /= np.linalg.norm(k, axis=1, keepdims=True)
    p = np.mean(np.prod(np.sinc(np.outer(x, k.ravel()).reshape(len(x), -1, 3)
                                / np.pi), axis=2) ** 2, axis=1)
    cube = tabulated_profile(x, p)
    rng = np.random.default_rng(0)
    y = (2000.0 * sphere_intensity(Q, 40.0, 0.1, profile=cube) + solvent(Q)) \
        * np.exp(rng.normal(0.0, 0.01, Q.size))
    fit = fit_spheres(Q, y, solvent(Q), q_min=0.007, q_max=0.25, profile=cube)
    assert fit.radius == pytest.approx(40.0, rel=0.02)
    assert fit.rel_sigma == pytest.approx(0.1, abs=0.02)
    as_spheres = fit_spheres(Q, y, solvent(Q), q_min=0.007, q_max=0.25)
    assert as_spheres.rms > 1.5 * fit.rms


def test_the_radius_must_be_positive():
    with pytest.raises(ValueError, match="positive"):
        sphere_intensity(Q, 0.0)


def test_the_fit_finds_the_radius_spread_and_background_put_in():
    fit = fit_spheres(Q, curve(60.0, 0.1, background=1.1), solvent(Q),
                      q_min=0.007, q_max=0.25)
    assert fit.radius == pytest.approx(60.0, rel=0.02)
    assert fit.rel_sigma == pytest.approx(0.1, abs=0.02)
    assert fit.background_scale == pytest.approx(1.1, rel=0.03)
    assert fit.diameter == pytest.approx(2 * fit.radius)
    assert 0 < fit.radius_err < 3.0
    assert fit.rms < 0.02
    assert not fit.notes


def test_the_fit_says_what_it_fitted_within_which_bounds():
    fit = fit_spheres(Q, curve(60.0, 0.1), solvent(Q), q_min=0.007,
                      q_max=0.25, radius_bounds=(10.0, 400.0), max_rel_sigma=0.3)
    assert fit.free == ("scale", "radius", "rel_sigma", "power_amplitude",
                        "power_exponent", "background_scale")
    assert set(fit.errors) == set(fit.bounds) == set(fit.free)
    assert fit.bounds["radius"] == (10.0, 400.0)
    assert fit.bounds["rel_sigma"] == (0.01, 0.3)
    assert fit.errors["radius"] == pytest.approx(fit.radius_err)
    held = fit_spheres(Q, curve(60.0, 0.1), solvent(Q), q_min=0.007,
                       q_max=0.25, power_law=False, background_bounds=(1, 1))
    assert held.free == ("scale", "radius", "rel_sigma")
    assert held.background_scale == 1.0


def test_a_low_q_rise_goes_to_the_power_law_not_to_the_radius():
    fit = fit_spheres(Q, curve(45.0, 0.12, power=300.0), solvent(Q),
                      q_min=0.007, q_max=0.25)
    assert fit.radius == pytest.approx(45.0, rel=0.03)
    assert fit.power_exponent == pytest.approx(3.0, abs=0.5)
    assert fit.power_share > 0.05
    plain = fit_spheres(Q, curve(45.0, 0.12, power=300.0), solvent(Q),
                        q_min=0.007, q_max=0.25, power_law=False)
    assert plain.rms > fit.rms


def test_large_spheres_are_found_from_many_starts():
    fit = fit_spheres(Q, curve(220.0, 0.15, scale=5e4), solvent(Q),
                      q_min=0.007, q_max=0.2)
    assert fit.radius == pytest.approx(220.0, rel=0.05)


def test_one_start_is_enough_near_the_answer():
    fit = fit_spheres(Q, curve(60.0, 0.1), solvent(Q), q_min=0.007,
                      q_max=0.25, radius_start=55.0)
    assert fit.radius == pytest.approx(60.0, rel=0.02)


def test_a_fit_set_by_hand_starts_holds_and_bounds_as_told():
    """Where the fit starts, which parameters are held and where each may
    go, by name; every one held is the model at those values, not a fit."""
    y = curve(radius=60.0, rel_sigma=0.1, power=5.0)
    free = fit_spheres(Q, y, solvent(Q))
    held = fit_spheres(Q, y, solvent(Q), fixed={"rel_sigma": 0.2},
                       start={"radius": 50.0})
    assert held.rel_sigma == 0.2 and held.held == {"rel_sigma": 0.2}
    assert "rel_sigma" not in held.free and np.isnan(held.rel_sigma_err)
    assert held.rms > free.rms                            # held off its best
    bounded = fit_spheres(Q, y, solvent(Q), bounds={"radius": (30.0, 45.0)})
    assert bounded.radius == pytest.approx(45.0, rel=1e-3)
    assert "radius" in bounded.at_bound and bounded.bounds["radius"] == (30.0, 45.0)

    values = {n: getattr(free, n) for n in ("scale", "radius", "rel_sigma",
                                            "power_amplitude", "power_exponent",
                                            "background_scale")}
    model = fit_spheres(Q, y, solvent(Q), fixed=values)
    assert model.free == () and model.rms == pytest.approx(free.rms, rel=1e-6)
    assert model.model == pytest.approx(free.model)
    with pytest.raises(ValueError, match="no parameter 'diameter'"):
        fit_spheres(Q, y, solvent(Q), start={"diameter": 100.0})
    with pytest.raises(ValueError, match="low bound"):
        fit_spheres(Q, y, solvent(Q), bounds={"radius": (50.0, 40.0)})


def test_a_background_held_as_measured_is_said_to_be_held():
    fit = fit_spheres(Q, curve(), solvent(Q), background_bounds=(1.0, 1.0))
    assert fit.held == {"background_scale": 1.0} and fit.background_scale == 1.0


def test_without_a_background_a_constant_can_take_its_place():
    y = 2000.0 * sphere_intensity(Q, 60.0, 0.1) + 30.0
    fit = fit_spheres(Q, y, q_min=0.007, q_max=0.25, constant=True,
                      power_law=False)
    assert fit.radius == pytest.approx(60.0, rel=0.02)
    assert fit.constant == pytest.approx(30.0, rel=0.05)


def test_a_bound_reached_and_a_faint_sample_are_said():
    faint = fit_spheres(Q, curve(60.0, 0.1, scale=10.0), solvent(Q),
                        q_min=0.007, q_max=0.25)
    assert any("its background" in n for n in faint.notes)
    two = (curve(30.0, 0.05, scale=500.0, background=0.0, noise=0.0)
           + curve(150.0, 0.05, scale=2e4, background=1.0, noise=0.0))
    fit = fit_spheres(Q, two, solvent(Q), q_min=0.007, q_max=0.25,
                      max_rel_sigma=0.2, power_law=False)
    assert fit.at_bound and fit.notes


def test_too_few_points_in_the_window_is_an_error():
    with pytest.raises(ValueError, match="usable points"):
        fit_spheres(Q, curve(), solvent(Q), q_min=0.25, q_max=0.26)


def test_the_median_curve_ignores_one_bad_curve_and_shares_the_first_x():
    x = np.linspace(0, 1, 11)
    good = 2 * x + 1
    x2 = np.linspace(-0.05, 1.05, 23)
    q, y = median_curve([x, x2, x], [good, 2 * x2 + 1, np.zeros_like(x)])
    assert np.array_equal(q, x)
    assert y == pytest.approx(good)
    q, y = median_curve([x, x + 0.5], [good, good])
    assert np.isfinite(y).all()                   # one curve still counts
    with pytest.raises(ValueError):
        median_curve([x], [good, good])
