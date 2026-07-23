# Backlog

This document outlines **ideas and potential next steps** that are not built yet, grouped roughly by theme. This is a parking lot rather than a commitment: it exists to collect good ideas and to show repo-viewers where GridGPT could go next. What has already shipped is described in the [README](../README.md) and measured in the [evaluation notes](evaluation.md).

## Puzzle quality and themes

The strict limit on how themed a 5x5 can get is the **raw material**, not the algorithm: a 5x5 needs 3-to-5-letter words, and a ~10k-word database simply does not hold many short words strongly tied to a given theme (see [evaluation](evaluation.md) sections 2 and 3). To directly address this:

- **Expand the word database with more sources.** More short, common answers means more genuinely on-theme options to draw from. A second scraper already exists for `crosswordtracker.com` but its output is not yet integrated. Other sources may be considered as well.
- **Curated theme / category tagging.** Tag database words with categories so "on-theme" becomes a verified lookup instead of a similarity guess. Slow to build (manual data work) but it removes the noise that cosine similarity cannot avoid.
- **Re-tune the similarity band for the large embedding model.** `sim_low` / `sim_high` in `conf/base/parameters.yml` were calibrated for `text-embedding-3-small` and were left unchanged when the default moved to `text-embedding-3-large`. A light sweep would confirm or improve them.

## Bigger grids

- **7x7 and up / Midi crossword style.** More slots and longer entries, and longer words tend to be more distinctive and easier to relate to a theme, so this would raise the theme ceiling as a side effect. Needs new templates plus generalising the frontend's hardcoded 5x5 assumptions (`grid-cols-5`, `Math.min(4, ...)`).
- **User-defined grid templates.** Let a solver lay out their own black squares rather than picking from the three built-in patterns. Depends on the same frontend generalisation as above, plus validation that the resulting grid is actually fillable.

## Gameplay and UX

- **Difficulty setting.** A frequency threshold for word obscurity plus a difficulty-conditioned clue prompt. Scaffolding already exists end to end (request field, template metadata, commented-out UI).
- **Shareable puzzles.** Seed the random number generator per puzzle and encode the seed plus parameters in a URL. Gives reproducible puzzles, shareable links, and reproducible bug reports, which pairs naturally with the deliberate randomness in anchor selection.
- **Streaming progress.** Server-sent events from the backend, replacing the rotating loading messages that are currently on a timer and unrelated to real progress.
- **Solver niceties.** Timer (NYT mini style), dark mode, print view.

## Architecture and code

- **A single crossword orchestrator.** `CrosswordGenerator` is really a grid filler, and the API route currently does the orchestration (theme scoring, anchor selection, generation, clues). Renaming it and introducing one orchestrator that takes the frontend inputs and returns a finished crossword would make the pipeline readable in one place and keep the route thin.
- **Multi-provider LLM support.** Turn `LLMConnection` into a small interface with per-provider implementations, so the clue and theme-anchor calls are not tied to one vendor.
- **Frontend de-duplication.** The across and down clue blocks are near-identical and could be one `ClueList` component, and the Tab handler and `navigateToSlot` could share a single navigation helper.
