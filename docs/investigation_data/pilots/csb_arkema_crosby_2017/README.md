# CSB Arkema Crosby Staged Evidence Pilot

This pilot adds U.S. Chemical Safety Board investigation `2017-08-I-TX`, the Arkema Crosby chemical-plant fires during Hurricane Harvey, as a staged investigation episode.

The reasoning target is coupled infrastructure failure: a natural hazard degrades utilities and safeguards, hazardous material stability becomes time-dependent, evacuation changes the operational state, and later investigation evidence revises the causal model.

## Evidence chronology

| Release date | Fragment | Role |
| --- | --- | --- |
| 2017-08-31 | CSB statement initiating the Arkema investigation | context |
| 2017-11-15 | preliminary 2D accident animation | official reconstruction/finding |
| 2018-05-24 | CSB final-report release | final institutional finding |

The CSB incident page states that Hurricane Harvey flooding disabled refrigeration on August 29, evacuation followed the next day, warming peroxide trailers combusted on August 31, remaining trailers were intentionally ignited September 3, and the evacuation zone was lifted September 4. These are useful sequence facts, but that page does not provide trustworthy exact UTC timestamps for every event.

For that reason, the pilot does **not** populate `actual_timeline` with invented midnight times. Exact private timeline claims remain empty until artifact-level evidence supports timestamp precision.

## Staged reasoning objective

At the first cutoff, the agent receives only the CSB statement that an investigation was being initiated after explosions and that the agency would seek information on the process, chemicals, and emergency preparedness. This is deliberately weak contextual evidence.

At the November 2017 cutoff, a CSB preliminary visual reconstruction becomes available. The agent may use it to improve the dependency-failure model but must retain that it was produced during an ongoing investigation.

At the May 2018 cutoff, final CSB findings become available. The final report release states that flooding caused equipment failure, chemicals decomposed and burned, and the investigation found a significant lack of guidance for flood and severe-weather planning.

## Conservative temporal policy

Date-only evidence becomes available at **12:00Z on the following calendar day**. The regression suite checks the state immediately before and at every gate:

1. `2017-09-01T11:59:59Z`: no evidence;
2. `2017-09-01T12:00:00Z`: initial CSB statement only;
3. `2017-11-16T11:59:59Z`: initial statement only;
4. `2017-11-16T12:00:00Z`: preliminary animation added;
5. `2018-05-25T11:59:59Z`: pre-final evidence only;
6. `2018-05-25T12:00:00Z`: final institutional release added.

## Epistemic treatment

The August statement is `context`. The preliminary animation is `official_finding` because it is an agency reconstruction, not raw sensor or surveillance evidence. The final release is also `official_finding`.

`ground_truth_claims` remains empty. The final CSB conclusion is stored only in the private oracle as an institutional finding.

## Media, privacy, and precision policy

Only CSB-hosted metadata/landing-page locators are stored. The repository does not copy final-report bytes, executive-summary files, embedded video, captions, audio, frames, images, or named-person records.

The checked-in review record covers link-only use. Media acquisition and derived artifacts require a separate rights review.

The pilot also explicitly refuses false timestamp precision: calendar-date event facts are not converted into private exact timestamps merely to make a timeline look complete.

## Falsifiers

The pilot fails if:

- the November preliminary animation appears at the August/September cutoff;
- May 2018 final findings appear before the final-release gate;
- the initial CSB statement is mislabeled as a completed finding;
- the preliminary animation is treated as raw primary evidence;
- exact private event timestamps are invented from date-only incident-page chronology;
- any fragment lacks the checked-in review identifier;
- final-report or executive-summary bytes are checked into the pilot;
- final CSB conclusions leak into the public episode before release;
- the executable pilot drifts from the Gold-10 Arkema case identity, capability tags, or preliminary-animation date.

## Scientific status

This is an implementation/provenance pilot. It does not establish scientific qualification, frontier discrimination, or training readiness.

The next research layer should score whether an agent correctly identifies dependency chains such as flooding → utility/safeguard loss → temperature control degradation → hazardous-material instability, while calibrating uncertainty at each evidence stage.
