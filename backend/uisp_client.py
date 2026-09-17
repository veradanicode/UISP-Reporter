import os
from typing import Any, Dict, List, Optional, Tuple

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class UISPError(RuntimeError):
    pass


class UISPClient:
    """Small, source-of-truth client: every value in a report comes from UISP."""

    def __init__(self, base_url: str, token: str, verify_ssl: bool = False, timeout: int = 35):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({'x-auth-token': token, 'Accept': 'application/json'})

    def get(self, path: str, params: Optional[dict] = None) -> Any:
        if not self.token:
            raise UISPError('UISP_API_TOKEN is not configured.')
        url = f'{self.base_url}{path}'
        try:
            r = self.session.get(url, params=params, verify=self.verify_ssl, timeout=self.timeout)
        except requests.RequestException as exc:
            raise UISPError(f'UISP connection failed: {exc}') from exc
        if not r.ok:
            body = r.text[:1200]
            raise UISPError(f'UISP API {r.status_code} for {path}: {body}')
        try:
            return r.json()
        except ValueError as exc:
            raise UISPError(f'UISP returned non-JSON data for {path}.') from exc

    def try_get(self, path: str, params: Optional[dict] = None) -> Tuple[bool, Any, Optional[str]]:
        try:
            return True, self.get(path, params), None
        except UISPError as exc:
            return False, None, str(exc)

    def list_devices(self) -> List[dict]:
        payload = self.get('/nms/api/v2.1/devices')
        return as_list(payload, ('data', 'devices', 'items'))

    def collect_device(self, device_id: str, period: str = '24h') -> dict:
        period_cfg = {
            '1h': {'interval': 'hour', 'period': '3600000'},
            '6h': {'interval': 'hour', 'period': '21600000'},
            '24h': {'interval': 'hour', 'period': '86400000'},
            '7d': {'interval': 'hour', 'period': '604800000'},
        }.get(period, {'interval': 'hour', 'period': '86400000'})

        endpoints = []
        def required(name, path, params=None):
            ok, data, err = self.try_get(path, params)
            endpoints.append({'name': name, 'path': path, 'params': params or {}, 'ok': ok, 'error': err})
            if not ok:
                raise UISPError(err or f'Unable to collect {name}.')
            return data

        def optional(name, path, params=None):
            ok, data, err = self.try_get(path, params)
            endpoints.append({'name': name, 'path': path, 'params': params or {}, 'ok': ok, 'error': err})
            return data if ok else None

        device = required('device', f'/nms/api/v2.1/devices/{device_id}')
        detail = required('detail', f'/nms/api/v2.1/devices/{device_id}/detail', {'withStations': 'true'})
        stats = required('statistics', f'/nms/api/v2.1/devices/{device_id}/statistics', period_cfg)
        interfaces = required('interfaces', f'/nms/api/v2.1/devices/{device_id}/interfaces')
        outages = required('outages', '/nms/api/v2.1/outages', {'deviceId': device_id, 'page': 1, 'count': 200})

        # UISP stores physical topology connections as Data Links.  This is the
        # source for the Uplink/Downlink port relationships shown in the UISP UI.
        # It is optional because some older UISP installations or device types
        # may not expose a data link for the selected device.
        data_links = optional('data_links', f'/nms/api/v2.1/data-links/device/{device_id}')

        # These are deliberately probes, not assumptions about the device model.
        # Only successful UISP responses are included in the final dataset.
        optional_endpoints = [
            ('device_status', f'/nms/api/v2.1/devices/{device_id}/status'),
            ('device_config', f'/nms/api/v2.1/devices/{device_id}/config'),
            ('device_health', f'/nms/api/v2.1/devices/{device_id}/health'),
            ('mac_table', f'/nms/api/v2.1/devices/{device_id}/mac-table'),
        ]
        extra = {}
        for name, path in optional_endpoints:
            value = optional(name, path)
            if value is not None:
                extra[name] = value

        # Probe the common wireless resources only when the selected device declares
        # an AirMAX/AirFiber/wireless role or type. A failed probe is simply recorded.
        identity = device.get('identification') if isinstance(device, dict) else {}
        identity = identity if isinstance(identity, dict) else {}
        role_text = ' '.join(str(identity.get(k, '')) for k in ('role', 'type', 'modelName', 'model')).lower()
        wireless = any(x in role_text for x in ('airmax', 'airfiber', 'wireless', 'access point', 'station', 'wave'))
        if wireless:
            for name, path in [
                ('wireless_stations', f'/nms/api/v2.1/devices/airmaxes/{device_id}/stations'),
                ('wireless_config', f'/nms/api/v2.1/devices/airmaxes/{device_id}/config/wireless'),
                ('site_survey', f'/nms/api/v2.1/devices/airmaxes/{device_id}/site-survey'),
                ('frequency_bands', f'/nms/api/v2.1/devices/airmaxes/{device_id}/frequency-bands'),
            ]:
                value = optional(name, path)
                if value is not None:
                    extra[name] = value

        return {
            'device_id': device_id,
            'period': period,
            'collected_at': __import__('datetime').datetime.now().isoformat(timespec='seconds'),
            'endpoints': endpoints,
            'device': device,
            'detail': detail,
            'statistics': stats,
            'interfaces': interfaces,
            'outages': outages,
            'data_links': data_links,
            'extra': extra,
        }


def as_list(payload: Any, keys=('data', 'items')) -> List[dict]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def device_id(item: dict) -> Optional[str]:
    if not isinstance(item, dict):
        return None
    ident = item.get('identification') if isinstance(item.get('identification'), dict) else {}
    return item.get('id') or ident.get('id')


def device_name(item: dict) -> str:
    if not isinstance(item, dict):
        return 'Unknown device'
    ident = item.get('identification') if isinstance(item.get('identification'), dict) else {}
    overview = item.get('overview') if isinstance(item.get('overview'), dict) else {}
    return str(ident.get('name') or overview.get('name') or item.get('name') or item.get('hostname') or device_id(item) or 'Unknown device')
