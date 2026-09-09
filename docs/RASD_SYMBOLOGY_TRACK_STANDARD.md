# RASD Symbology & Track Standard v1

## Purpose
This document defines the RASD baseline for track lifecycle, identity evidence, confidence, affiliation, and APP-6E-ready symbology. It is a data and interoperability standard, not an engagement or weapon-control specification.

## Core separation
RASD must keep the following concerns separate:

1. **Track state**: whether an object is tentative, confirmed, actively tracked, stale, lost, or archived.
2. **Entity type**: what the tracked object is believed to be (aircraft, vessel, vehicle, person, unit, site, unknown).
3. **Affiliation**: the current identity/affiliation assessment.
4. **Risk**: the operational attention level.
5. **Data state**: freshness of observations.
6. **Symbology**: standardized rendering metadata (APP-6E-ready SIDC and related fields).

`UNKNOWN` and `SUSPECT` must never be treated as `HOSTILE` automatically.

## Processing flow

```text
Provider / Sensor / Internal Asset Feed
                ↓
             RawEvent
                ↓
            Observation
                ↓
        Validation & Quality
                ↓
          Track Association
                ↓
       Track Create / Update
                ↓
         Entity Resolution
                ↓
      Identity Evidence Fusion
                ↓
       Affiliation + Confidence
                ↓
      APP-6E Classification/SIDC
                ↓
       Geofence / Rule Engine
                ↓
        Risk / Alert Workflow
```

## Track lifecycle

```text
TENTATIVE → CONFIRMED → TRACKING → IDENTIFIED
                  ↓          ↓
                STALE      STALE
                  ↓          ↓
                 LOST → ARCHIVED
```

A single transient measurement should not normally create a confirmed operational track. Confirmation policy is provider-specific and based on observation consistency and data quality.

## Affiliation states
RASD stores the detailed affiliation result separately from risk:

- `PENDING`
- `UNKNOWN`
- `ASSUMED_FRIEND`
- `FRIEND`
- `NEUTRAL`
- `SUSPECT`
- `HOSTILE`

The UI may expose a simplified view, but the database keeps the detailed state.

## Confidence model
RASD does not use one generic confidence value. A track maintains at least:

- Track confidence
- Position confidence
- Identity confidence
- Affiliation confidence
- Source confidence

All values are normalized to 0–100 in the Odoo model. Each identity decision should be explainable from linked evidence records.

## Identity evidence
Evidence is stored as first-class data and may come from:

- Internal asset registry
- Trusted identifier
- Declared identifier
- Sensor correlation
- Operator verification
- External feed
- Other approved source

Every evidence item contains source reference, time, confidence, optional supported affiliation, conflict state, and details.

## APP-6E-ready symbology
RASD stores a 20-character numeric SIDC when an approved APP-6E-compatible symbol dictionary/renderer is available. The code is not generated from ad-hoc icon filenames.

The data model preserves these logical components:

```text
Version / Context / Affiliation / Symbol Set / Status
HQ-TF-Dummy / Amplifier / Entity / Modifier 1 / Modifier 2
```

Detailed symbol dictionaries should be provided through an authorized dataset or renderer and should not be hard-coded into operational logic.

## Track / sensor separation
A tracked entity is the object being observed. A sensor or data source is an observation tool. They must not be modeled as the same object merely because both appear on the map.

Examples:
- Aircraft, vessel, vehicle: normally tracked entities.
- Radar, camera, ADS-B receiver, AIS station: normally assets/providers/sensors.
- A satellite may be represented as a track only when the satellite itself is the object being tracked; otherwise it is a source/asset.

## Geofence rules
Zone entry/exit operates on track position and time. Geofence state must use hysteresis/debounce so measurement noise near a boundary does not produce repeated enter/exit events.

A zone event changes neither affiliation nor identity by itself. It is evidence for a rule/risk evaluation only.

## Risk
Risk is independent of affiliation:

- `NORMAL`
- `WATCH`
- `WARNING`
- `CRITICAL`

Example: a friendly asset with stale telemetry may be `FRIEND + WARNING`; an unknown object moving normally may remain `UNKNOWN + NORMAL`.

## Freshness
Data freshness states:

- `LIVE`
- `DELAYED`
- `STALE`
- `LOST`

Provider-specific freshness thresholds belong in provider configuration, not in the global track model.

## Auditability
Changes to identity, affiliation, risk, classification, and important track state must be attributable to source evidence, operator, or rule version. Raw observations must remain available for reconstruction and replay.

## Odoo implementation introduced in this change

- `rasd.symbology.standard`
- `rasd.track`
- `rasd.identity.evidence`
- APP-6E standard seed record
- 20-digit SIDC validation
- separate track/risk/data lifecycle fields
- separate confidence dimensions
- evidence linkage and conflict indicator

## Next integration work
The existing RASD gateway/RawEvent/provider pipeline, when present in the deployment repository, should write normalized observations into this track layer. UI rendering should consume `rasd.track` and a dedicated symbology renderer rather than embedding classification decisions in JavaScript map components.
