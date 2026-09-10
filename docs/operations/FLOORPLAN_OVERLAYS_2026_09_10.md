# Floorplan overlay alignment

Updated Newark's `home-command` Floorplans and Londondale views against the
user-renamed 1400 x 1350 SVGs on 2026-09-10. SVGs and HA registries were not edited.

- First floor: repositioned Foyer, Family Room, Kitchen, Garage and Office
  occupancy, lighting, media and display-name overlays within their room bounds.
- Second floor: repositioned Master Bedroom, Master Bath and Upstairs Hall;
  moved Loft Ceiling from the open-to-below void into the labeled Loft room.
- Moved `media_player.master_fire_tv_stick` from the center bedroom into Master
  Bedroom, matching its live HA area. Corrected its caption from Theater device
  to Master Fire TV. Both Master media entities were unavailable at inspection;
  repositioning does not repair their connections.
- Removed the Master Bedroom sensor from the first-floor overview; it remains
  on the second-floor map and the existing room tile.
- Removed the unsupported Theater occupancy placement from Bedroom Kim. Kept
  `binary_sensor.theater_occupied` visible in a separate location-unconfirmed
  tile and asked the user for its room. No sensor or automation was deleted.
- Removed the stale Bedroom center label overlay from Bedroom Kim. Existing
  room-name dropdown helpers are preserved, without changing their values.

Verification: fresh-hash surgical API transform, post-write verification and
readback; desktop screenshot at 1000 x 3300 with a 10-second settle showed both
floorplans and all repositioned icons. No device actions or HA restart performed.
Mobile touch-target spacing was not separately validated.

## Final room and light corrections

- User confirmed center bedroom is Bedroom Kim and Theater occupancy refers to
  basement stairs. The separate tile now reads Basement stairs occupancy; the
  entity ID remains unchanged and is not placed on either floor's room map.
- Added Dining Room `light.tapo_smart_dimmer` at 49% left / 61% top. It was
  unavailable during verification.
- Living Room overlay now uses user-corrected `light.living_room2` at 19% left /
  63% top, replacing unavailable `light.living_room_ceiling_a`. Verified on and
  visually rendered with its active-state color. Both use more-info on tap.
- Versioned live views: `dashboard/londondale_floorplan_views.json`. These are
  two exported views, not a replacement for the entire Home Command dashboard.
  Use the managed API and a fresh config hash to merge them if restoring.
- Source SVGs: `dashboard/assets/01-floor-plan.svg` and `02-floor-plan.svg`.
  They are served from HA's `/config/www/` using the same filenames.
- Observation history copied from the parent workspace into
  `docs/operations/HOME_CONTEXT_OBSERVATION_LOG.md`. Historical findings are
  dated snapshots, not claims about today's live states.
