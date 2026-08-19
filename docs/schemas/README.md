# Accessory Probe schemas

The runtime-enforced, package-distributed v1 schemas are the canonical copies:

- [`accessory-probe-manifest-v1.schema.json`](../../src/sky_walker/accessory_probe/schemas/accessory-probe-manifest-v1.schema.json)
- [`accessory-probe-record-v1.schema.json`](../../src/sky_walker/accessory_probe/schemas/accessory-probe-record-v1.schema.json)

Keeping the schemas inside `sky_walker.accessory_probe` ensures an installed CLI validates the same contract that the repository tests publish.
