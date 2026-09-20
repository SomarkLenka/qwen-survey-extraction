What the documents are

Each is an RRC directional-survey filing: a header page or two (company, well identity, references), then the station table spanning several pages, sometimes followed by plats or certification letters (no data — skip those). Formats vary by survey vendor (ProDirectional, LEAM, COMPASS, PathFinder…), but the station table is always the target.

What to extract per document

1. Well identity (for matching): API number as printed (8, 10, or 14 digits), well name/number, operator. We match on API and reject docs that don't identify the intended well, so capture this even when it only appears in a header or footer.
2. The full station table, every row, in document order. Per station:
  - MD (ft) — required
  - Inclination (degrees) — required
  - Azimuth (degrees) — required
  - TVD (ft) — strongly wanted (it's our independent error check)
  - N/S and E/W offsets (ft, signed) if printed
  - Grid Northing/Easting or lat/long if printed
3. Header metadata: north reference (Grid vs True), surface location coordinates if printed, survey tool type (MWD/Gyro), the From/To MD range, KB/RKB elevation, report date.
4. Provenance: source URL or document ID, and which pages the table came from.

Rules that matter more than they look

- Preserve minus signs and hemisphere labels exactly. A dropped "−" or an S read as N is the single worst error class — it mirrors the whole lateral. If a column is labeled S or W with positive numbers, keep it that way and note the label; don't "normalize."
- Don't skip, reorder, or interpolate rows, and keep the tie-in/zero row. MD must come out strictly increasing.
- No unit conversion — leave everything in usft/degrees as printed.
- If grid coordinates are extracted, they're useless without the datum and zone (TX is usually NAD27 State Plane, in usft) — capture that line from the header or skip grid coords in favor of the wellhead-relative offsets.
- When a packet holds multiple surveys (pilot hole + lateral, or plan + as-drilled), we want the as-drilled survey reaching the deepest MD; if unsure, extract all and label each with its From/To range — we'll pick.
- If a value is illegible, output it as null with a flag rather than guessing. We validate every well physically (MD monotonic, TVD vs inclination integration, terminus vs bottom-hole location), so a flagged gap is recoverable — a confident wrong digit is poison.

Output format

JSON per well (preferred):

{
  "api": "42-177-32508",
  "well_name": "BURROW 1H",
  "operator": "Paloma Resources LLC",
  "north_ref": "grid",
  "tool": "MWD",
  "source_url": "https://webapps.rrc.state.tx.us/dpimages/img/...",
  "table_pages": [3, 9],
  "stations": [
    {"md": 0, "inc": 0.0, "azm": 0.0, "tvd": 0.0, "ns_ft": 0.0, "ew_ft": 0.0},
    {"md": 200, "inc": 0.37, "azm": 181.34, "tvd": 200.0, "ns_ft": -0.65, "ew_ft": -0.02}
  ]
}

A flat CSV works too (one row per station, with api and source_url columns repeated). Either way I can write the loader — the schema above maps directly onto our trajectory pipeline, and every submission goes through the same validation gates our own extractions do, so nothing malformed can land.
