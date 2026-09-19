# KinoDEM v1

KinoDEM is the physical branch of the KinoFM experiment. It studies whether a mechanical draw can exhibit measurable, persistent physical bias.

## What v1 models

- 25 numbered particles.
- 2D circular rotating drum.
- Ball-ball rigid contact with restitution.
- Coulomb-like tangential friction.
- Contact with a moving rotating wall.
- Gravity and linear air drag.
- Monte Carlo perturbations of ball radius, mass, restitution, friction and drum angular velocity.
- A replaceable outlet/extraction score.

The current geometry and physical constants are **not measurements of the real Kino machine**. Therefore v1 is a simulator/calibration scaffold, not a validated predictor.

## Core invariant

Kino draws 14 of 25 balls. For any Monte Carlo batch where every simulation selects exactly 14 unique balls:

```
sum_i P(ball_i selected) = 14
P0 = 14 / 25 = 0.56
```

KinoDEM checks this invariant automatically.

## Run

Quick smoke test:

```bash
python kinodem_v1.py --runs 20 --mix-seconds 0.06 --outdir kinodem-results
```

More simulations:

```bash
python kinodem_v1.py --runs 1000 --mix-seconds 1.2 --dt 0.003 --omega 7.0 --outdir kinodem-results
```

Outputs:

- `kinodem_probabilities.csv`
- `kinodem_summary.json`

The probabilities are simulation inclusion frequencies, not claims about the next real Kino draw.

## Calibration roadmap

The extraction rule is intentionally isolated from the dynamics. A physically useful next version should replace assumed values using measured data:

1. Exact drum geometry and extraction port.
2. Actual rotation/agitation law versus time.
3. Diameter and mass of every numbered ball.
4. Ball-wall and ball-ball coefficients of restitution.
5. Friction/rolling resistance.
6. Airflow if the machine uses forced air; this would motivate CFD-DEM.
7. High-speed video reconstruction of pre-extraction positions/velocities.

Only after calibration should physical bias estimates be compared with the historical statistical module.

## Validation philosophy

A physical advantage must survive repeated Monte Carlo perturbations, parameter uncertainty, alternate initial conditions, sensitivity analysis, comparison against the symmetric 0.56 inclusion baseline, and out-of-sample historical validation when the corresponding machine configuration is known.

KinoDEM must not turn an arbitrary simulated asymmetry into a claimed real-world prediction.
