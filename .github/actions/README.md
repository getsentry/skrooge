# Skrooge GitHub Actions

This directory contains reusable GitHub Actions for running skrooge cost estimation and automatically commenting results on pull requests.

## Available Actions

### 1. skrooge-comment

A simple action that runs skrooge with provided parameters and comments the output on PRs.

**Usage in other repositories:**

```yaml
name: Cost Estimation
on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  estimate:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Run skrooge cost estimation
        uses: getsentry/skrooge/.github/actions/skrooge-comment@main
        with:
          replicas: '5'
          cpu: '2000'
          mem: '4096'
          instance: 'c2-standard-30'
          cost-class: 'sud'
          region: 'us-central1'
          format: 'english'
          github-token: ${{ secrets.GITHUB_TOKEN }}
          comment-prefix: '## 💰 Deployment Cost Estimate'
```

**Inputs:**
- `replicas` (optional): Number of replicas in the deployment (default: '1')
- `cpu` (optional): CPU change in milli-cores (default: '0')
- `mem` (optional): Memory change in MiB (default: '0')
- `instance` (required): Instance type this deployment is running on
- `cost-class` (optional): Type of cost to calculate (default: 'sud')
- `region` (optional): Region to use for cost calculation (default: 'us-central1')
- `format` (optional): Output format - 'english' or 'json' (default: 'english')
- `github-token` (required): GitHub token for commenting on PRs
- `comment-prefix` (optional): Prefix for the comment (default: '## 💰 Skrooge Cost Estimate')

### 2. skrooge-k8s-parser

An advanced action that automatically parses Kubernetes manifests to extract resource requirements and runs skrooge cost estimation.

**Usage in other repositories:**

```yaml
name: K8s Cost Analysis
on:
  pull_request:
    types: [opened, synchronize, reopened]
    paths:
      - '**/deployment.yaml'
      - '**/deployment.yml'
      - '**/statefulset.yaml'
      - '**/statefulset.yml'

jobs:
  analyze:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Analyze Kubernetes manifests and estimate costs
        uses: getsentry/skrooge/.github/actions/skrooge-k8s-parser@main
        with:
          manifest-path: '.'
          instance: 'c2-standard-30'
          cost-class: 'sud'
          region: 'us-central1'
          format: 'english'
          github-token: ${{ secrets.GITHUB_TOKEN }}
          comment-prefix: '## 💰 Kubernetes Cost Analysis'
```

**Inputs:**
- `manifest-path` (optional): Path to Kubernetes manifest file(s) (default: '.')
- `instance` (required): Instance type this deployment is running on
- `cost-class` (optional): Type of cost to calculate (default: 'sud')
- `region` (optional): Region to use for cost calculation (default: 'us-central1')
- `format` (optional): Output format - 'english' or 'json' (default: 'english')
- `github-token` (required): GitHub token for commenting on PRs
- `comment-prefix` (optional): Prefix for the comment (default: '## 💰 Kubernetes Cost Analysis')

### 3. skrooge-diff-analyzer

A specialized action for large Kubernetes manifest repositories that analyzes only the changed files in a PR and provides before/after cost comparisons.

**Perfect for repositories with large `k8s/materialized_manifests` directories.**

**Usage in other repositories:**

```yaml
name: Skrooge Diff Analysis
on:
  pull_request:
    types: [opened, synchronize, reopened]
    paths:
      - "k8s/materialized_manifests/**/*.yaml"
      - "k8s/materialized_manifests/**/*.yml"

jobs:
  analyze-cost-impact:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write

    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Needed for git diff analysis

      - name: Analyze cost impact of changes
        uses: mwarkentin/skrooge/.github/actions/skrooge-diff-analyzer@main
        with:
          manifest-path: "k8s/materialized_manifests"
          instance: "c2-standard-30"
          cost-class: "sud"
          region: "us-central1"
          format: "english"
          github-token: ${{ secrets.GITHUB_TOKEN }}
          comment-prefix: "## 💰 Kubernetes Cost Impact Analysis"
```

**Inputs:**
- `manifest-path` (optional): Path to Kubernetes manifest directory (default: 'k8s/materialized_manifests')
- `instance` (required): Instance type this deployment is running on
- `cost-class` (optional): Type of cost to calculate (default: 'sud')
- `region` (optional): Region to use for cost calculation (default: 'us-central1')
- `format` (optional): Output format - 'english' or 'json' (default: 'english')
- `github-token` (required): GitHub token for commenting on PRs
- `comment-prefix` (optional): Prefix for the comment (default: '## 💰 Kubernetes Cost Impact Analysis')

## Supported Kubernetes Resources

The `skrooge-k8s-parser` action currently supports:

- **Deployments**: Extracts replicas, CPU, and memory requests from all containers
- **StatefulSets**: Extracts replicas, CPU, and memory requests from all containers

## Cost Classes

Available cost classes for GCP instances:
- `sud`: Sustained Use Discount (default)
- `ondemand`: On-demand pricing
- `preemptible`: Preemptible instances
- `cud-1y`: 1-year Committed Use Discount
- `cud-3y`: 3-year Committed Use Discount

## Regions

The actions support all major GCP regions. Default is `us-central1`.

## Special Features

### Diff Analysis for Large Repositories

The `skrooge-diff-analyzer` action is specifically designed for repositories with large Kubernetes manifest directories:

- **Smart File Detection**: Only analyzes `deployment.yaml` files that have actually changed
- **Before/After Comparison**: Compares resource requirements before and after changes
- **Cost Impact Analysis**: Shows the actual cost difference, not just total costs
- **Git Integration**: Uses git diff to identify changed files between branches/commits
- **Efficient Processing**: Skips unchanged files to avoid unnecessary computation

### Example Diff Analysis Output

```
## 💰 Kubernetes Cost Impact Analysis

**📈 Changes Detected:**
- **Files Modified:** 2 deployment manifest(s)
- **CPU Change:** +2000m (2.0 cores)
- **Memory Change:** +4096Mi (4.0 GiB)
- **Replica Change:** +1

**💰 Cost Impact:**

**Before Changes:**
```
This workload is running on c2-standard-30 instances in us-central1 with 30 cores and 120GiB of memory.
This workload will require 3.0 cores and 4.0 GiB of memory. This workload is cores-constrained.
This workload will require 1 instances, costing $0.125/h (or $91.40/m (or $1096.80/y)) at sud rates.
```

**After Changes:**
```
This workload is running on c2-standard-30 instances in us-central1 with 30 cores and 120GiB of memory.
This workload will require 5.0 cores and 8.0 GiB of memory. This workload is cores-constrained.
This workload will require 1 instances, costing $0.208/h (or $152.33/m (or $1828.00/y)) at sud rates.
```

*Generated by skrooge - A Kubernetes cost estimator*
```

## Example Output

The actions will comment on PRs with output like:

```
## 💰 Kubernetes Cost Analysis

**Resources Detected:**
```
CPU: 5000m, Memory: 8192Mi, Replicas: 5
```

**Cost Estimate:**
```
This workload is running on c2-standard-30 instances in us-central1 with 30 cores and 120GiB of memory.
This workload will require 5.0 cores and 8.0 GiB of memory. This workload is cores-constrained.
This workload will require 1 instances, costing $0.125/h (or $91.40/m (or $1096.80/y)) at sud rates.
```

*Generated by skrooge - A Kubernetes cost estimator*
```

## Requirements

- Python 3.8+
- GitHub Actions permissions for pull request comments
- Valid GCP instance type name
