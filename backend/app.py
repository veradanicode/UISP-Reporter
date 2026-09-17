import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

from uisp_client import UISPClient, UISPError, device_id, device_name
from report_engine import generate_complete_report

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent
REPORT_DIR = BASE_DIR / 'reports'
REPORT_DIR.mkdir(parents=True, exist_ok=True)

UISP_URL = os.getenv('UISP_URL', 'https://vdtaccess.uisp.com').rstrip('/')
TOKEN = os.getenv('UISP_API_TOKEN', '')
VERIFY_SSL = os.getenv('UISP_VERIFY_SSL', 'false').lower() in ('1', 'true', 'yes', 'on')
PORT = int(os.getenv('PORT', '5000'))

client = UISPClient(UISP_URL, TOKEN, VERIFY_SSL)
app = Flask(__name__)
CORS(app)

DEFAULT_SECTIONS = {
    'device_information': True,
    'performance': True,
    'interfaces': True,
    'subscribers': True,
    'outages': True,
    'charts': True,
    'additional': True,
}


def err(message, code=502):
    return jsonify({'error': message}), code


@app.get('/api/health')
def health():
    return jsonify({
        'ok': True,
        'configured': bool(TOKEN),
        'uisp_url': UISP_URL,
        'device_id_required_in_env': False,
    })


@app.get('/api/devices')
def devices():
    try:
        items = client.list_devices()
        result = []
        for item in items:
            did = device_id(item)
            if not did:
                continue
            ident = item.get('identification') if isinstance(item.get('identification'), dict) else {}
            overview = item.get('overview') if isinstance(item.get('overview'), dict) else {}
            result.append({
                'id': did,
                'name': device_name(item),
                'model': ident.get('modelName') or ident.get('model') or item.get('model'),
                'type': ident.get('type') or item.get('type'),
                'role': ident.get('role') or item.get('role'),
                'ip': item.get('ip') or item.get('ipAddress') or overview.get('ipAddress'),
                'mac': item.get('mac') or ident.get('mac') or item.get('macAddress'),
                'status': overview.get('status') or item.get('status'),
            })
        return jsonify(result)
    except UISPError as exc:
        return err(str(exc))


@app.get('/api/devices/<device_id_value>/inspect')
def inspect_device(device_id_value):
    period = request.args.get('period', '24h')
    try:
        data = client.collect_device(device_id_value, period)
        return jsonify(data)
    except UISPError as exc:
        return err(str(exc))


@app.post('/api/reports/generate')
def generate():
    body = request.get_json(silent=True) or {}
    ids = body.get('device_ids') or []
    if not isinstance(ids, list) or not ids:
        return err('Select at least one device from the UISP device list.', 400)

    # The client receives IDs selected from /api/devices. There is deliberately
    # no device ID setting in .env and no fallback device ID in this application.
    ids = [str(value).strip() for value in ids if str(value).strip()]
    if not ids:
        return err('Select at least one device from the UISP device list.', 400)

    period = body.get('period', '24h')
    if period not in ('1h', '6h', '24h', '7d'):
        return err('Unsupported period. Use 1h, 6h, 24h or 7d.', 400)

    sections = {**DEFAULT_SECTIONS, **(body.get('sections') or {})}
    report_id = uuid.uuid4().hex

    try:
        datasets = []
        errors = []
        for did in ids:
            try:
                datasets.append(client.collect_device(did, period))
            except UISPError as exc:
                errors.append(f'{did}: {exc}')

        if not datasets:
            return err('No selected device could be collected. ' + ' | '.join(errors), 502)

        pdf = generate_complete_report(datasets, REPORT_DIR, report_id, sections)
        return jsonify({
            'report_id': report_id,
            'filename': pdf.name,
            'collected_devices': len(datasets),
            'failed_devices': errors,
            'preview_url': f'/api/reports/{report_id}/preview',
            'download_url': f'/api/reports/{report_id}/download',
        })
    except Exception as exc:
        app.logger.exception('Report generation failed')
        return err(str(exc))


@app.get('/api/reports/<report_id>/preview')
def preview(report_id):
    path = REPORT_DIR / f'{report_id}.pdf'
    if not path.exists():
        return err('Report not found', 404)
    return send_file(path, mimetype='application/pdf', as_attachment=False, download_name=path.name)


@app.get('/api/reports/<report_id>/download')
def download(report_id):
    path = REPORT_DIR / f'{report_id}.pdf'
    if not path.exists():
        return err('Report not found', 404)
    return send_file(path, mimetype='application/pdf', as_attachment=True, download_name=path.name)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT, debug=True)
