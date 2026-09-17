import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak

PERIOD_LABELS = {
    '1h': 'Last 1 hour',
    '6h': 'Last 6 hours',
    '24h': 'Last 24 hours',
    '7d': 'Last 7 days',
}

# veryimp.pdf visual agreement
BLUE = '#0056b3'
DARK_GREEN = '#123832'
DARK_GRAY = '#343a40'
NORMAL_BLUE = '#2f80ed'
PEAK_RED = '#dc3545'
GRID = '#dee2e6'
LIGHT_BLUE = '#eaf3ff'
LIGHT_RED = '#fdecec'
LIGHT_GRAY = '#f8f9fa'
TEXT_MUTED = '#4A5568'


def safe(value: Any) -> str:
    if value is None or value == '':
        return 'N/A'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(', ', ': '))
    return str(value)


def pretty_key(key: Any) -> str:
    text = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', str(key))
    return text.replace('_', ' ').replace('-', ' ').strip().title()


def paragraph(value, style):
    text = safe(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return Paragraph(text, style)


def flatten(value: Any, prefix=''):
    rows = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f'{prefix}.{key}' if prefix else str(key)
            rows.extend(flatten(child, path))
    elif isinstance(value, list):
        if not value:
            rows.append((prefix, '[]'))
        else:
            for index, child in enumerate(value):
                rows.extend(flatten(child, f'{prefix}[{index}]'))
    else:
        rows.append((prefix, safe(value)))
    return rows


def list_from(payload, keys=('items', 'data', 'interfaces', 'stations', 'subscribers')):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return value
        if isinstance(payload.get('data'), dict):
            return list_from(payload['data'], keys)
    return []


def first_value(*values):
    for value in values:
        if value is not None and value != '' and value != [] and value != {}:
            return value
    return None


def recursive_find(obj: Any, keys: tuple[str, ...], max_depth=5):
    """Find a meaningful field in nested UISP payloads without assuming one schema."""
    wanted = {key.lower() for key in keys}

    def walk(value, depth):
        if depth > max_depth:
            return None
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).lower() in wanted and child not in (None, '', [], {}):
                    return child
            for child in value.values():
                result = walk(child, depth + 1)
                if result not in (None, '', [], {}):
                    return result
        elif isinstance(value, list):
            for child in value:
                result = walk(child, depth + 1)
                if result not in (None, '', [], {}):
                    return result
        return None

    return walk(obj, 0)


def parse_timestamp(value):
    if isinstance(value, (int, float)):
        value = value / 1000 if value > 10_000_000_000 else value
        try:
            return datetime.fromtimestamp(value)
        except Exception:
            return None
    if not value:
        return None
    text = str(value).replace('Z', '+00:00')
    try:
        dt = datetime.fromisoformat(text)
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except Exception:
        return None


def parse_iso(value):
    dt = parse_timestamp(value)
    return dt.strftime('%d %b %H:%M') if dt else safe(value)


def format_uptime(value):
    if value is None:
        return 'N/A'
    try:
        total = int(float(value))
        days, rem = divmod(total, 86400)
        hours, rem = divmod(rem, 3600)
        minutes = rem // 60
        return f'{days}d {hours}h {minutes}m'
    except Exception:
        return safe(value)


def styled_table(rows, widths, header=True, font_size=8, header_color=DARK_GREEN, repeat_rows=None):
    styles = getSampleStyleSheet()
    cell = ParagraphStyle(
        'ReportCell', parent=styles['Normal'], fontName='Helvetica',
        fontSize=font_size, leading=font_size + 2, spaceAfter=0,
    )
    head = ParagraphStyle(
        'ReportHead', parent=cell, fontName='Helvetica-Bold',
        textColor=colors.white,
    )
    data = []
    for i, row in enumerate(rows):
        data.append([paragraph(value, head if header and i == 0 else cell) for value in row])
    table = Table(
        data,
        colWidths=widths,
        repeatRows=(1 if header else 0) if repeat_rows is None else repeat_rows,
        hAlign='LEFT',
    )
    commands = [
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor(GRID)),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]
    if header:
        commands += [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(header_color)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ]
    table.setStyle(TableStyle(commands))
    return table


def extract_series(block, key='avg'):
    if not block:
        return [], []
    target = block.get(key) if isinstance(block, dict) else block
    if isinstance(block, dict) and not target and key == 'avg':
        target = block.get('values') or block.get('history') or block.get('data')
    if not isinstance(target, list):
        return [], []
    timestamps, values = [], []
    for item in target:
        if isinstance(item, dict):
            x = item.get('x', item.get('timestamp', item.get('time')))
            y = item.get('y', item.get('value'))
            if x is not None and isinstance(y, (int, float)) and math.isfinite(float(y)):
                dt = parse_timestamp(x)
                if dt:
                    timestamps.append(dt)
                    values.append(float(y))
    return timestamps, values


def metric_summary(node):
    if not isinstance(node, dict):
        return None, None, None
    avg_ts, avg_values = extract_series(node, 'avg')
    max_ts, max_values = extract_series(node, 'max')

    def scalar(value):
        return value if isinstance(value, (int, float)) and math.isfinite(float(value)) else None

    latest = scalar(node.get('latest'))
    average = scalar(node.get('average')) or scalar(node.get('avg'))
    peak = scalar(node.get('peak'))

    if latest is None and avg_values:
        latest = avg_values[-1]
    if average is None and avg_values:
        average = sum(avg_values) / len(avg_values)
    if peak is None and max_values:
        peak = max(max_values)
    if peak is None and avg_values:
        peak = max(avg_values)
    return latest, average, peak


def choose_unit(values):
    peak = max([abs(float(v)) for v in values] or [0])
    if peak >= 1_048_576:
        return 1_048_576, 'MB'
    if peak >= 1024:
        return 1024, 'KB'
    return 1, 'B'


def align_peak_series(avg_ts, max_ts, max_values):
    """Align UISP peak values by timestamp when possible; tolerate different lengths."""
    if not max_values:
        return []
    if len(max_values) == len(avg_ts) and len(max_ts) == len(max_values):
        by_time = dict(zip(max_ts, max_values))
        aligned = [by_time.get(ts) for ts in avg_ts]
        if all(value is not None for value in aligned):
            return aligned
    return max_values


def make_chart(data_source, title, unit, path, port=False):
    """Create a veryimp-style chart: normal/average BLUE, peak RED."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    avg_ts, avg_values = extract_series(data_source, 'avg')
    max_ts, max_values = extract_series(data_source, 'max')
    if len(avg_values) < 2:
        return None

    points = sorted(zip(avg_ts, avg_values), key=lambda pair: pair[0])
    avg_ts = [p[0] for p in points]
    avg_values = [p[1] for p in points]
    peak_values = align_peak_series(avg_ts, max_ts, max_values)

    if peak_values and len(peak_values) == len(avg_values):
        # Keep peak data paired with the average timestamps.
        peak_points = list(zip(avg_ts, peak_values))
    elif peak_values:
        peak_points = list(zip(max_ts, peak_values))
    else:
        peak_points = []

    raw_for_unit = avg_values + (peak_values or [])
    divisor, scaled_unit = choose_unit(raw_for_unit) if port else (1, unit)
    avg_scaled = [v / divisor for v in avg_values]
    peak_scaled = [v / divisor for v in peak_values] if peak_values else []

    latest = avg_scaled[-1]
    average = sum(avg_scaled) / len(avg_scaled)
    peak = max(peak_scaled) if peak_scaled else max(avg_scaled)

    fig = None
    try:
        fig, ax = plt.subplots(figsize=(8.0, 2.8))

        # REQUIRED visual agreement with veryimp.pdf:
        # normal/average = blue, peak = red.
        ax.plot(avg_ts, avg_scaled, color=NORMAL_BLUE, linewidth=1.8, label='Average')
        ax.fill_between(avg_ts, avg_scaled, color=NORMAL_BLUE, alpha=0.10)

        if peak_scaled:
            peak_x = avg_ts if len(peak_scaled) == len(avg_ts) else [p[0] for p in peak_points]
            ax.plot(peak_x, peak_scaled, color=PEAK_RED, linewidth=1.25, label='Peak')
            if len(peak_scaled) == len(avg_scaled):
                ax.fill_between(avg_ts, avg_scaled, peak_scaled, color=PEAK_RED, alpha=0.08)

        ax.set_title(
            f'{title}\nNow: {latest:.1f}{scaled_unit} | Avg: {average:.1f}{scaled_unit} | Peak: {peak:.1f}{scaled_unit}',
            fontsize=8, fontweight='bold', loc='center'
        )
        ax.set_ylabel(scaled_unit)
        ax.grid(True, linestyle=':', alpha=0.25)
        ax.tick_params(labelsize=6.5)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b %H:%M'))
        ax.legend(loc='upper right', fontsize=6, frameon=False)
        fig.autofmt_xdate()
        fig.tight_layout()
        fig.savefig(path, dpi=120, bbox_inches='tight')
        return path
    except (OSError, ValueError, RuntimeError, TypeError):
        return None
    finally:
        if fig is not None:
            plt.close(fig)


def _find_metric_sources(payload, target_keys, max_depth=10):
    """Find telemetry metric blocks anywhere in the UISP payload.

    GPON telemetry is not consistent across UISP versions: output current and
    output voltage may live under statistics, interfaces, health, power, fiber,
    or another nested object. Search the complete response tree, but only
    return values that actually look like telemetry blocks.
    """
    found = []
    wanted = {str(k).lower() for k in target_keys}

    def walk(value, depth=0):
        if depth > max_depth:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).lower() in wanted and isinstance(child, (dict, list)):
                    found.append((str(key), child))
                walk(child, depth + 1)
        elif isinstance(value, list):
            for child in value:
                walk(child, depth + 1)

    walk(payload)
    return found


def discover_metric_charts(stats, work_dir, extra=None, device=None, detail=None, interfaces=None):
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    charts = []
    core = [
        ('ping', 'ms', 'Ping Latency Profile'),
        ('cpu', '%', 'Core CPU Allocation History'),
        ('ram', '%', 'Memory Allocation History'),
        ('temperature', '°C', 'Internal Component Temperature'),
    ]

    # GPON/ONU devices expose electrical/optical telemetry in different
    # locations depending on the UISP version. Search all collected payloads,
    # not just statistics, so real UISP Output Current/Voltage charts are not
    # silently omitted.
    gpon_metrics = [
        ('outputCurrent', 'A', 'Output Current History'),
        ('output_current', 'A', 'Output Current History'),
        ('outputVoltage', 'V', 'Output Voltage History'),
        ('output_voltage', 'V', 'Output Voltage History'),
        ('outputCurrentHistory', 'A', 'Output Current History'),
        ('outputVoltageHistory', 'V', 'Output Voltage History'),
        ('current', 'A', 'Output Current History'),
        ('voltage', 'V', 'Output Voltage History'),
    ]

    sources = []
    for payload in (stats, device, detail, interfaces or [], extra or {}):
        if payload not in (None, '', [], {}):
            sources.append(payload)

    seen_sources = set()

    # First use the known top-level/core paths.
    for key, unit, title in core:
        source = stats.get(key) if isinstance(stats, dict) else None
        if source is None and isinstance(stats, dict):
            for container_key in ('gpon', 'fiber', 'optical', 'power', 'health'):
                container = stats.get(container_key)
                if isinstance(container, dict) and container.get(key) is not None:
                    source = container.get(key)
                    break
        if source is None:
            continue
        source_key = id(source)
        if source_key in seen_sources:
            continue
        seen_sources.add(source_key)
        path = work_dir / f'{re.sub(r"[^A-Za-z0-9_-]+", "_", key)}.png'
        if make_chart(source, title, unit, path):
            charts.append(path)

    # Then discover GPON metrics wherever UISP placed them.
    for key, unit, title in gpon_metrics:
        for payload in sources:
            for found_key, source in _find_metric_sources(payload, (key,)):
                source_key = id(source)
                if source_key in seen_sources:
                    continue
                seen_sources.add(source_key)
                path = work_dir / f'{re.sub(r"[^A-Za-z0-9_-]+", "_", found_key)}_{len(charts)}.png'
                if make_chart(source, title, unit, path):
                    charts.append(path)

    interfaces_list = list_from(stats, ('interfaces', 'items', 'data')) if isinstance(stats, dict) else []
    for index, entry in enumerate(interfaces_list):
        if not isinstance(entry, dict):
            continue
        ident = entry.get('identification') if isinstance(entry.get('identification'), dict) else {}
        name = ident.get('displayName') or ident.get('name') or entry.get('name') or entry.get('id') or f'port_{index}'
        safe_name = re.sub(r'[^A-Za-z0-9_-]+', '_', str(name))
        for direction, keys in [('Rx', ('receive', 'rxBytes', 'rxRate')), ('Tx', ('transmit', 'txBytes', 'txRate'))]:
            source = next((entry.get(k) for k in keys if entry.get(k) is not None), None)
            path = work_dir / f'int_{safe_name}_{direction.lower()}.png'
            if make_chart(source, f'Interface {name} - {direction} Throughput', 'B', path, port=True):
                charts.append(path)
    return charts


def extract_interfaces(payload):
    return list_from(payload, ('items', 'data', 'interfaces'))


def extract_subscribers(dataset):
    detail = dataset.get('detail') or {}
    candidates = [
        detail.get('stations') if isinstance(detail, dict) else None,
        detail.get('subscribers') if isinstance(detail, dict) else None,
        dataset.get('subscribers'),
        dataset.get('extra', {}).get('wireless_stations') if isinstance(dataset.get('extra'), dict) else None,
    ]
    # UISP also embeds the richest connected-station records inside the
    # wireless interface object. Include those so the compact subscriber
    # section never incorrectly says there are no active stations.
    for face in extract_interfaces(dataset.get('interfaces')):
        if isinstance(face, dict):
            candidates.append(face.get('stations'))
    collected = []
    seen = set()
    for candidate in candidates:
        result = list_from(candidate, ('items', 'data', 'stations', 'subscribers'))
        for item in result:
            if not isinstance(item, dict):
                continue
            key = str(item.get('mac') or item.get('ipAddress') or item.get('id') or item.get('name') or len(collected))
            if key not in seen:
                seen.add(key)
                collected.append(item)
    return collected


def extract_wireless_stations(dataset):
    """Collect the rich station records exposed inside wireless interfaces and the AirMax station endpoint."""
    candidates = []
    interfaces = extract_interfaces(dataset.get('interfaces'))
    for face in interfaces:
        if not isinstance(face, dict):
            continue
        stations = face.get('stations')
        if isinstance(stations, list):
            candidates.extend(stations)
        elif isinstance(stations, dict):
            candidates.extend(list_from(stations, ('items', 'data', 'stations')))

    extra = dataset.get('extra') if isinstance(dataset.get('extra'), dict) else {}
    candidates.extend(list_from(extra.get('wireless_stations'), ('items', 'data', 'stations')))

    detail = dataset.get('detail') if isinstance(dataset.get('detail'), dict) else {}
    candidates.extend(list_from(detail.get('stations'), ('items', 'data', 'stations')))

    merged = []
    by_key = {}
    for item in candidates:
        if not isinstance(item, dict):
            continue
        key = str(item.get('mac') or item.get('ipAddress') or item.get('id') or item.get('name') or len(merged))
        if key not in by_key:
            by_key[key] = item
            merged.append(item)
        else:
            # Prefer the richest record when the same station came from two endpoints.
            existing = by_key[key]
            for k, v in item.items():
                if existing.get(k) in (None, '', [], {}) and v not in (None, '', [], {}):
                    existing[k] = v
    return merged


def format_rate(value):
    if value in (None, '', [], {}):
        return 'N/A'
    try:
        value = float(value)
        if value >= 1_000_000_000:
            return f'{value / 1_000_000_000:.2f} Gbps'
        if value >= 1_000_000:
            return f'{value / 1_000_000:.2f} Mbps'
        if value >= 1_000:
            return f'{value / 1_000:.2f} Kbps'
        return f'{value:.0f} bps'
    except Exception:
        return safe(value)


def format_bytes(value):
    if value in (None, '', [], {}):
        return 'N/A'
    try:
        value = float(value)
        units = ('B', 'KB', 'MB', 'GB', 'TB')
        index = 0
        while abs(value) >= 1024 and index < len(units) - 1:
            value /= 1024
            index += 1
        return f'{value:.1f} {units[index]}'
    except Exception:
        return safe(value)


def format_mbps(value):
    if value in (None, '', [], {}):
        return 'N/A'
    try:
        return f'{float(value) / 1_000_000:.2f} Mbps'
    except Exception:
        return safe(value)


def format_percent(value):
    if value in (None, '', [], {}):
        return 'N/A'
    try:
        number = float(value)
        if abs(number) <= 1:
            number *= 100
        return f'{number:.0f}%'
    except Exception:
        return safe(value)


def station_link_potential(station, device=None, detail=None):
    """Return UISP's direct link-potential field when present; do not invent a value."""
    payloads = [station, device or {}, detail or {}]
    for payload in payloads:
        value = recursive_find(payload, ('linkPotential', 'linkPotentialPercent', 'potential'))
        if value not in (None, '', [], {}):
            return format_percent(value)
    return 'N/A (not returned by UISP API)'


def station_diagnostic_rows(station, device, detail, interfaces):
    """Build a human-readable station/link profile from UISP's rich wireless fields."""
    wireless = {}
    for face in interfaces:
        if not isinstance(face, dict):
            continue
        if isinstance(face.get('wireless'), dict):
            wireless = face['wireless']
            break

    overview = device.get('overview') if isinstance(device, dict) and isinstance(device.get('overview'), dict) else {}
    link_score = overview.get('linkScore') if isinstance(overview.get('linkScore'), dict) else {}
    hint = link_score.get('linkScoreHint') or recursive_find(device, ('linkScoreHint',))
    utilization = first_value(
        station.get('utilization'),
        station.get('downlinkUtilization'),
        station.get('uplinkUtilization'),
        overview.get('downlinkUtilization'),
        overview.get('uplinkUtilization'),
    )
    station_name = station.get('name') or station.get('displayName') or station.get('hostname') or 'Wireless Station'
    status = 'CONNECTED' if station.get('connected') is True else ('DISCONNECTED' if station.get('connected') is False else 'N/A')

    down = station.get('downlinkCapacity')
    up = station.get('uplinkCapacity')
    total = station.get('totalCapacity')
    expected_down = first_value(
        station.get('theoreticalDownlinkCapacity'),
        overview.get('theoreticalDownlinkCapacity'),
    )
    expected_up = first_value(
        station.get('theoreticalUplinkCapacity'),
        overview.get('theoreticalUplinkCapacity'),
    )
    if total is None and down is not None and up is not None:
        try:
            total = float(down) + float(up)
        except Exception:
            total = None
    expected_total = first_value(station.get('theoreticalTotalCapacity'), overview.get('theoreticalTotalCapacity'))

    current_signal = first_value(station.get('rxSignal'), station.get('signal'))
    tx_signal = first_value(station.get('txSignal'), station.get('remoteSignal'))
    ideal_rx = station.get('rxSignalIdeal')
    ideal_tx = station.get('txSignalIdeal')

    rows = [
        ['Link Status', status],
        ['Link Health', safe(first_value(
            station.get('linkHealth'), station.get('health'),
            station.get('linkStatus'), overview.get('linkHealth'), overview.get('health')
        ))],
        ['Link Potential', station_link_potential(station, device, detail)],
        ['Link Capacity', format_mbps(total)],
        ['Expected Capacity', format_mbps(expected_total)],
        ['PTMP Link Name', station_name],
        ['Station IP Address', station.get('ipAddress') or nested_get(station, 'deviceIdentification.ip')],
        ['Station MAC', station.get('mac')],
        ['Version', nested_get(station, 'deviceIdentification.firmwareVersion') or station.get('firmwareVersion')],
        ['Radio', station.get('radio')],
        ['Uptime', format_uptime(station.get('uptime'))],
        ['Connection Time', format_uptime(station.get('connectionTime'))],
        ['Utilization', format_percent(utilization)],
        ['Capacity / Expected — Downlink', f'{format_mbps(down)} / {format_mbps(expected_down)}'],
        ['Capacity / Expected — Uplink', f'{format_mbps(up)} / {format_mbps(expected_up)}'],
        ['UL Data Rate / Expected', f'{safe(station.get("txMcs"))}X / {safe(station.get("txMcsIdeal"))}X'],
        ['DL Data Rate / Expected', f'{safe(station.get("rxMcs"))}X / {safe(station.get("rxMcsIdeal"))}X'],
        ['Frequency', f'{safe(wireless.get("frequency") or station.get("frequency"))} MHz'],
        ['Channel Width', f'{safe(wireless.get("channelWidth"))} MHz'],
        ['TX Signal / Expected', f'{safe(tx_signal)} dBm / {safe(ideal_tx)} dBm'],
        ['RX Signal / Expected', f'{safe(current_signal)} dBm / {safe(ideal_rx)} dBm'],
        ['Frame Length', f'{safe(wireless.get("frameLength"))} ms'],
        ['DL / UL Ratio', f'{safe(wireless.get("dlRatio"))}% / {100 - float(wireless.get("dlRatio")):.0f}%' if wireless.get('dlRatio') is not None else 'N/A'],
        ['Output Power (EIRP)', f'{safe(wireless.get("transmitEirp"))} dBm'],
        ['TX / RX Bytes', f'{format_bytes(station.get("txBytes"))} / {format_bytes(station.get("rxBytes"))}'],
        ['TX / RX Data Rate', f'{format_rate(station.get("txRate"))} / {format_rate(station.get("rxRate"))}'],
        ['TX / RX Modulation', f'{safe(station.get("txModulation"))} / {safe(station.get("rxModulation"))}'],
        ['Noise Floor', f'{safe(station.get("noiseFloor") or wireless.get("noiseFloor"))} dBm'],
        ['Latency', f'{safe(station.get("latency"))} ms'],
        ['Distance', f'{safe(station.get("distance"))} m'],
    ]
    if hint:
        rows.append(['UISP Link Hint', hint])
    if link_score:
        rows.append(['Link Score', format_percent(link_score.get('linkScore'))])
        rows.append(['Overall Score', format_percent(link_score.get('score'))])
    return rows



def _format_capacity_value(value):
    """Format UISP capacity values while tolerating bps or already-Mbps values."""
    if value in (None, '', [], {}):
        return 'N/A'
    if isinstance(value, str):
        text = value.strip()
        if any(unit in text.lower() for unit in ('bps', 'kbps', 'mbps', 'gbps')):
            return text
    try:
        number = float(value)
        # UISP telemetry commonly returns capacity in bps; small values are
        # occasionally already expressed in Mbps.
        if abs(number) < 10000:
            return f'{number:.2f} Mbps'
        return format_mbps(number)
    except Exception:
        return safe(value)


def _format_duration_or_percent(value, percent=False):
    if value in (None, '', [], {}):
        return 'N/A'
    if percent:
        return format_percent(value)
    return format_uptime(value)


def _format_percent_if_numeric(value):
    """Format a percentage only when the source is actually percentage-like."""
    if value in (None, '', [], {}):
        return 'N/A'
    text = str(value).strip()
    if '%' in text:
        return text
    try:
        number = float(value)
        # UISP percentage fields may be returned as either 0..1 or 0..100.
        if 0 <= number <= 1:
            number *= 100
        if 0 <= number <= 100:
            return f'{number:.1f}%'
    except (TypeError, ValueError):
        pass
    return safe(value)


def _format_signal(value):
    if value in (None, '', [], {}):
        return 'N/A'
    text = safe(value)
    return text if 'dbm' in text.lower() else f'{text} dBm'


def _format_ratio(value):
    if value in (None, '', [], {}):
        return 'N/A'
    if isinstance(value, dict):
        down = first_value(value.get('downlink'), value.get('down'), value.get('dl'))
        up = first_value(value.get('uplink'), value.get('up'), value.get('ul'))
        if down is not None or up is not None:
            return f'{_format_percent_if_numeric(down)} / {_format_percent_if_numeric(up)}'
    text = safe(value)
    if '/' in text:
        return text
    try:
        down = float(value)
        if 0 <= down <= 100:
            return f'{down:.0f}% / {100-down:.0f}%'
    except (TypeError, ValueError):
        pass
    return text


def _format_antenna(value):
    if not isinstance(value, dict):
        return safe(value)
    name = value.get('name') or value.get('displayName') or value.get('type')
    gain = value.get('gain')
    built_in = value.get('builtIn')
    parts = []
    if name:
        parts.append(str(name))
    if gain is not None:
        parts.append(f'{gain} dBi')
    if built_in is True:
        parts.append('Built-in')
    return ' — '.join(parts) if parts else safe(value)


def _wireless_source_values(device, detail, extra):
    """Return source payloads in UI-oriented precedence order."""
    sources = []
    for payload in (
        detail,
        device,
        (extra or {}).get('device_status') if isinstance(extra, dict) else None,
        (extra or {}).get('device_health') if isinstance(extra, dict) else None,
        (extra or {}).get('wireless_config') if isinstance(extra, dict) else None,
    ):
        if isinstance(payload, dict):
            sources.append(payload)
    return sources


def _wireless_value(sources, *paths):
    """Use exact paths first, then an exact-key recursive fallback."""
    for payload in sources:
        for path in paths:
            value = nested_get(payload, path)
            if value not in (None, '', [], {}):
                return value
    keys = {path.split('.')[-1].lower() for path in paths}
    for payload in sources:
        value = recursive_find(payload, tuple(keys))
        if value not in (None, '', [], {}):
            return value
    return None


def _wireless_percentage(sources, *paths):
    """Find only explicit percentage fields; never turn uptime seconds into %."""
    value = _wireless_value(sources, *paths)
    if value is None:
        return None
    try:
        number = float(value)
        if number > 100 and '%' not in str(value):
            return None
    except (TypeError, ValueError):
        if '%' not in str(value):
            return None
    return value


def access_point_summary_rows(device, detail, extra, stations, interfaces=None):
    """Build the wireless/PTMP panel from the same UISP interface/link records used by the UI.

    Important: do not substitute generic device uptime/counters for link-panel values.
    UISP exposes several similarly named values at different levels (device, radio,
    interface and station). The report therefore keeps those scopes separate and
    only uses explicit fields for each UI label.
    """
    sources = _wireless_source_values(device, detail, extra)

    # Wireless interface data is a major source for the UISP device panel.
    # Add only the nested wireless blocks, rather than the entire interface, so
    # unrelated subscriber/device fields cannot leak into the link summary.
    for face in interfaces or []:
        if not isinstance(face, dict):
            continue
        wireless = face.get('wireless')
        if isinstance(wireless, dict):
            sources.insert(0, wireless)

    # Some UISP versions put link-panel values in a station record. Prefer those
    # only for fields that are explicitly link-scoped.
    link_records = [x for x in (stations or []) if isinstance(x, dict)]
    rows = []

    def add(label, value, formatter=None):
        if value in (None, '', [], {}):
            return
        rows.append([label, formatter(value) if formatter else value])

    # These correspond to the values displayed in UISP's wireless link panel.
    link_potential = _wireless_percentage(
        sources, 'overview.linkPotential', 'overview.linkPotentialPercent',
        'linkPotential', 'linkPotentialPercent', 'potential'
    )
    if link_potential is None:
        for record in link_records:
            value = _wireless_percentage(
                [record], 'linkPotential', 'linkPotentialPercent', 'potential',
                'overview.linkPotential', 'overview.linkPotentialPercent'
            )
            if value is not None:
                link_potential = value
                break
    add('Link Potential', link_potential, _format_percent_if_numeric)

    add('Link Capacity', _wireless_value(
        sources, 'overview.linkCapacity', 'linkCapacity'
    ), _format_capacity_value)

    # If UISP does not expose a single total capacity field, preserve the two
    # directional capacities rather than inventing a total.
    capacity_expected = _wireless_value(
        sources, 'overview.capacityExpected', 'capacityExpected',
        'overview.capacity', 'capacity', 'overview.capacity.expected'
    )
    if capacity_expected is None:
        for record in link_records:
            capacity_expected = _wireless_value(
                [record], 'capacityExpected', 'overview.capacityExpected',
                'capacity', 'overview.capacity'
            )
            if capacity_expected is not None:
                break
    if capacity_expected is not None:
        if isinstance(capacity_expected, dict):
            current = first_value(capacity_expected.get('current'), capacity_expected.get('capacity'), capacity_expected.get('downlink'))
            expected = first_value(capacity_expected.get('expected'), capacity_expected.get('theoretical'))
            add('Capacity / Expected', f'{_format_capacity_value(current)} / {_format_capacity_value(expected)}')
        elif isinstance(capacity_expected, (list, tuple)) and len(capacity_expected) >= 2:
            add('Capacity / Expected', f'{_format_capacity_value(capacity_expected[0])} / {_format_capacity_value(capacity_expected[1])}')
        else:
            add('Capacity / Expected', safe(capacity_expected))

    ptmp_name = _wireless_value(sources, 'overview.ptmpLinkName', 'overview.linkName', 'ptmpLinkName', 'linkName')
    if ptmp_name is None:
        for record in link_records:
            ptmp_name = _wireless_value([record], 'ptmpLinkName', 'linkName', 'name', 'apDevice.name', 'apDeviceName')
            if ptmp_name:
                break
    add('PTMP Link Name', ptmp_name)
    add('Utilization (Past 24Hrs)', _wireless_percentage(
        sources, 'overview.utilization24h', 'overview.utilization24Hrs',
        'utilization24h', 'utilization24Hrs'
    ), _format_percent_if_numeric)
    add('Airtime Distribution', _wireless_percentage(
        sources, 'overview.airtimeDistribution', 'overview.airTimeDistribution',
        'airtimeDistribution', 'airTimeDistribution'
    ), _format_percent_if_numeric)

    # Uptime must come from an explicit percentage field. A raw overview.uptime
    # value is a duration in seconds on many AirMAX devices (e.g. 1803376).
    add('Uptime', _wireless_percentage(
        sources, 'overview.uptimePercentage', 'overview.uptimePercent',
        'uptimePercentage', 'uptimePercent', 'availabilityPercentage', 'availability',
        'overview.availabilityPercentage', 'overview.availability'
    ), _format_percent_if_numeric)

    add('UL Data Rate / Expected', _wireless_value(
        sources, 'overview.ulDataRateExpected', 'ulDataRateExpected'
    ))
    add('DL Data Rate / Expected', _wireless_value(
        sources, 'overview.dlDataRateExpected', 'dlDataRateExpected'
    ))
    add('Version', _wireless_value(sources, 'identification.firmwareVersion', 'firmwareVersion', 'overview.firmwareVersion'))
    add('Radio', _wireless_value(sources, 'overview.radio', 'radio'))
    add('Frequency', _wireless_value(sources, 'overview.frequency', 'frequency'), lambda v: f'{safe(v)} MHz')
    add('Channel Width', _wireless_value(sources, 'overview.channelWidth', 'channelWidth'), lambda v: f'{safe(v)} MHz')

    # The UISP UI labels signal directions from the selected station's point of
    # view. Preserve tx/rx direction exactly instead of swapping them.
    tx_signal = _wireless_value(sources, 'overview.txSignal', 'txSignal')
    rx_signal = _wireless_value(sources, 'overview.rxSignal', 'rxSignal')
    tx_ideal = _wireless_value(sources, 'overview.txSignalIdeal', 'txSignalIdeal')
    rx_ideal = _wireless_value(sources, 'overview.rxSignalIdeal', 'rxSignalIdeal')
    if tx_signal is not None or tx_ideal is not None:
        add('TX Signal / Expected', f'{_format_signal(tx_signal)} / {_format_signal(tx_ideal)}')
    if rx_signal is not None or rx_ideal is not None:
        add('RX Signal / Expected', f'{_format_signal(rx_signal)} / {_format_signal(rx_ideal)}')

    add('Frame Length', _wireless_value(sources, 'overview.frameLength', 'frameLength'), lambda v: f'{safe(v)} ms')
    add('DL / UL Ratio', _wireless_value(sources, 'overview.dlRatio', 'dlRatio'), _format_ratio)
    add('Output Power (EIRP)', _wireless_value(sources, 'overview.transmitEirp', 'transmitEirp', 'outputPower'), lambda v: f'{safe(v)} dBm')

    tx_bytes = _wireless_value(sources, 'overview.txBytes', 'txBytes')
    rx_bytes = _wireless_value(sources, 'overview.rxBytes', 'rxBytes')
    if tx_bytes is not None or rx_bytes is not None:
        add('TX / RX Bytes', f'{format_bytes(tx_bytes)} / {format_bytes(rx_bytes)}')

    connection = _wireless_value(sources, 'overview.connectionTime', 'connectionTime', 'connectionDuration')
    add('Connection Time', connection, format_uptime)

    security = _wireless_value(sources, 'overview.wirelessSecurity', 'wirelessSecurity', 'security')
    add('Wireless Security', security)
    add('Country', _wireless_value(sources, 'overview.country', 'country', 'identification.country'))
    mode = _wireless_value(sources, 'overview.wirelessMode', 'wirelessMode')
    if mode:
        mode_map = {'sta-ptmp': 'Station', 'ap-ptmp': 'Access Point'}
        add('Wireless Mode', mode_map.get(str(mode).lower(), safe(mode)))
    add('Antenna', _wireless_value(sources, 'overview.antenna', 'antenna'), _format_antenna)
    add('Cable Loss', _wireless_value(sources, 'overview.cableLoss', 'cableLoss'), lambda v: f'{safe(v)} dB')
    add('Location', _wireless_value(sources, 'overview.location', 'location', 'identification.location'))
    add('Altitude', _wireless_value(sources, 'overview.altitude', 'altitude'), lambda v: f'{safe(v)} m')
    ethernet = _wireless_value(sources, 'overview.ethernetPort', 'ethernetPort')
    if ethernet is None:
        for face in interfaces or []:
            if not isinstance(face, dict):
                continue
            ident = face.get('identification') if isinstance(face.get('identification'), dict) else {}
            status = face.get('status') if isinstance(face.get('status'), dict) else {}
            if str(ident.get('type', '')).lower() in ('ethernet', 'eth', 'ethernet-port') or str(ident.get('name', '')).lower().startswith(('eth', 'port')):
                display = ident.get('displayName') or ident.get('name')
                speed = status.get('currentSpeed') or status.get('speed')
                duplex = status.get('duplex') or status.get('duplexMode')
                if display:
                    text = str(display)
                    if speed not in (None, '', 'N/A'):
                        text += f' {speed}'
                    if duplex not in (None, '', 'N/A'):
                        text += f' - {duplex}'
                    ethernet = text
                    break
    add('Ethernet Port', ethernet)

    if not any(row[0] == 'Stations Connected to AP' for row in rows) and stations:
        rows.append(['Stations Connected to AP', len(stations)])
    return rows

def is_gpon_device(device, detail):
    """Identify GPON/ONU/Fiber devices without relying on one UISP field name."""
    payloads = [device or {}, detail or {}]
    text_parts = []
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for path in (
            'identification.name', 'identification.modelName', 'identification.model',
            'identification.type', 'identification.role', 'overview.model',
            'overview.modelName', 'type', 'model', 'modelName', 'role',
        ):
            value = nested_get(payload, path)
            if value not in (None, '', [], {}):
                text_parts.append(str(value).lower())
    text = ' '.join(text_parts)
    return any(term in text for term in ('gpon', 'onu', 'fiber nano', 'fiber nano-g', 'optical network unit'))


def gpon_summary_rows(device, detail, extra):
    """Extract the GPON/ONU fields visible on UISP's Fiber device page."""
    payloads = [
        device or {}, detail or {},
        (extra or {}).get('device_status') if isinstance(extra, dict) else None,
        (extra or {}).get('device_health') if isinstance(extra, dict) else None,
        (extra or {}).get('wireless_config') if isinstance(extra, dict) else None,
    ]

    def val(*paths):
        for payload in payloads:
            if not isinstance(payload, dict):
                continue
            for path in paths:
                found = nested_get(payload, path)
                if found not in (None, '', [], {}):
                    return found
        # Fallback: UISP has changed the nesting/casing of GPON fields
        # between endpoint versions. Match keys case-insensitively and
        # recursively, but only against the exact candidate key names.
        keys = {str(path.split('.')[-1]).lower() for path in paths}
        def find_key(node):
            if isinstance(node, dict):
                for key, child in node.items():
                    if str(key).lower() in keys and child not in (None, '', [], {}):
                        return child
                    found = find_key(child)
                    if found not in (None, '', [], {}):
                        return found
            elif isinstance(node, list):
                for child in node:
                    found = find_key(child)
                    if found not in (None, '', [], {}):
                        return found
            return None
        for payload in payloads:
            found = find_key(payload)
            if found not in (None, '', [], {}):
                return found
        return None

    candidates = [
        ('Experience', ('overview.experience', 'experience', 'experienceScore', 'experiencePercentage')),
        ('Fiber Signal', ('overview.fiberSignal', 'overview.opticalSignal', 'fiberSignal', 'opticalSignal', 'rxOpticalPower', 'opticalPower', 'signal')),
        ('Connection Time', ('overview.connectionTime', 'connectionTime', 'connectionDuration')),
        ('OLT PON Port', ('overview.oltPonPort', 'overview.oltPONPort', 'overview.oltPort', 'overview.ponPort', 'overview.ponPortId', 'gpon.oltPonPort', 'gpon.oltPONPort', 'gpon.oltPort', 'gpon.ponPort', 'gpon.ponPortId', 'fiber.oltPonPort', 'fiber.oltPONPort', 'fiber.oltPort', 'fiber.ponPort', 'fiber.ponPortId', 'oltPonPort', 'oltPONPort', 'oltPort', 'ponPort', 'ponPortId')),
        ('ONU Mode', ('overview.onuMode', 'overview.ponMode', 'overview.onu.mode', 'gpon.onuMode', 'gpon.ponMode', 'gpon.onu.mode', 'fiber.onuMode', 'fiber.ponMode', 'fiber.onu.mode', 'onuMode', 'ponMode')),
        ('Fiber Dying Gasp', ('overview.fiberDyingGasp', 'overview.dyingGasp', 'fiberDyingGasp', 'dyingGasp')),
        ('Uptime', ('overview.uptimePercentage', 'overview.uptimePercent', 'uptimePercentage', 'uptimePercent', 'availabilityPercentage', 'availability', 'overview.availabilityPercentage', 'overview.availability', 'overview.uptime', 'uptime')),
        ('CPU Usage', ('overview.cpu', 'cpu', 'cpuUsage', 'overview.cpuUsage')),
        ('Memory Usage', ('overview.ram', 'overview.memory', 'ram', 'memory', 'memoryUsage', 'overview.memoryUsage')),
        ('Latency', ('overview.latency', 'latency', 'ping')),
        ('Throughput RX / TX', ('overview.throughput', 'overview.throughputRxTx', 'throughput', 'throughputRxTx')),
        ('Temperature', ('overview.temperature', 'temperature')),
        ('Power Time', ('overview.uptime', 'powerTime', 'overview.powerTime')),
    ]

    rows = []
    for label, paths in candidates:
        value = val(*paths)
        if value in (None, '', [], {}):
            continue
        if label in ('Experience', 'Uptime'):
            value = format_percent(value)
        elif label == 'Fiber Signal':
            text = safe(value)
            if 'dbm' not in text.lower():
                text = f'{text} dBm'
            value = text
        elif label == 'Connection Time':
            value = format_uptime(value)
        elif label == 'Latency':
            try:
                value = f'{float(value):g} ms'
            except Exception:
                value = safe(value)
        elif label == 'Temperature':
            value = f'{safe(value)} °C'
        elif label in ('CPU Usage', 'Memory Usage'):
            try:
                value = f'{float(value):g}%'
            except Exception:
                value = safe(value)
        elif label == 'Throughput RX / TX' and isinstance(value, dict):
            rx = first_value(value.get('rx'), value.get('receive'), value.get('rxRate'))
            tx = first_value(value.get('tx'), value.get('transmit'), value.get('txRate'))
            value = f'{format_rate(rx)} / {format_rate(tx)}'
        elif label == 'Power Time':
            value = format_uptime(value)
        rows.append([label, value])
    return rows


def resolve_device_ip(device, detail):
    """UISP IP resolver: prefer explicit device fields, then detail, then nested payloads."""
    candidates = [
        device.get('ip') if isinstance(device, dict) else None,
        device.get('ipAddress') if isinstance(device, dict) else None,
        device.get('managementIp') if isinstance(device, dict) else None,
        device.get('managementIpAddress') if isinstance(device, dict) else None,
        nested_get(device, 'overview.ipAddress'),
        nested_get(device, 'overview.ip'),
        detail.get('ip') if isinstance(detail, dict) else None,
        detail.get('ipAddress') if isinstance(detail, dict) else None,
        detail.get('managementIp') if isinstance(detail, dict) else None,
        detail.get('managementIpAddress') if isinstance(detail, dict) else None,
        nested_get(detail, 'overview.ipAddress'),
        nested_get(detail, 'overview.ip'),
        recursive_find(device, ('ipAddress', 'ip')),
        recursive_find(detail, ('ipAddress', 'ip')),
    ]
    value = first_value(*candidates)
    return value


def resolve_ipv6(device, detail):
    candidates = [
        device.get('ipv6LinkLocalList') if isinstance(device, dict) else None,
        detail.get('ipv6LinkLocalList') if isinstance(detail, dict) else None,
        device.get('ipv6AddressList') if isinstance(device, dict) else None,
        detail.get('ipv6AddressList') if isinstance(detail, dict) else None,
        nested_get(device, 'overview.ipv6LinkLocalList'),
        nested_get(detail, 'overview.ipv6LinkLocalList'),
    ]
    for value in candidates:
        if isinstance(value, list) and value:
            return ', '.join(str(x) for x in value)
        if value not in (None, '', [], {}):
            return value
    return None


def nested_get(obj, path):
    current = obj
    for part in path.split('.'):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _series_latest(node):
    """Return the latest numeric value from a UISP scalar/series block."""
    if node in (None, '', [], {}):
        return None
    if isinstance(node, (int, float)) and math.isfinite(float(node)):
        return float(node)
    if isinstance(node, dict):
        # UISP telemetry commonly exposes avg/max/values/history as [{x, y}].
        for key in ('avg', 'average', 'values', 'history', 'data', 'series'):
            value = node.get(key)
            if isinstance(value, list):
                numeric = []
                for item in value:
                    if isinstance(item, dict):
                        y = item.get('y', item.get('value'))
                    else:
                        y = item
                    if isinstance(y, (int, float)) and math.isfinite(float(y)):
                        numeric.append(float(y))
                if numeric:
                    return numeric[-1]
            elif isinstance(value, (int, float)) and math.isfinite(float(value)):
                return float(value)
        for key in ('latest', 'current', 'value', 'rate'):
            value = node.get(key)
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                return float(value)
    if isinstance(node, list):
        numeric = []
        for item in node:
            value = _series_latest(item)
            if value is not None:
                numeric.append(value)
        if numeric:
            return numeric[-1]
    return None


def _latest_metric(stats, key):
    if not isinstance(stats, dict):
        return None
    direct = _series_latest(stats.get(key))
    if direct is not None:
        return direct
    # Some UISP builds nest telemetry under data/metrics/overview.
    return _series_latest(recursive_find(stats, (key,)))


def _aggregate_interface_rate(stats, keys):
    """Aggregate current RX/TX rates from UISP interface telemetry when no top-level rate exists."""
    if not isinstance(stats, dict):
        return None
    interfaces = list_from(stats, ('interfaces', 'items', 'data'))
    total = 0.0
    found = False
    for face in interfaces:
        if not isinstance(face, dict):
            continue
        # Prefer rate fields. If UISP only exposes byte counters here, do not
        # mistake cumulative bytes for a current throughput rate.
        value = None
        for key in keys:
            if face.get(key) is not None:
                value = _series_latest(face.get(key))
                if value is not None:
                    break
        if value is not None:
            total += value
            found = True
    return total if found else None


def resolve_device_throughput(stats, device, detail):
    """Resolve the live RX/TX throughput shown by UISP, including EdgeSwitch telemetry."""
    payloads = [stats, device, detail]
    rx_keys = ('rxRate', 'receiveRate', 'downloadRate', 'download', 'rx')
    tx_keys = ('txRate', 'transmitRate', 'uploadRate', 'upload', 'tx')
    rx = None

    # Explicit top-level/nested scalar or telemetry series.
    for key in rx_keys:
        rx = _series_latest(stats.get(key)) if isinstance(stats, dict) else None
        if rx is not None:
            break
    if rx is None:
        rx = _aggregate_interface_rate(stats, ('rxRate', 'receive', 'rx'))

    for key in tx_keys:
        tx = _series_latest(stats.get(key)) if isinstance(stats, dict) else None
        if tx is not None:
            break
    if tx is None:
        tx = _aggregate_interface_rate(stats, ('txRate', 'transmit', 'tx'))

    if rx is None or tx is None:
        # Last fallback: UISP may expose current rates directly in device/detail.
        for payload in (device, detail):
            if not isinstance(payload, dict):
                continue
            if rx is None:
                for key in rx_keys:
                    rx = _series_latest(payload.get(key))
                    if rx is not None:
                        break
            if tx is None:
                for key in tx_keys:
                    tx = _series_latest(payload.get(key))
                    if tx is not None:
                        break

    if rx is None and tx is None:
        return None
    return f'RX: {format_rate(rx)} / TX: {format_rate(tx)}'


def resolve_uptime_percentage(stats, device, detail, extra=None):
    # UISP can expose both:
    #   - uptime duration in seconds (e.g. 1304267)
    #   - uptime percentage (e.g. 99.800)
    # Never interpret a large duration as a percentage.
    percent_candidates = []
    duration_candidates = []
    payloads = [device, detail, stats]
    if isinstance(extra, dict):
        payloads.extend([
            extra.get('device_status'),
            extra.get('device_health'),
            extra.get('wireless_config'),
        ])

    for payload in payloads:
        if not isinstance(payload, dict):
            continue

        percent_candidates.extend([
            payload.get('uptimePercentage'),
            payload.get('uptimePercent'),
            payload.get('availabilityPercentage'),
            payload.get('availability'),
            nested_get(payload, 'overview.uptimePercentage'),
            nested_get(payload, 'overview.uptimePercent'),
            nested_get(payload, 'overview.availabilityPercentage'),
            nested_get(payload, 'overview.availability'),
            nested_get(payload, 'status.uptimePercentage'),
            nested_get(payload, 'status.uptimePercent'),
        ])

        # Only use a generic `uptime` field as a percentage when its value is
        # already in the percentage range. Larger numeric values are durations.
        for candidate in (
            payload.get('uptime'),
            nested_get(payload, 'overview.uptime'),
            nested_get(payload, 'status.uptime'),
        ):
            if candidate not in (None, '', [], {}):
                try:
                    number = float(candidate)
                    if 0 <= number <= 100:
                        duration_candidates.append(candidate)
                except (TypeError, ValueError):
                    # A string such as "99.800%" is still a valid percentage.
                    if '%' in str(candidate):
                        duration_candidates.append(candidate)

    value = first_value(*percent_candidates, *duration_candidates)
    return format_percent(value) if value is not None else None


def normalized_device_fields(device, detail, stats, device_id, extra=None):
    ident = device.get('identification') if isinstance(device.get('identification'), dict) else {}
    detail_ident = detail.get('identification') if isinstance(detail.get('identification'), dict) else {}
    overview = device.get('overview') if isinstance(device.get('overview'), dict) else {}
    detail_overview = detail.get('overview') if isinstance(detail.get('overview'), dict) else {}

    # UISP portal's live CPU/RAM/latency values come from telemetry. Device
    # overview values can be stale, so telemetry is deliberately preferred.
    cpu = _latest_metric(stats, 'cpu')
    ram = _latest_metric(stats, 'ram')
    ping = _latest_metric(stats, 'ping')

    if cpu is None:
        cpu = first_value(overview.get('cpu'), detail_overview.get('cpu'), device.get('cpu'), detail.get('cpu'))
    if ram is None:
        ram = first_value(overview.get('ram'), detail_overview.get('ram'), device.get('ram'), detail.get('ram'))

    cpu_text = f'CPU: {cpu:g}' if isinstance(cpu, (int, float)) else None
    ram_text = f'RAM: {ram:g}' if isinstance(ram, (int, float)) else None
    cpu_ram = ' | '.join(x for x in (cpu_text, ram_text) if x) or None

    firmware = first_value(
        ident.get('firmwareVersion'), detail_ident.get('firmwareVersion'),
        device.get('firmwareVersion'), detail.get('firmwareVersion'),
        overview.get('firmwareVersion'), detail_overview.get('firmwareVersion'),
    )
    power_time = format_uptime(first_value(
        overview.get('uptime'), detail_overview.get('uptime'),
        device.get('uptime'), detail.get('uptime'),
    ))
    throughput = resolve_device_throughput(stats, device, detail)

    return {
        'Device Name': first_value(ident.get('name'), detail_ident.get('name'), device.get('name'), detail.get('name'), overview.get('name')),
        'Model Variant': first_value(ident.get('modelName'), detail_ident.get('modelName'), ident.get('model'), detail_ident.get('model'), device.get('model')),
        'IP Address': resolve_device_ip(device, detail),
        'MAC Address': first_value(device.get('mac'), ident.get('mac'), detail.get('mac'), detail_ident.get('mac'), device.get('macAddress')),
        'Device UUID': first_value(device_id, ident.get('id'), detail_ident.get('id'), device.get('id')),
        'Current Status': first_value(overview.get('status'), detail_overview.get('status'), device.get('status'), detail.get('status')),
        'IPv6 Link Local': resolve_ipv6(device, detail),
        'Version': firmware,
        'Temperature': first_value(overview.get('temperature'), detail_overview.get('temperature'), device.get('temperature'), detail.get('temperature')),
        'CPU / RAM': cpu_ram,
        'Latency': f'{ping:g} ms' if isinstance(ping, (int, float)) else None,
        'Uptime': resolve_uptime_percentage(stats, device, detail, extra),
        'Power Time': power_time,
        'Throughput RX / TX': throughput,
    }


def _value_at_paths(payloads, paths):
    for payload in payloads:
        for path in paths:
            value = nested_get(payload, path)
            if value not in (None, '', [], {}):
                return value
    return None


def additional_device_rows(device, detail, extra, normal_fields):
    """Curate useful UISP fields that are absent from the main report."""
    payloads = [device, detail]
    rows = []
    # UISP fields can be scalars, lists, or nested dictionaries.  Never put
    # raw values into a set because lists/dicts are unhashable.
    def dedupe_key(value):
        try:
            return json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)
        except (TypeError, ValueError):
            return repr(value)

    used = {dedupe_key(value) for value in normal_fields.values()}

    candidates = [
        ('Firmware Version', ('firmwareVersion', 'overview.firmwareVersion', 'identification.firmwareVersion')),
        ('Serial Number', ('serialNumber', 'overview.serialNumber', 'identification.serialNumber')),
        ('Platform', ('platformName', 'platformId')),
        ('Device Type', ('type', 'identification.type')),
        ('Device Category', ('category', 'identification.category')),
        ('Role', ('role', 'identification.role')),
        ('Enabled', ('enabled', 'overview.enabled')),
        ('Authorized', ('authorized', 'overview.authorized')),
        ('Hostname', ('hostname', 'overview.hostname')),
        ('Site', ('identification.site.name', 'site.name')),
        ('Site ID', ('identification.site.id', 'site.id')),
        ('Country', ('country', 'identification.country')),
        ('Country Code', ('countryCode', 'identification.countryCode')),
        ('Wireless Mode', ('overview.wirelessMode', 'wirelessMode')),
        ('Signal', ('overview.signal', 'signal')),
        ('Remote Signal', ('overview.remoteSignal', 'remoteSignal')),
        ('Signal Maximum', ('overview.signalMax', 'signalMax')),
        ('Remote Signal Maximum', ('overview.remoteSignalMax', 'remoteSignalMax')),
        ('Distance', ('overview.distance', 'distance')),
        ('Frequency', ('overview.frequency', 'frequency')),
        ('Stations Count', ('overview.stationsCount', 'stationsCount')),
        ('Uplink Capacity', ('overview.uplinkCapacity', 'uplinkCapacity')),
        ('Downlink Capacity', ('overview.downlinkCapacity', 'downlinkCapacity')),
        ('Uplink Score', ('overview.linkScore.uplinkScore', 'overview.uplinkScore', 'uplinkScore')),
        ('Downlink Score', ('overview.linkScore.downlinkScore', 'overview.downlinkScore', 'downlinkScore')),
        ('Link Score', ('overview.linkScore.score', 'overview.linkScore', 'linkScore')),
        ('Air Time', ('overview.linkScore.airTime', 'overview.airTime', 'airTime')),
        ('Voltage', ('overview.voltage', 'voltage')),
        ('Power Consumption', ('overview.consumption', 'consumption')),
        ('Bias Current', ('overview.biasCurrent', 'biasCurrent')),
        ('Output Power', ('overview.outputPower', 'outputPower')),
        ('PSU', ('overview.psu', 'psu')),
        ('Battery Capacity', ('overview.batteryCapacity', 'batteryCapacity')),
        ('Discovery Protocol', ('discovery.protocol', 'overview.discovery.protocol')),
        ('Discovery Configured', ('discovery.configured', 'overview.discovery.configured')),
    ]
    for label, paths in candidates:
        value = _value_at_paths(payloads, paths)
        if value not in (None, '', [], {}):
            key = dedupe_key(value)
            if key not in used:
                rows.append([label, value])
                used.add(key)

    for endpoint_name, payload in extra.items():
        if isinstance(payload, dict):
            # Pull meaningful top-level scalar fields from optional endpoint responses.
            for key, value in payload.items():
                if isinstance(value, (str, int, float, bool)) and value not in (None, ''):
                    label = f'{pretty_key(endpoint_name)} — {pretty_key(key)}'
                    key_value = dedupe_key(value)
                    if key_value not in used:
                        rows.append([label, value])
                        used.add(key_value)
    return rows


def extract_data_links(payload):
    """Normalize UISP /data-links/device/{id} responses to a list."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ('items', 'data', 'links', 'dataLinks'):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        # Some UISP versions can return one link object directly.
        if any(key in payload for key in ('from', 'to', 'state', 'type')):
            return [payload]
    return []


def _topology_endpoint_value(endpoint, keys):
    """Read a scalar from a Data Link endpoint without assuming one schema."""
    if not isinstance(endpoint, dict):
        if isinstance(endpoint, str):
            return endpoint if not keys else None
        return None
    for key in keys:
        value = endpoint.get(key)
        if value not in (None, '', [], {}):
            return value
    # UISP can nest the interface/device object differently between releases.
    for container_key in ('interface', 'device', 'identification', 'overview'):
        container = endpoint.get(container_key)
        if isinstance(container, dict):
            for key in keys:
                value = container.get(key)
                if value not in (None, '', [], {}):
                    return value
    return None


def topology_endpoint_label(endpoint):
    """Return a readable port/interface label from a UISP data-link endpoint."""
    if endpoint is None:
        return 'N/A'
    if isinstance(endpoint, str):
        return endpoint
    if isinstance(endpoint, (int, float)):
        return str(endpoint)
    if isinstance(endpoint, dict):
        value = _topology_endpoint_value(endpoint, (
            'displayName', 'name', 'label', 'description', 'interfaceName',
            'port', 'portName', 'id', 'interfaceId',
        ))
        if isinstance(value, dict):
            return topology_endpoint_label(value)
        return safe(value)
    return safe(endpoint)


def topology_device_label(endpoint):
    """Return the remote device/site name from a UISP data-link endpoint."""
    if not isinstance(endpoint, dict):
        return None
    device = endpoint.get('device')
    if isinstance(device, dict):
        ident = device.get('identification') if isinstance(device.get('identification'), dict) else {}
        overview = device.get('overview') if isinstance(device.get('overview'), dict) else {}
        value = (
            ident.get('displayName') or ident.get('name') or ident.get('hostname')
            or overview.get('name') or device.get('name') or device.get('displayName')
            or device.get('id')
        )
        if value:
            return str(value)
    site = endpoint.get('site')
    if isinstance(site, dict):
        value = site.get('name') or site.get('displayName') or site.get('id')
        if value:
            return str(value)
    return None


def topology_rows(data_links, selected_device_id):
    """Build the Uplink/Downlink rows shown by the UISP topology UI.

    Data Links are directional in UISP's model: `from` -> `to`. For the
    selected device, a link arriving at it is displayed as an Uplink and a
    link leaving it is displayed as a Downlink. The function only reports
    relationships actually returned by UISP; it never invents a connection.
    """
    links = extract_data_links(data_links)
    if not links:
        return [], []

    uplinks = []
    downlinks = []
    selected = str(selected_device_id or '').lower()

    for link in links:
        from_ep = link.get('from') if isinstance(link.get('from'), dict) else None
        to_ep = link.get('to') if isinstance(link.get('to'), dict) else None
        if from_ep is None and to_ep is None:
            continue

        def endpoint_ids(ep):
            ids = []
            if not isinstance(ep, dict):
                return ids
            device = ep.get('device') if isinstance(ep.get('device'), dict) else {}
            ident = device.get('identification') if isinstance(device.get('identification'), dict) else {}
            for value in (
                device.get('id'), ident.get('id'), device.get('deviceId'),
                ep.get('deviceId'), ep.get('id'),
            ):
                if value not in (None, ''):
                    ids.append(str(value).lower())
            return ids

        from_is_selected = selected and selected in endpoint_ids(from_ep)
        to_is_selected = selected and selected in endpoint_ids(to_ep)

        state = str(link.get('state') or link.get('status') or 'N/A').upper()
        link_type = str(link.get('type') or 'N/A').upper()
        remote_from = topology_device_label(from_ep)
        remote_to = topology_device_label(to_ep)

        from_port = topology_endpoint_label(from_ep.get('interface') if isinstance(from_ep, dict) else None)
        to_port = topology_endpoint_label(to_ep.get('interface') if isinstance(to_ep, dict) else None)

        # If UISP gives us the selected side, use the physical port on that
        # side. Otherwise fall back to the endpoint's direct port/interface.
        if to_is_selected:
            remote_name = remote_from or topology_endpoint_label(from_ep)
            row = [to_port, remote_name, state, link_type]
            uplinks.append(row)
        elif from_is_selected:
            remote_name = remote_to or topology_endpoint_label(to_ep)
            row = [from_port, remote_name, state, link_type]
            downlinks.append(row)
        else:
            # Older UISP responses may omit endpoint device IDs. In that case
            # keep the link visible rather than silently dropping it. Direction
            # follows the API's from -> to order.
            from_name = remote_from or topology_endpoint_label(from_ep)
            to_name = remote_to or topology_endpoint_label(to_ep)
            if from_name or to_name:
                downlinks.append([from_port, to_name or from_name, state, link_type])

    return uplinks, downlinks


def interface_additional_rows(interfaces):
    rows = []
    for index, face in enumerate(interfaces):
        ident = face.get('identification', {}) if isinstance(face.get('identification'), dict) else {}
        status = face.get('status', {}) if isinstance(face.get('status'), dict) else {}
        stats = face.get('statistics', {}) if isinstance(face.get('statistics'), dict) else {}
        addresses = face.get('addresses') if isinstance(face.get('addresses'), list) else []
        name = ident.get('displayName') or ident.get('name') or face.get('name') or f'Interface {index + 1}'
        address_text = ', '.join(str(a.get('cidr')) for a in addresses if isinstance(a, dict) and a.get('cidr'))
        rows.append([
            name,
            ident.get('type') or 'N/A',
            address_text or 'N/A',
            face.get('mtu') or 'N/A',
            status.get('speed') or status.get('currentSpeed') or 'N/A',
            'Enabled' if face.get('enabled') is True else ('Disabled' if face.get('enabled') is False else 'N/A'),
            stats.get('rxrate', stats.get('rxRate', 'N/A')),
            stats.get('txrate', stats.get('txRate', 'N/A')),
            stats.get('errors', 'N/A'),
        ])
    return rows


def non_timeseries_flatten(payload, prefix='', max_rows=250):
    """Flatten response while skipping massive x/y telemetry arrays."""
    rows = []
    if len(rows) >= max_rows:
        return rows
    if isinstance(payload, dict):
        for key, child in payload.items():
            path = f'{prefix}.{key}' if prefix else str(key)
            if key in ('avg', 'max', 'values', 'history') and isinstance(child, list):
                rows.append((path, f'{len(child)} telemetry points'))
                continue
            rows.extend(non_timeseries_flatten(child, path, max_rows - len(rows)))
            if len(rows) >= max_rows:
                break
    elif isinstance(payload, list):
        if not payload:
            rows.append((prefix, '[]'))
        elif all(isinstance(item, (str, int, float, bool)) for item in payload):
            rows.append((prefix, safe(payload)))
        else:
            for index, child in enumerate(payload):
                rows.extend(non_timeseries_flatten(child, f'{prefix}[{index}]', max_rows - len(rows)))
                if len(rows) >= max_rows:
                    break
    else:
        rows.append((prefix, safe(payload)))
    return rows


def render_device_report(dataset, story, work_dir, sections, device_number=None):
    device = dataset.get('device') or {}
    detail = dataset.get('detail') or {}
    stats = dataset.get('statistics') or {}
    interfaces = extract_interfaces(dataset.get('interfaces'))
    outages = list_from(dataset.get('outages'), ('items', 'data'))
    subscribers = extract_subscribers(dataset)
    wireless_stations = extract_wireless_stations(dataset)
    extra = dataset.get('extra') or {}

    ident = device.get('identification') if isinstance(device.get('identification'), dict) else {}
    detail_ident = detail.get('identification') if isinstance(detail.get('identification'), dict) else {}
    device_id = dataset.get('device_id') or ident.get('id') or detail_ident.get('id') or device.get('id')
    normalized = normalized_device_fields(device, detail, stats, device_id, extra)
    name = normalized['Device Name'] or device_id
    model = normalized['Model Variant']
    role = first_value(ident.get('role'), detail_ident.get('role'), device.get('role'), device.get('type'))

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('ReportTitle', parent=styles['Title'], fontName='Helvetica-Bold', fontSize=18, leading=22, textColor=colors.HexColor(BLUE), spaceAfter=2)
    section_style = ParagraphStyle('Section', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=12, leading=15, spaceBefore=12, spaceAfter=6)
    meta_style = ParagraphStyle('Meta', parent=styles['Normal'], fontSize=8.5, leading=11, textColor=colors.HexColor(TEXT_MUTED), spaceAfter=5)

    if device_number:
        story.append(PageBreak())
    story.append(Paragraph('UISP NETWORK INFRASTRUCTURE REPORT', title_style))
    story.append(Paragraph(f'<b>{safe(name)}</b> &nbsp; • &nbsp; {safe(model)} &nbsp; • &nbsp; {safe(role)}', meta_style))
    story.append(Paragraph(
        f'Device UUID: {safe(device_id)} &nbsp; • &nbsp; Data window: {PERIOD_LABELS.get(dataset.get("period"), dataset.get("period", "N/A"))} &nbsp; • &nbsp; Collected: {safe(dataset.get("collected_at"))}',
        meta_style,
    ))

    if sections.get('device_information', True):
        story.append(Paragraph('Device Specifications Profile', section_style))
        spec_pairs = list(normalized.items())
        rows = []
        for i in range(0, len(spec_pairs), 2):
            left = spec_pairs[i]
            right = spec_pairs[i + 1] if i + 1 < len(spec_pairs) else ('', '')
            rows.append([left[0] + ':', safe(left[1]), right[0] + (':' if right[0] else ''), safe(right[1])])
        story.append(styled_table(rows, [1.25*inch, 2.35*inch, 1.25*inch, 2.35*inch], header=False, font_size=8))

    if sections.get('performance', True):
        story.append(Paragraph('Performance Statistics', section_style))
        perf = [('Metric', 'Latest', 'Average', 'Peak')]
        for key, label, unit in [('ping','Ping','ms'), ('cpu','CPU','%'), ('ram','RAM','%'), ('temperature','Temperature','°C')]:
            node = stats.get(key) if isinstance(stats, dict) else None
            if isinstance(node, dict):
                latest, average, peak = metric_summary(node)
                if latest is not None or average is not None or peak is not None:
                    perf.append([label, f'{safe(latest)} {unit}', f'{safe(average)} {unit}', f'{safe(peak)} {unit}'])
        if len(perf) == 1:
            perf.append(['No summary telemetry', 'N/A', 'N/A', 'N/A'])
        story.append(styled_table(perf, [2.2*inch, 1.55*inch, 1.55*inch, 1.55*inch], header=True, font_size=7.5))

    if sections.get('interfaces', True):
        story.append(Paragraph('PORT Information', section_style))
        if interfaces:
            rows = [['Port Display Name', 'Interface Alias Description', 'Link Status', 'PoE Mode', 'Current Load (Power)']]
            for index, face in enumerate(interfaces):
                fi = face.get('identification', {}) if isinstance(face.get('identification'), dict) else face
                fs = face.get('status', {}) if isinstance(face.get('status'), dict) else face
                fp = face.get('poe', {}) if isinstance(face.get('poe'), dict) else face
                fm = face.get('statistics', {}) if isinstance(face.get('statistics'), dict) else face
                name_v = fi.get('displayName') or fi.get('name') or face.get('name') or face.get('id') or f'Port {index + 1}'
                desc_v = fi.get('description') or face.get('description') or '—'
                status_v = fs.get('status') or face.get('state') or 'N/A'
                poe_v = fp.get('output') or face.get('poeMode') or face.get('poe') or 'N/A'
                if str(poe_v).lower() == 'active':
                    poe_v = 'PoE+'
                power_v = fm.get('poePower') if isinstance(fm, dict) else None
                power_v = power_v if power_v is not None else face.get('poePower')
                rows.append([f'Port {name_v}', desc_v, str(status_v).upper(), str(poe_v).upper(), f'{power_v} W' if isinstance(power_v, (int, float)) else safe(power_v)])
            story.append(styled_table(rows, [1.55*inch, 1.85*inch, 1.25*inch, 1.15*inch, 1.35*inch], True, 7.2, BLUE))
        else:
            story.append(Paragraph('UISP returned no interface list for this device.', meta_style))

    if sections.get('topology', True):
        uplinks, downlinks = topology_rows(dataset.get('data_links'), device_id)
        if uplinks or downlinks:
            story.append(Paragraph('Network Topology — Uplink & Downlink', section_style))
            story.append(Paragraph(
                'Physical data-link relationships returned by UISP for the selected device. '
                'The report preserves the UISP port, remote device/link name, state and link type.',
                meta_style,
            ))

            if uplinks:
                story.append(Paragraph('Uplink', meta_style))
                story.append(styled_table(
                    [['Port', 'Uplink Device / Link', 'Status', 'Type']] + uplinks,
                    [1.0*inch, 4.1*inch, 1.0*inch, 1.0*inch],
                    True, 7.2, BLUE,
                ))
            else:
                story.append(Paragraph('Uplink: No UISP data link returned for this device.', meta_style))

            if downlinks:
                story.append(Spacer(1, 8))
                story.append(Paragraph('Downlink', meta_style))
                story.append(styled_table(
                    [['Port', 'Downlink Device / Link', 'Status', 'Type']] + downlinks,
                    [1.0*inch, 4.1*inch, 1.0*inch, 1.0*inch],
                    True, 7.2, DARK_GRAY,
                ))
            else:
                story.append(Paragraph('Downlink: No UISP data links returned for this device.', meta_style))

    # GPON/ONU summary: UISP exposes several fiber-specific fields that do
    # not belong in the generic device specification or port table. Keep them
    # in a dedicated section so Fiber NanoG/ONU reports mirror the UISP page.
    if is_gpon_device(device, detail):
        gpon_summary = gpon_summary_rows(device, detail, extra)
        if gpon_summary:
            story.append(Paragraph('GPON / Fiber ONU Overview', section_style))
            story.append(styled_table(
                [['Field', 'UISP Value']] + gpon_summary,
                [2.55*inch, 4.55*inch],
                True,
                7.0,
                DARK_GREEN,
            ))

    # Wireless/PTMP summary: keep selected-device link fields separate from
    # connected subscriber/station diagnostics so directions and values are not mixed.
    ap_summary = access_point_summary_rows(device, detail, extra, wireless_stations, interfaces)
    if sections.get('subscribers', True) and ap_summary and wireless_stations:
        story.append(Paragraph('PTMP / Wireless Link Overview', section_style))
        story.append(styled_table(
            [['Field', 'UISP Value']] + ap_summary,
            [2.55*inch, 4.55*inch],
            True,
            7.0,
            DARK_GREEN,
        ))

    # Subscriber information is device-type dependent. Switches, routers and
    # other infrastructure devices normally do not have subscriber/client
    # profiles, so do not print an empty "Active Connected Subscribers" section
    # for them. The section appears only when UISP actually returned subscriber
    # or wireless-station records for this selected device.
    has_subscriber_data = bool(subscribers or wireless_stations)
    if sections.get('subscribers', True) and has_subscriber_data:
        story.append(Paragraph('Active Connected Subscribers Profile', section_style))
        rows = [['Subscriber Name', 'Device Model', 'IP Address', 'Signal']]
        for item in subscribers:
            sid = item.get('identification', {}) if isinstance(item.get('identification'), dict) else {}
            sov = item.get('overview', {}) if isinstance(item.get('overview'), dict) else {}
            rows.append([
                sid.get('name') or sid.get('hostname') or item.get('name') or item.get('hostname') or 'Client',
                sid.get('modelName') or sid.get('model') or item.get('modelName') or item.get('model') or 'N/A',
                str(
                    item.get('ipAddress')
                    or sid.get('ip')
                    or item.get('ip')
                    or recursive_find(item, ('ipAddress', 'ip', 'address'))
                    or 'N/A'
                ).split('/')[0],
                f'{sov.get("signal")} dBm' if sov.get('signal') is not None else safe(item.get('signal')),
            ])
        story.append(styled_table(rows, [2.15*inch, 1.65*inch, 1.55*inch, 1.15*inch], True, 7.5, DARK_GRAY))

    # Wireless station diagnostics are deliberately separate from the compact
    # subscriber table. UISP exposes much richer radio/link data here (MCS,
    # expected signal, capacity, frame length, DL/UL ratio, EIRP, byte counts,
    # connection time, etc.) and these fields should not be lost in the PDF.
    if sections.get('subscribers', True) and wireless_stations:
        stations = wireless_stations
        if stations:
            story.append(Paragraph('Wireless Station & Link Diagnostics', section_style))
            for station_index, station in enumerate(stations, start=1):
                station_label = station.get('name') or station.get('displayName') or station.get('ipAddress') or f'Station {station_index}'
                story.append(Paragraph(f'Station {station_index}: {safe(station_label)}', meta_style))
                station_rows = station_diagnostic_rows(station, device, detail, interfaces)
                story.append(styled_table(
                    [['Station / Link Field', 'UISP Value']] + station_rows,
                    [2.55*inch, 4.55*inch],
                    True,
                    7.0,
                    DARK_GREEN,
                ))
                if station_index < len(stations):
                    story.append(Spacer(1, 8))

    if sections.get('outages', True):
        story.append(Paragraph('System Interruption & Network Outage Logs', section_style))
        rows = [['Event ID', 'Type', 'From (Start)', 'To (End)', 'Duration']]
        for outage in outages[:100]:
            if not isinstance(outage, dict):
                continue
            start = outage.get('startTimestamp') or outage.get('startTime')
            end = outage.get('endTimestamp') or outage.get('endTime')
            duration = outage.get('aggregatedTime') or outage.get('duration')
            if isinstance(duration, (int, float)):
                seconds = int(duration / 1000) if duration > 10000 else int(duration)
                h, rem = divmod(seconds, 3600)
                m, s = divmod(rem, 60)
                duration = f'{h}h {m}m' if h else f'{m}m {s}s'
            rows.append([safe(outage.get('id', 'N/A'))[:8], str(outage.get('type', 'OUTAGE')).upper(), parse_iso(start), 'Ongoing' if not end or outage.get('inProgress') else parse_iso(end), safe(duration)])
        if len(rows) == 1:
            rows.append(['No outage history returned for this selected device.', '', '', '', ''])
        story.append(styled_table(rows, [0.95*inch, 0.75*inch, 1.55*inch, 1.55*inch, 1.15*inch], True, 7.2, DARK_GRAY))

    if sections.get('charts', True):
        work_dir = Path(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        charts = discover_metric_charts(stats, work_dir, extra=extra, device=device, detail=detail, interfaces=interfaces)
        if charts:
            story.append(PageBreak())
            story.append(Paragraph('UISP Live Device Performance Diagnostics Audit', title_style))
            story.append(Paragraph(
                f'Target Device UUID: {safe(device_id)} &nbsp; • &nbsp; Period Window: {safe(dataset.get("period", "N/A")).upper()} &nbsp; • &nbsp; Run Date: {safe(dataset.get("collected_at"))}',
                meta_style,
            ))
            for chart in charts:
                story.append(Image(str(chart), width=540, height=189))
                story.append(Spacer(1, 8))

    if sections.get('additional', True):
        story.append(PageBreak())
        story.append(Paragraph('Additional UISP Information', title_style))
        story.append(Paragraph(
            'This section promotes useful fields returned by UISP that are not already represented in the main report. Values are read from the selected device response, device detail response, interfaces and optional endpoint responses.',
            meta_style,
        ))

        # 1. Curated device/network information.
        device_rows = additional_device_rows(device, detail, extra, normalized)
        if device_rows:
            story.append(Paragraph('Device, Network & Link Details', section_style))
            story.append(styled_table([['Field', 'UISP Value']] + device_rows, [2.4*inch, 4.7*inch], True, 7.2, DARK_GREEN))

        # 2. Interface addressing/health that the compact PORT table cannot show.
        int_rows = interface_additional_rows(interfaces)
        if int_rows:
            story.append(Spacer(1, 8))
            story.append(Paragraph('Interface Addressing & Counters', section_style))
            story.append(styled_table(
                [['Interface', 'Type', 'Addresses', 'MTU', 'Speed', 'State', 'RX', 'TX', 'Errors']] + int_rows,
                [1.05*inch, .55*inch, 1.75*inch, .45*inch, .65*inch, .65*inch, .65*inch, .65*inch, .55*inch],
                True, 6.1, BLUE,
            ))

        # 3. Physical topology returned by the Data Links endpoint.
        topology_payload = dataset.get('data_links')
        topology_flat = non_timeseries_flatten(topology_payload, 'data_links', max_rows=120)
        if topology_flat:
            story.append(Spacer(1, 8))
            story.append(Paragraph('UISP Physical Data Links (Source)', section_style))
            story.append(styled_table(
                [['UISP Field', 'Value']] + topology_flat,
                [3.0*inch, 4.1*inch],
                True, 6.2, DARK_GREEN,
            ))

        # 4. Endpoint audit makes optional data visible without dumping JSON blobs.
        endpoint_rows = [['Endpoint', 'Status', 'Purpose / Result']]
        for endpoint in dataset.get('endpoints', []):
            if not isinstance(endpoint, dict):
                continue
            result = 'Successful response' if endpoint.get('ok') else safe(endpoint.get('error'))
            endpoint_rows.append([endpoint.get('name'), 'OK' if endpoint.get('ok') else 'FAILED', result])
        if len(endpoint_rows) > 1:
            story.append(Spacer(1, 8))
            story.append(Paragraph('UISP Endpoint Audit', section_style))
            story.append(styled_table(endpoint_rows, [1.7*inch, .8*inch, 4.6*inch], True, 6.8, DARK_GRAY))

        # 4. Preserve additional scalar/non-timeseries data, but avoid pages of x/y points.
        raw_rows = []
        for label, payload in [
            ('Device Response', device),
            ('Device Detail Response', detail),
            ('Statistics Response', stats),
            ('Interfaces Response', dataset.get('interfaces') or {}),
            ('Outages Response', dataset.get('outages') or {}),
        ]:
            for key, value in non_timeseries_flatten(payload, label, 220):
                raw_rows.append([key, value])
        for label, payload in extra.items():
            for key, value in non_timeseries_flatten(payload, pretty_key(label), 120):
                raw_rows.append([key, value])

        # Deduplicate repeated fields produced by device + detail responses.
        seen = set()
        deduped = []
        for row in raw_rows:
            marker = (str(row[0]), str(row[1]))
            if marker not in seen:
                seen.add(marker)
                deduped.append(row)

        if deduped:
            story.append(Spacer(1, 8))
            story.append(Paragraph('Supplementary UISP Field Audit', section_style))
            story.append(Paragraph(
                'Nested telemetry arrays are represented by their point counts above rather than printed as thousands of unreadable x/y rows. The underlying live values remain available to the charts and summary statistics.',
                meta_style,
            ))
            story.append(styled_table(
                [['UISP Field', 'Value']] + deduped,
                [3.0*inch, 4.1*inch], True, 6.2, DARK_GREEN,
            ))


def add_page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont('Helvetica', 7)
    canvas.setFillColor(colors.HexColor('#6c757d'))
    canvas.drawRightString(letter[0] - 36, 20, f'Page {doc.page}')
    canvas.restoreState()


def generate_complete_report(datasets, report_dir: Path, report_id: str, sections: dict) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    output = report_dir / f'{report_id}.pdf'
    work_dir = report_dir / f'{report_id}_charts'
    work_dir.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output), pagesize=letter,
        rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36,
        title='UISP Network Infrastructure Report',
        author='UISP Report Generator',
    )
    story = []
    for index, dataset in enumerate(datasets, 1):
        render_device_report(dataset, story, work_dir / f'device_{index}', sections, index if index > 1 else None)
    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    return output
