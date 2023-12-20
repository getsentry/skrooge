# skrooge
A quick and dirty kubernetes cost estimator

## Idea

In english:
```
Pod size: 2 cpu, 3GB RAM
Previous deployment: 32 cpu, 48GB RAM
New deployment: 64 cpu, 96GB RAM
Running on c2-standard-30 which have 30 cpu, 120GiB RAM, and cost $914/month
Up to 2 new instances to support +32 CPU, cost $1828 / month ($21,936 / year)
```

It would be nice to have a CLI tool which could do these calculations for us (and integrate with GCP pricing / instance APIs to get instance shapes and costs automatically)

```bash
$ kubecost --cpu 32 --mem 48 --instance c2-standard-30
c2-standard-30: 30 cpu, 120GiB RAM, $914/month
Limiting factor: CPU (ceil(32/30) = 2)
Cost: $1828 / month ($21,936 / year)
```
