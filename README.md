# Irabelle Parcels

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=notf0und&repository=irabelle-parcels&category=integration)

A Home Assistant integration that tracks your packages from almost any carrier worldwide. The carrier is detected automatically. No API key, no account, no registration.

Delivered parcels move to an **archive** instead of being deleted: they disappear from your dashboard but keep their full history, and you can track them again with one tap. Two Lovelace cards come with the integration, so no extra frontend resource to install.

## Installation

1. Click the button above, or in HACS add `https://github.com/notf0und/irabelle-parcels` as a custom repository (type *Integration*), then download **Irabelle Parcels**.
2. Restart Home Assistant.
3. **Settings → Devices & services → Add integration → Irabelle Parcels**.
4. Choose your destination country, an optional postal code (some carriers give better delivery estimates with it), the polling frequency, and how long a delivered parcel stays active before it is archived (`0` = never archive automatically).

## Cards

The cards are loaded automatically. Find them in the card picker by searching for "Irabelle Parcels".

### Parcels card

```yaml
type: custom:irabelle-parcels-card
title: Parcels
```

- **Active** and **Archive** tabs, with counts. The archive is searchable once it has more than a few parcels.
- Each parcel shows its status, last event, how long ago it happened, and the expected delivery day. Tap it to see the carrier (linked to the carrier's own tracking page), route, days in transit and the event timeline, plus actions: **Archive** / **Track again**, **Rename**, **History** (the sensor's more-info dialog), **Delete**.
- The **+** button opens an add form with paste-from-clipboard buttons for the tracking number and the name.
- **Clear archive** deletes every archived parcel for good, after you confirm.

| Option | Default | Description |
| --- | --- | --- |
| `title` | `Parcels` | Card title |
| `show_add` | `true` | Show the **+** button and add form |
| `show_archive` | `true` | Show the Archive tab |
| `hide_if_empty` | `false` | Hide the whole card when nothing is on the way |
| `max_events` | `3` | Events shown before "Show all" |

### Chips card

```yaml
type: custom:irabelle-parcels-chips-card
```

One chip per active parcel, coloured by status, with the expected delivery day. Tapping a chip opens a popup with the parcel's details, timeline and actions. **When nothing is on the way, the card is hidden entirely**: no empty box, and sections and stacks close up around it. It stays visible while you edit the dashboard.

| Option | Default | Description |
| --- | --- | --- |
| `show_eta` | `true` | Show the expected delivery day on each chip |
| `max_events` | `5` | Events shown in the popup before "Show all" |

## Entities

One sensor per **active** parcel (archived parcels have no sensor and are not polled):

- State: `transit`, `arrived`, `pickup`, `delivered`, `cancelled`, `returned`, `no_data` or `error`.
- Attributes: `tracking_number`, `carrier`, `status_text`, `last_update`, `origin`, `destination`, `expected_delivery`, `days_in_transit`, `related_tracking_ids`, `tracking_url` and `statuses` (the event history; it is not written to the recorder database).

Event times are the destination's local time, as the carriers report them (the service labels them UTC; the cards show them as they are).

## Archive

A parcel is archived automatically once it has been **delivered** for longer than the configured time (default 2 days; change it in **Configure → Settings**). You can also archive any parcel by hand. Archived parcels:

- keep their last tracking data and full event history, shown in the card's Archive tab;
- are not polled and have no sensor, so they drop out of any card or automation that lists the sensors;
- come back with **Track again** in the card, the `unarchive_parcel` action, or by adding the same tracking number again.

## Actions

| Action | Fields | Description |
| --- | --- | --- |
| `irabelle_parcels.add_parcel` | `tracking_number`, `name` (optional), `carrier` (optional, default `Auto Detect`) | Start tracking a parcel. Returns `tracking_number` (normalised) as response data. Adding an archived parcel restores it. |
| `irabelle_parcels.update_parcel` | `tracking_number`, `name`, `carrier` | Rename a parcel and/or change its carrier. |
| `irabelle_parcels.archive_parcel` | `tracking_number` | Stop tracking a parcel and archive it. |
| `irabelle_parcels.unarchive_parcel` | `tracking_number` | Track an archived parcel again. |
| `irabelle_parcels.remove_parcel` | `tracking_number` | Delete a parcel (active or archived) for good. |
| `irabelle_parcels.clear_archive` | | Delete every archived parcel. Returns `removed` (count). |

```yaml
action: irabelle_parcels.add_parcel
data:
  tracking_number: SYNZ011162148
  name: LIR2032 batteries
```

## Events

`irabelle_parcels_event` fires whenever an active parcel gets a new tracking event, with `tracking_number`, `name`, `carrier`, `carrier_slug`, `status_text`, `last_update` and `state`. Most new events (e.g. "Arrived at hub") don't change the sensor state, so use this event for announcements:

```yaml
alias: Parcels - announce new events
triggers:
  - trigger: event
    event_type: irabelle_parcels_event
conditions:
  - condition: time
    after: "08:00:00"
    before: "22:00:00"
actions:
  - action: notify.notify
    data:
      message: "New update for {{ trigger.event.data.name }}: {{ trigger.event.data.status_text }}"
```

To list the parcels currently on the way in a template: `{{ integration_entities('irabelle_parcels') }}`.

## How it works

The integration calls a public mobile tracking API with an app-like device fingerprint. That fingerprint is generated once and kept, because the service caches results per fingerprint. **Configure → Device fingerprint** can override it with a real app install's values (Android ID and so on).
