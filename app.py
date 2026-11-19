from flask import Flask, render_template, request, jsonify, send_file
import sqlite3, csv, json
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from statistics import median
BASE=Path(__file__).resolve().parent; DB=BASE/'rideops.sqlite3'; CSV=BASE/'data'/'rideops_support_tickets.csv'
app=Flask(__name__)
SLA_HOURS=72
CHECKS={
'Live tracking / GPS incorrect':['Capture trip ID, timestamp and affected route','Verify driver app connectivity and version','Compare GPS position with another trip/device','Check service status and known incidents','Attach route screenshot and evidence'],
'Roster / booking not syncing':['Confirm employee and booking IDs','Check roster effective date and cutoff','Verify latest roster sync timestamp','Compare booking in admin and client views','Attach affected shift and mismatch evidence'],
'Report export failing':['Confirm report name and date range','Retry with a smaller date range','Check format and browser download permissions','Compare export with on-screen report','Capture exact error and screenshot'],
'Cab delay / no-show complaint':['Confirm trip ID and scheduled pickup time','Check driver assignment and trip status','Review notification history','Contact operations owner if trip is active','Record client impact and evidence'],
'Billing / invoice discrepancy':['Capture invoice number and billing period','Compare line items with trip records','Check rate card, taxes and adjustments','Check whether multiple trips are affected','Attach invoice and trip references'],
'OTP / boarding issue':['Verify registered phone and trip ID','Check OTP expiry and resend attempts','Confirm device network and app version','Check whether multiple users are affected','Capture timestamp and exact error']}
DEFAULT=['Confirm affected user or record ID','Capture exact timestamp and error','Check known issue and service status','Complete documented L1 troubleshooting','Attach evidence before escalation']
def db():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init():
 global SLA_HOURS
 with db() as c:
  c.executescript("CREATE TABLE IF NOT EXISTS ticket_state(id TEXT PRIMARY KEY,status TEXT,agent TEXT,notes TEXT); CREATE TABLE IF NOT EXISTS checklist(id TEXT PRIMARY KEY,items TEXT); CREATE TABLE IF NOT EXISTS actions(seq INTEGER PRIMARY KEY AUTOINCREMENT,ticket_id TEXT,action TEXT,notes TEXT,actor TEXT,created TEXT); CREATE TABLE IF NOT EXISTS config(k TEXT PRIMARY KEY,v TEXT);")
  c.execute("INSERT OR IGNORE INTO config VALUES('engineering_sla','72')"); c.execute("INSERT OR IGNORE INTO config VALUES('policy','Balanced')")
  SLA_HOURS=int(c.execute("SELECT v FROM config WHERE k='engineering_sla'").fetchone()[0])
def raw():
 with open(CSV,encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
 with db() as c: states={r['id']:dict(r) for r in c.execute('select * from ticket_state')}
 for t in rows:
  s=states.get(t['ticket_id'],{}); t['current_status']=s.get('status') or t['status']; t['current_agent']=s.get('agent') or t['assigned_agent']; t['notes']=s.get('notes') or ''
  t['reopen_count']=int(t.get('reopen_count') or 0); t['eng_handoffs']=int(t.get('eng_handoffs') or 0); t['csat_score']=float(t['csat_score']) if t.get('csat_score') else None
 return rows
def age(t):
 try:return max(0,(datetime(2026,9,30,23,59)-datetime.strptime(t['created_at'],'%Y-%m-%d %H:%M')).total_seconds()/3600)
 except:return 0
def score(t):return {'P1':40,'P2':25,'P3':10,'P4':0}.get(t['priority'],0)+min(age(t),240)/6+10*t['reopen_count']+(15 if t['current_status']=='Open - with Engineering' and age(t)>SLA_HOURS else 0)
def metrics(ts):
 esc=[t for t in ts if t['escalated_to_eng']=='Yes']; ret=[t for t in esc if t.get('eng_outcome') in ('Insufficient info - returned to L1','Config issue - returned to L1')]
 resolved=[]
 for t in ts:
  if t.get('final_closed_at'):
   try:resolved.append((datetime.strptime(t['final_closed_at'],'%Y-%m-%d %H:%M')-datetime.strptime(t['created_at'],'%Y-%m-%d %H:%M')).total_seconds()/3600)
   except:pass
 cs=[t['csat_score'] for t in ts if t['csat_score'] is not None]; op=[t for t in ts if t['current_status'].startswith('Open')]
 return {'total':len(ts),'open':len(op),'p1':sum(t['priority']=='P1' for t in op),'eng_open':sum(t['current_status']=='Open - with Engineering' for t in op),'eng_over72':sum(t['current_status']=='Open - with Engineering' and age(t)>72 for t in op),'escalated':len(esc),'escalation_rate':round(len(esc)/len(ts)*100,1),'avoidable':round(len(ret)/len(esc)*100,1) if esc else 0,'returned':len(ret),'reopened':sum(t['reopen_count']>0 for t in ts),'reopen_rate':round(sum(t['reopen_count']>0 for t in ts)/len(ts)*100,1),'median_resolution':round(median(resolved),1) if resolved else 0,'csat':round(sum(cs)/len(cs),2) if cs else 0,'csat_n':len(cs)}
@app.get('/')
def home():return render_template('index.html')
@app.get('/api/summary')
def summary():
 ts=raw(); m=metrics(ts); weeks=defaultdict(lambda:[0,0])
 for t in ts:
  try:dt=datetime.strptime(t['created_at'],'%Y-%m-%d %H:%M'); w=(dt-timedelta(days=dt.weekday())).strftime('%d %b'); weeks[w][0]+=1; weeks[w][1]+=t['escalated_to_eng']=='Yes'
  except:pass
 cats=defaultdict(lambda:[0,0,0])
 for t in ts:
  x=cats[t['category']]; x[0]+=1; x[1]+=t['escalated_to_eng']=='Yes'; x[2]+=t.get('eng_outcome') in ('Insufficient info - returned to L1','Config issue - returned to L1')
 outcomes=Counter(t['eng_outcome'] or 'Other' for t in ts if t['escalated_to_eng']=='Yes')
 return jsonify({'metrics':m,'weekly':[{'week':k,'tickets':v[0],'escalations':v[1]} for k,v in sorted(weeks.items(),key=lambda x:datetime.strptime(x[0]+' 2026','%d %b %Y'))],'categories':[{'name':k,'tickets':v[0],'escalated':v[1],'rate':round(v[1]/v[0]*100,1),'returned':v[2]} for k,v in sorted(cats.items(),key=lambda x:x[1][0],reverse=True)],'outcomes':dict(outcomes),'backlog':dict(Counter(t['current_status'] for t in ts if t['current_status'].startswith('Open'))),'top':sorted([t for t in ts if t['current_status'].startswith('Open')],key=score,reverse=True)[:8]})
@app.get('/api/tickets')
def tickets():
 ts=raw(); q=request.args.get('q','').lower(); status=request.args.get('status','Open'); pri=request.args.get('priority','All'); cat=request.args.get('category','All'); agent=request.args.get('agent','All'); out=[]
 for t in ts:
  if status!='All' and ('Open' if t['current_status'].startswith('Open') else 'Closed')!=status:continue
  if pri!='All' and t['priority']!=pri:continue
  if cat!='All' and t['category']!=cat:continue
  if agent!='All' and t['current_agent']!=agent:continue
  if q and q not in ' '.join(str(t.get(k,'')) for k in ['ticket_id','description','client_name','category','client_id']).lower():continue
  t['age_hours']=round(age(t),1); t['gate_score']=round(score(t),1); out.append(t)
 out.sort(key=lambda x:x['gate_score'],reverse=True)
 return jsonify({'tickets':out,'categories':sorted(set(t['category'] for t in ts)),'agents':sorted(set(t['current_agent'] for t in ts))})
@app.get('/api/ticket/<tid>')
def ticket(tid):
 t=next((x for x in raw() if x['ticket_id']==tid),None)
 if not t:return jsonify(error='Ticket not found'),404
 with db() as c:
  r=c.execute('select items from checklist where id=?',(tid,)).fetchone(); acts=[dict(x) for x in c.execute('select * from actions where ticket_id=? order by seq desc',(tid,))]
 t['checks']=json.loads(r['items']) if r else [False]*len(CHECKS.get(t['category'],DEFAULT)); t['suggestions']=CHECKS.get(t['category'],DEFAULT); t['age_hours']=round(age(t),1); t['gate_score']=round(score(t),1); t['history']=acts
 return jsonify(t)
@app.post('/api/ticket/<tid>/update')
def update(tid):
 d=request.json or {}; action=d.get('action','Updated ticket')
 if not any(x['ticket_id']==tid for x in raw()):return jsonify(error='Ticket not found'),404
 with db() as c:
  old=c.execute('select * from ticket_state where id=?',(tid,)).fetchone(); status=d.get('status',old['status'] if old else None); agent=d.get('agent',old['agent'] if old else None); notes=d.get('notes',old['notes'] if old else '')
  c.execute('insert or replace into ticket_state values(?,?,?,?)',(tid,status,agent,notes))
  if 'checks' in d:c.execute('insert or replace into checklist values(?,?)',(tid,json.dumps(d['checks'])))
  c.execute('insert into actions(ticket_id,action,notes,actor,created) values(?,?,?,?,?)',(tid,action,d.get('notes',''),'Amrita Yadav',datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
 return jsonify(ok=True)
@app.get('/api/activity')
def activity():
 with db() as c:return jsonify([dict(x) for x in c.execute('select * from actions order by seq desc limit 200')])
@app.get('/api/settings')
def settings():
 with db() as c:return jsonify({r['k']:r['v'] for r in c.execute('select * from config')})
@app.post('/api/settings')
def save_settings():
 global SLA_HOURS
 with db() as c:
  for k,v in (request.json or {}).items():c.execute('insert or replace into config values(?,?)',(k,str(v)))
 if 'engineering_sla' in (request.json or {}): SLA_HOURS=int(request.json['engineering_sla'])
 return jsonify(ok=True)
@app.get('/api/export')
def export():return send_file(CSV,as_attachment=True,download_name='rideops_tickets.csv')
@app.get('/api/knowledge')
def knowledge():
 entries=[{'title':'Driver GPS location is jumping between cities','category':'Live tracking / GPS incorrect','type':'Troubleshooting','body':'Capture trip ID and timestamp, verify driver app connectivity and version, compare another trip, then attach route evidence.'},{'title':'Cab not assigned after booking','category':'Roster / booking not syncing','type':'Playbook','body':'Confirm employee and booking IDs, roster effective date, sync timestamp and booking visibility in admin.'},{'title':'Report export fails with error 500','category':'Report export failing','type':'Known issue','body':'Retry with a smaller date range, verify browser download permissions and capture the exact error.'},{'title':'OTP not received by employee','category':'OTP / boarding issue','type':'Troubleshooting','body':'Verify registered phone, OTP expiry, resend attempts, device network and app version.'},{'title':'Invoice shows incorrect amount','category':'Billing / invoice discrepancy','type':'FAQ','body':'Compare invoice line items with trip records, rate card, taxes and adjustments.'},{'title':'How to diagnose a GPS issue before engineering','category':'Live tracking / GPS incorrect','type':'Best practice','body':'Complete all L1 checks and attach a route screenshot before escalating.'}]
 q=request.args.get('q','').lower(); return jsonify([x for x in entries if not q or q in (x['title']+' '+x['category']+' '+x['body']).lower()])
if __name__=='__main__':init();app.run(host='127.0.0.1',port=5000,debug=False)
