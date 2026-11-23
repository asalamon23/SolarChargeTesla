import os,time,math,threading,requests
from collections import deque
from flask import Flask,request,jsonify,render_template_string
app=Flask(__name__)
state={'mode':'solar','solar_w':6500,'grid_w':-4200,'amps':0,'charging':False,'status':'Simulation','connected':False,'last_update':time.time(),'error':'','manual_amps':10}
settings={'phases':3,'voltage':230,'min_amps':6,'max_amps':16,'reserve_w':450,'grid_allowance_w':0,'interval_s':30,'min_change_s':90,'start_hold_s':120,'stop_hold_s':45}
history=deque(maxlen=100); lock=threading.RLock(); last_command=0; candidate_since=time.time(); candidate=None
# FusionSolar adapter: optional gateway URL must return {solar_w: number, grid_w: number}, where grid_w > 0 is import.
# Can be backed by a Huawei-approved northbound API bridge or local Modbus meter bridge.
def get_meter():
    url=os.getenv('METER_BRIDGE_URL','')
    if not url: return None
    r=requests.get(url,headers={'Authorization':'Bearer '+os.getenv('METER_BRIDGE_TOKEN','')},timeout=8);r.raise_for_status();j=r.json()
    solar=float(j['solar_w']);grid=float(j['grid_w'])
    if not math.isfinite(solar) or not math.isfinite(grid): raise ValueError('Non-finite meter reading')
    return solar,grid

def tesla_command(action,amps=None):
    # Signed Vehicle Command Proxy is required for set_charging_amps on supported vehicles.
    base=os.getenv('TESLA_PROXY_URL','').rstrip('/'); vin=os.getenv('TESLA_VIN',''); token=os.getenv('TESLA_ACCESS_TOKEN','')
    if not (base and vin and token): raise RuntimeError('Tesla proxy/VIN/access token not configured')
    path={'amps':'set_charging_amps','start':'charge_start','stop':'charge_stop'}[action]
    body={'charging_amps':int(amps)} if action=='amps' else {}
    r=requests.post(f'{base}/api/1/vehicles/{vin}/command/{path}',json=body,headers={'Authorization':'Bearer '+token},timeout=20)
    r.raise_for_status();data=r.json()
    if data.get('response',{}).get('result') is False: raise RuntimeError(str(data['response']))
    return data

def target(s):
    if s['mode']=='off':return 0
    if s['mode']=='manual':return max(settings['min_amps'],min(settings['max_amps'],int(s['manual_amps'])))
    # grid_w is net grid import (+) or export (-). When EV already charging,
    # adding existing EV load to export yields the achievable total EV charging power.
    existing_w=s['amps']*settings['phases']*settings['voltage'] if s['charging'] else 0
    available=existing_w-s['grid_w']-settings['reserve_w']
    if s['mode']=='hybrid': available+=settings['grid_allowance_w']
    amps=math.floor(max(0,available)/(settings['phases']*settings['voltage']))
    return max(0,min(settings['max_amps'],amps)) if amps>=settings['min_amps'] else 0

def cycle():
    global last_command,candidate_since,candidate
    with lock:
        try:
            meter=get_meter()
            if meter:
                state['solar_w'],state['grid_w']=meter;state['last_update']=time.time()
            elif os.getenv('METER_BRIDGE_URL'): raise RuntimeError('Meter bridge not responding')
            # Never issue real commands from simulated meter readings.
            live=bool(meter and os.getenv('TESLA_PROXY_URL') and os.getenv('TESLA_VIN') and os.getenv('TESLA_ACCESS_TOKEN'))
            state['connected']=live;state['status']='Live' if live else 'Simulation'
            if time.time()-state['last_update']>90: raise RuntimeError('Stale meter data')
            wanted=target(state)
            if wanted!=candidate: candidate=wanted;candidate_since=time.time()
            hold=settings['start_hold_s'] if wanted>0 and not state['charging'] else settings['stop_hold_s'] if wanted==0 else 0
            if time.time()-candidate_since>=hold and time.time()-last_command>=settings['min_change_s'] and (wanted!=state['amps'] or (wanted==0 and state['charging'])):
                if live:
                    if wanted==0: tesla_command('stop')
                    else:
                        tesla_command('amps',wanted)
                        if not state['charging']:tesla_command('start')
                state['amps']=wanted;state['charging']=wanted>0;last_command=time.time()
            state['error']=''
        except Exception as e:
            state['error']=str(e);state['status']='Error'
            # Fail safe: attempt to stop charging on live meter failures; never rely on this alone for electrical safety.
            if state['connected']:
                try:tesla_command('stop');state['charging']=False;state['amps']=0
                except Exception as stop_error:state['error']+='; stop failed: '+str(stop_error)
        history.append({'t':int(time.time()),'solar_w':state['solar_w'],'grid_w':state['grid_w'],'amps':state['amps']})

def worker():
    while True:
        cycle();time.sleep(settings['interval_s'])

HTML='''<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SolarCharge</title><style>
:root{font-family:system-ui,-apple-system,sans-serif;color:#172b31;background:#f2f7f5}*{box-sizing:border-box}body{margin:0}.wrap{max-width:920px;margin:auto;padding:28px 16px}header{display:flex;justify-content:space-between;align-items:center}h1{font-size:29px;margin:0}small,.muted{color:#65777b}.pill{background:#d9f4e5;color:#17653b;padding:7px 12px;border-radius:20px;font-size:12px;font-weight:700}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:24px 0}.card{background:white;border-radius:18px;padding:22px;box-shadow:0 3px 16px #183c3110}.value{font-size:32px;font-weight:750;margin:10px 0}.label{font-size:13px;color:#6a7d80}.modes{display:flex;gap:9px;flex-wrap:wrap}button{border:1px solid #c8d7d1;border-radius:11px;background:white;padding:12px 16px;cursor:pointer;font-weight:650;color:#25423c}button.active{background:#147c54;color:white;border-color:#147c54}.line{display:flex;justify-content:space-between;align-items:center;gap:12px}.range{width:100%;accent-color:#147c54}.notice{padding:14px;background:#fff5df;border-radius:12px;font-size:13px;margin-top:15px}.err{color:#aa3030}.two{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:650px){.grid,.two{grid-template-columns:1fr}.value{font-size:28px}} </style><div class="wrap"><header><div><h1>☀ SolarCharge</h1><small>FusionSolar × Tesla Model Y</small></div><span class="pill" id="status">Loading</span></header><div class="grid"><div class="card"><div class="label">☀ Solar production</div><div class="value" id="solar">—</div><small>Huawei inverter</small></div><div class="card"><div class="label">⚡ Grid balance</div><div class="value" id="grid">—</div><small id="gridlabel">Import / export</small></div><div class="card"><div class="label">🚗 Tesla charging</div><div class="value" id="amps">—</div><small id="power">3-phase · 230 V/phase</small></div></div><div class="two"><section class="card"><h3>Charging mode</h3><div class="modes"><button data-mode="solar">☀ Solar only</button><button data-mode="hybrid">⚡ Solar + grid</button><button data-mode="manual">✋ Manual</button><button data-mode="off">■ Off</button></div><p class="muted" id="description"></p><div id="manualBox" style="display:none"><div class="line"><b>Manual charging current</b><b id="manualValue">10 A</b></div><input class="range" id="manual" type="range" min="6" max="16" value="10"></div></section><section class="card"><h3>System overview</h3><div class="line"><span>Inverter & smart meter</span><b id="meter">Demo readings</b></div><hr><div class="line"><span>Vehicle</span><b>Model Y</b></div><hr><div class="line"><span>Supply</span><b>3-phase</b></div><hr><div class="line"><span>Charge state</span><b id="chargeState">—</b></div><div class="notice" id="notice">Demo mode: no commands are sent to your car.</div></section></div><p class="muted" style="font-size:12px">For safety, live mode needs a verified smart-meter bridge, Tesla OAuth token and signed-command proxy. Current limits must match your installation.</p></div><script>
const descriptions={solar:'Charge only from surplus solar. Pause when surplus falls below the three-phase minimum.',hybrid:'Use surplus solar and a configurable grid allowance.',manual:'Set the requested Tesla charging current yourself.',off:'Stop charging.'};
async function post(data){let r=await fetch('/api/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});if(!r.ok)alert((await r.json()).error);await refresh()}
async function refresh(){let d=await(await fetch('/api/state')).json();document.getElementById('solar').textContent=(d.solar_w/1000).toFixed(2)+' kW';document.getElementById('grid').textContent=(Math.abs(d.grid_w)/1000).toFixed(2)+' kW';document.getElementById('gridlabel').textContent=d.grid_w<0?'Exporting to grid':'Importing from grid';document.getElementById('amps').textContent=d.amps+' A';document.getElementById('power').textContent=(d.amps*3*230/1000).toFixed(2)+' kW charging power';document.getElementById('status').textContent=d.status;document.getElementById('meter').textContent=d.connected?'Live':'Simulation';document.getElementById('chargeState').textContent=d.charging?'Charging':'Paused';document.getElementById('description').textContent=descriptions[d.mode];document.querySelectorAll('[data-mode]').forEach(b=>b.classList.toggle('active',b.dataset.mode===d.mode));document.getElementById('manualBox').style.display=d.mode==='manual'?'block':'none';document.getElementById('manual').value=d.manual_amps;document.getElementById('manualValue').textContent=d.manual_amps+' A';document.getElementById('notice').textContent=d.error|| (d.connected?'Live mode: commands enabled':'Demo mode: no commands are sent to your car.');}
document.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>post({mode:b.dataset.mode}));document.getElementById('manual').onchange=e=>post({manual_amps:+e.target.value});refresh();setInterval(refresh,5000);
</script></html>'''
@app.get('/')
def index():return render_template_string(HTML)
@app.get('/api/state')
def api_state():
    with lock:return jsonify(dict(state,settings=settings))
@app.post('/api/control')
def control():
    d=request.get_json(silent=True) or {}
    with lock:
        if 'mode' in d:
            if d['mode'] not in ('solar','hybrid','manual','off'):return jsonify(error='Invalid mode'),400
            state['mode']=d['mode']
        if 'manual_amps' in d:
            try:a=int(d['manual_amps'])
            except (TypeError,ValueError):return jsonify(error='Invalid amperage'),400
            if not settings['min_amps']<=a<=settings['max_amps']:return jsonify(error='Current out of range'),400
            state['manual_amps']=a
        return jsonify(ok=True)
@app.post('/api/demo')
def demo():
    if os.getenv('METER_BRIDGE_URL'):return jsonify(error='Disabled with live meter'),403
    d=request.get_json(silent=True) or {}
    with lock:
        try:
            for key in ('solar_w','grid_w'):
                if key in d:
                    val=float(d[key]);assert math.isfinite(val) and abs(val)<100000
                    state[key]=val
            state['last_update']=time.time()
        except (ValueError,TypeError,AssertionError):return jsonify(error='Invalid demo reading'),400
    return jsonify(ok=True)
if __name__=='__main__':
    threading.Thread(target=worker,daemon=True).start()
    app.run(host='127.0.0.1',port=int(os.getenv('PORT','8080')),debug=False)
