# Model artifacts

Trained models are copied here from `research/artifacts/<version>/` (model.joblib +
manifest.json). The gateway loads one at start-up only if the manifest SHA-256 matches
and the scikit-learn version is identical. Artifacts are git-ignored.
