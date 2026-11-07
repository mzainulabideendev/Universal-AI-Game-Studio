# V5 LLM evaluation results

Generated: 2026-11-07T05:36:54+00:00

- Mode: `pipeline`
- Source: `deterministic-fallback`
- Live provider: `False`
- Provider/model: `None` / `None`
- Cases: 22
- Mean score: 0.957

## Component means

| Component | Mean |
| --- | --- |
| genre_recall | 1.0 |
| genre_precision | 1.0 |
| dimension | 0.944 |
| keyword_recall | 0.939 |
| exclusion_recall | 1.0 |
| technical | 1.0 |
| engine | 1.0 |
| clarification | 0.706 |
| structure | 1.0 |
| conflict | 1.0 |
| non_hallucination | 1.0 |

## Per-case results

| ID | Category | Overall | Genres | Requirements | Questions | Gap |
| --- | --- | --- | --- | --- | --- | --- |
| EV-01 | 2d-platformer | 0.944 | platformer | 18 | 3 |  |
| EV-02 | 3d-endless-runner | 0.857 | - | 13 | 2 | yes |
| EV-03 | open-world-adventure | 1.0 | open-world, adventure | 28 | 2 |  |
| EV-04 | fighting | 0.944 | fighting | 18 | 4 |  |
| EV-05 | chess | 0.929 | - | 16 | 4 | yes |
| EV-06 | survival | 0.907 | survival | 19 | 3 |  |
| EV-07 | racing | 1.0 | racing | 22 | 2 |  |
| EV-08 | multiplayer-shooter | 0.944 | shooter | 21 | 4 |  |
| EV-09 | simulation | 0.944 | simulation | 15 | 3 |  |
| EV-10 | mobile-casual | 0.75 | - | 12 | 3 | yes |
| EV-11 | roman-urdu-adventure | 1.0 | adventure | 21 | 3 |  |
| EV-12 | roman-urdu-racing | 1.0 | racing | 20 | 3 |  |
| EV-13 | urdu-platformer | 1.0 | platformer | 18 | 3 |  |
| EV-14 | mixed-urdu-english | 1.0 | adventure | 21 | 2 |  |
| EV-15 | explicit-exclusions | 0.944 | horror, survival | 23 | 3 |  |
| EV-16 | conflicting-requirements | 1.0 | racing | 23 | 2 |  |
| EV-17 | ambiguous-tiny | 1.0 | - | 10 | 4 |  |
| EV-18 | ambiguous-scope | 1.0 | - | 10 | 4 |  |
| EV-19 | sports | 1.0 | sports | 14 | 2 |  |
| EV-20 | strategy | 0.944 | strategy | 15 | 3 |  |
| EV-21 | puzzle | 0.938 | puzzle | 13 | 3 |  |
| EV-22 | tower-defense | 1.0 | tower-defense | 17 | 2 |  |

## Capability gaps

- **EV-02** (3d-endless-runner): The deterministic lexicon has no 'endless runner' genre; only collectibles and dimension are expected to be found.
- **EV-05** (chess): Chess is not a lexicon genre; the parser cannot name the genre from vocabulary.
- **EV-10** (mobile-casual): Casual/stacking games are not represented in the lexicon.

## Cases below 0.75

- None.

## Exclusion leaks

- None.

## Interpretation

These scores measure the path that actually ran. When `live` is false and
`source` is `deterministic-fallback`, they describe the offline vocabulary
parser, not an LLM. They must not be cited as model-quality evidence.
