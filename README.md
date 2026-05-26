# Verus-SpecGym in Harbor

This repository is a fork of the [Harbor agentic evaluation framework](https://github.com/harbor-framework/harbor) configured to run
**Verus-SpecGym**, a specification autoformalization benchmark for Verus/Rust.

Verus-SpecGym tasks are distributed as Harbor task directories. The helper scripts for downloading the task zips, extracting them, adding current Harbor task metadata, running sample jobs, and summarizing logs live in the [Verus-SpecGym helper scripts README](verus_spec_gym_specific_scripts/README.md). The linked README should have all details to run the benchmark.

The Harbor-format task zips are available [at this Google Drive link](https://drive.google.com/drive/folders/13OsxAM7t5xTnuqRoyVdMIApNuCJA4SyP).

The public dashboard for inspecting sample trajectories is available at [https://formal-verif-is-cool.github.io/](https://formal-verif-is-cool.github.io/).

The evaluator package, which is already installed in the evaluation container, is [available here](https://github.com/formal-verif-is-cool/anonymous_code/tree/main/verus_gym_package).

For the Harbor framework documentation, see [README_FOR_HARBOR.md](README_FOR_HARBOR.md), which is the README derived from their original repository.

For any questions, please reach out at [anmolagarwal4453@gmail.com](mailto:anmolagarwal4453@gmail.com).
