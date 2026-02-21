# snapchat-memories-export-processor
Combines the main and overlay files from a Snapchat Memories export

This script combines the main files (images or videos) with their respective overlay files you get from a Snapchat Memories export.

# Usage
1. Extract the .zip file(s) from Snapchat. Each memory with an overlay should have a separate subdirectory containing the base image or video and the overlay.
1. [Install uv](https://docs.astral.sh/uv/getting-started/installation/), if you have not already.
1. Open a terminal in the repo directory and run the script with `uv run process_memories.py <path to memories directory>`
1. All base files that had overlays will be placed in a `base/` folder. All files (those that didn't have overlays _and_ those that did) are combined and placed in `output/`.

# Development
This repo leverages [pre-commit](https://pre-commit.com). To install the pre-commit hooks, run `pre-commit install`. Before making contributions, install and run pre-commit.
