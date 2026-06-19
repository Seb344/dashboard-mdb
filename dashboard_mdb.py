#!/usr/bin/env python3
"""
Dashboard MDB — Seb
Interroge la DB Notion "Biens" et génère un HTML avec KPI par période + graphe 12 mois.
"""

import os, json, requests, webbrowser
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

TOKEN  = os.getenv("NOTION_TOKEN")
DB_ID  = os.getenv("NOTION_DB_ID")

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

STATUTS_ANALYSES = [
    "Pré-étude avant appel", "KO avant appel", "KO pré-étude",
    "Pré-étude après appel", "A contacter", "Message laissé",
    "KO après appel", "Visite planifiée", "KO après visite",
    "Etude en cours", "KO après étude finale", "Faire offre",
    "Offre faite", "KO offre refusée", "Offre acceptée",
    "Relancer suite offre refusée",
]
STATUTS_VISITES = [
    "Visite planifiée", "KO après visite", "Etude en cours",
    "KO après étude finale", "Faire offre", "Offre faite",
    "KO offre refusée", "Relancer suite offre refusée", "Offre acceptée",
]
STATUTS_OFFRES    = ["Offre faite", "KO offre refusée", "Relancer suite offre refusée", "Offre acceptée"]
STATUTS_ACCEPTEES = ["Offre acceptée"]

def get_periodes_fixes(today):
    y, m = today.year, today.month
    lundi = today - timedelta(days=today.weekday())
    debut_mois = date(y, m, 1)
    fin_mois   = date(y, m+1, 1) - timedelta(days=1) if m < 12 else date(y, 12, 31)
    q = (m - 1) // 3 + 1
    debuts_q = {1:(1,1), 2:(4,1), 3:(7,1), 4:(10,1)}
    fins_q   = {1:(3,31), 2:(6,30), 3:(9,30), 4:(12,31)}
    return [
        {"id":"sem",  "label":"Semaine en cours", "debut":lundi, "fin":lundi+timedelta(days=6)},
        {"id":"mois", "label":"Mois en cours",    "debut":debut_mois, "fin":fin_mois},
        {"id":"trim", "label":f"T{q} {y}",        "debut":date(y,*debuts_q[q]), "fin":date(y,*fins_q[q])},
        {"id":"year", "label":f"Année {y}",       "debut":date(y,1,1), "fin":date(y,12,31)},
    ]

def get_periodes_libres(today):
    y, m = today.year, today.month
    semaines, mois_list, trimestres = [], [], []
    lundi = today - timedelta(days=today.weekday())
    for i in range(26):
        d = lundi - timedelta(weeks=i)
        num = d.isocalendar()[1]
        semaines.append({"label":f"S{num:02d} — {d.strftime('%d/%m')} au {(d+timedelta(days=6)).strftime('%d/%m/%Y')}", "debut":d.isoformat(), "fin":(d+timedelta(days=6)).isoformat()})
    mois_noms = ["Jan","Fév","Mar","Avr","Mai","Jun","Jul","Aoû","Sep","Oct","Nov","Déc"]
    cm, cy = m, y
    for _ in range(24):
        dm = date(cy, cm, 1)
        fm = date(cy, cm+1, 1) - timedelta(days=1) if cm < 12 else date(cy, 12, 31)
        mois_list.append({"label":f"{mois_noms[cm-1]}. {cy}", "debut":dm.isoformat(), "fin":fm.isoformat()})
        cm -= 1
        if cm == 0: cm, cy = 12, cy-1
    debuts_q = {1:(1,1), 2:(4,1), 3:(7,1), 4:(10,1)}
    fins_q   = {1:(3,31), 2:(6,30), 3:(9,30), 4:(12,31)}
    cq, cy2 = (m-1)//3+1, y
    for _ in range(8):
        trimestres.append({"label":f"T{cq} {cy2}", "debut":date(cy2,*debuts_q[cq]).isoformat(), "fin":date(cy2,*fins_q[cq]).isoformat()})
        cq -= 1
        if cq == 0: cq, cy2 = 4, cy2-1
    return semaines, mois_list, trimestres

def get_chart_data(today):
    """Génère les labels et données pour le graphe 12 derniers mois."""
    mois_noms = ["Jan","Fév","Mar","Avr","Mai","Jun","Jul","Aoû","Sep","Oct","Nov","Déc"]
    y, m = today.year, today.month
    labels = []
    periodes = []
    cm, cy = m, y
    for _ in range(12):
        dm = date(cy, cm, 1)
        fm = date(cy, cm+1, 1) - timedelta(days=1) if cm < 12 else date(cy, 12, 31)
        labels.insert(0, f"{mois_noms[cm-1]} {cy}")
        periodes.insert(0, (dm, fm))
        cm -= 1
        if cm == 0: cm, cy = 12, cy-1
    return labels, periodes

def fetch_all_biens():
    biens, payload = [], {"page_size": 100}
    while True:
        r = requests.post(f"https://api.notion.com/v1/databases/{DB_ID}/query", headers=HEADERS, json=payload)
        r.raise_for_status()
        data = r.json()
        biens.extend(data["results"])
        if not data.get("has_more"): break
        payload["start_cursor"] = data["next_cursor"]
    return biens

def get_date(bien):
    prop = bien["properties"].get("MAJ Statuts", {})
    d = prop.get("date", {})
    if not d or not d.get("start"): return None
    try: return date.fromisoformat(d["start"][:10])
    except: return None

def get_statut(bien):
    prop = bien["properties"].get("Statut", {})
    sel = prop.get("select") or prop.get("status")
    return sel.get("name", "") if sel else ""

def compute_kpi(biens, debut, fin):
    if isinstance(debut, str): debut = date.fromisoformat(debut)
    if isinstance(fin, str):   fin   = date.fromisoformat(fin)
    sel=ana=vis=off=acc=0
    for b in biens:
        d = get_date(b)
        if not d or not (debut <= d <= fin): continue
        sel += 1
        s = get_statut(b)
        if s in STATUTS_ANALYSES:  ana += 1
        if s in STATUTS_VISITES:   vis += 1
        if s in STATUTS_OFFRES:    off += 1
        if s in STATUTS_ACCEPTEES: acc += 1
    return {"sel":sel,"ana":ana,"vis":vis,"off":off,"acc":acc}

def pct(a,b): return round(a/b*100) if b else 0

def render_html(biens, today):
    pf = get_periodes_fixes(today)
    semaines, mois_list, trimestres = get_periodes_libres(today)
    fixes_data = []
    for p in pf:
        k = compute_kpi(biens, p["debut"], p["fin"])
        fixes_data.append({**p, "kpi":k, "d":p["debut"].strftime("%d/%m/%Y"), "f":p["fin"].strftime("%d/%m/%Y")})
    biens_js = [{"date":get_date(b).isoformat(),"statut":get_statut(b)} for b in biens if get_date(b)]
    k0 = fixes_data[0]["kpi"]

    # Données graphe 12 mois
    chart_labels, chart_periodes = get_chart_data(today)
    chart_sel, chart_ana, chart_vis, chart_off = [], [], [], []
    for dm, fm in chart_periodes:
        k = compute_kpi(biens, dm, fm)
        chart_sel.append(k["sel"])
        chart_ana.append(k["ana"])
        chart_vis.append(k["vis"])
        chart_off.append(k["off"])

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8"><title>Dashboard MDB</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',Arial,sans-serif;background:#0f1117;color:#e8e8e8;min-height:100vh}}
header{{background:#1a1a2e;padding:1.2rem 2rem;border-bottom:1px solid #2a2a4a;display:flex;align-items:center;justify-content:space-between}}
header h1{{font-size:1.2rem;font-weight:500;color:#fff}}
header .meta{{font-size:.75rem;color:#666;text-align:right;line-height:1.6}}
.zone{{padding:1rem 2rem 0}}
.zone-label{{font-size:10px;color:#555;text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px}}
.tabs-fixed{{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:.8rem}}
.tab-btn{{background:#1e1e30;border:1px solid #2a2a4a;color:#aaa;padding:6px 16px;border-radius:20px;cursor:pointer;font-size:.8rem;transition:all .15s}}
.tab-btn:hover{{background:#2a2a4a;color:#ddd}}
.tab-btn.active{{background:#0f6e56;border-color:#0f6e56;color:#fff;font-weight:500}}
.selectors{{display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:.8rem 2rem;border-top:1px solid #1a1a2e;border-bottom:1px solid #1a1a2e}}
.sel-group{{display:flex;align-items:center;gap:6px}}
.sel-group label{{font-size:.75rem;color:#666}}
.sel-group select{{background:#1e1e30;border:1px solid #2a2a4a;color:#ccc;padding:5px 10px;border-radius:20px;font-size:.75rem;cursor:pointer}}
.content{{padding:1.2rem 2rem 2rem}}
.period-info{{font-size:.75rem;color:#555;margin-bottom:1rem}}
.kpi-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:.8rem;margin-bottom:1.5rem}}
.kpi-card{{border-radius:12px;padding:1.2rem;text-align:center}}
.kpi-blue  {{background:#0d2a4a;border:1px solid #185FA5}}
.kpi-purple{{background:#1e1535;border:1px solid #534AB7}}
.kpi-teal  {{background:#0a2820;border:1px solid #0f6e56}}
.kpi-amber {{background:#2a1e08;border:1px solid #854F0B}}
.kpi-icon{{font-size:1.5rem;margin-bottom:.4rem}}
.kpi-value{{font-size:2.6rem;font-weight:700;color:#fff;line-height:1;margin-bottom:.3rem}}
.kpi-label{{font-size:.72rem;color:#888;text-transform:uppercase;letter-spacing:.05em}}
.kpi-obj{{font-size:.68rem;color:#444;margin-top:.25rem}}
.funnel{{background:#1a1a2e;border:1px solid #2a2a4a;border-radius:12px;padding:1rem 1.4rem;margin-bottom:1.5rem}}
.funnel-title{{font-size:.72rem;color:#555;text-transform:uppercase;letter-spacing:.06em;margin-bottom:.9rem}}
.f-row{{display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:.5px solid #2a2a4a}}
.f-row:last-child{{border-bottom:none}}
.f-label{{font-size:.78rem;color:#888;min-width:220px}}
.f-wrap{{flex:1;background:#252540;border-radius:4px;height:7px;overflow:hidden}}
.f-bar{{height:100%;border-radius:4px;transition:width .4s ease}}
.b1{{background:#185FA5}}.b2{{background:#534AB7}}.b3{{background:#0f6e56}}.b4{{background:#3B6D11}}
.f-pct{{font-size:.82rem;font-weight:500;color:#ddd;min-width:34px;text-align:right}}
.chart-box{{background:#1a1a2e;border:1px solid #2a2a4a;border-radius:12px;padding:1rem 1.4rem}}
.chart-title{{font-size:.72rem;color:#555;text-transform:uppercase;letter-spacing:.06em;margin-bottom:1rem}}
.footer{{font-size:.7rem;color:#333;margin-top:1.2rem;text-align:right}}
</style>
</head>
<body>
<header>
  <h1>🏗️ Dashboard MDB — Seb</h1>
  <div class="meta">Généré le {today.strftime("%d/%m/%Y")}<br>Objectifs semaine : 10 analyses · 5 visites · 3 offres</div>
</header>
<div class="zone">
  <div class="zone-label">Périodes rapides</div>
  <div class="tabs-fixed">
    <button class="tab-btn active" onclick="showFixed(0)">Semaine en cours</button>
    <button class="tab-btn" onclick="showFixed(1)">Mois en cours</button>
    <button class="tab-btn" onclick="showFixed(2)">Trimestre en cours</button>
    <button class="tab-btn" onclick="showFixed(3)">Année {today.year}</button>
  </div>
</div>
<div class="selectors">
  <span style="font-size:.72rem;color:#444;margin-right:4px;">Période libre →</span>
  <div class="sel-group"><label>Semaine</label><select id="sel-sem" onchange="showCustom('sem')"><option value="">--</option></select></div>
  <div class="sel-group"><label>Mois</label><select id="sel-mois" onchange="showCustom('mois')"><option value="">--</option></select></div>
  <div class="sel-group"><label>Trimestre</label><select id="sel-trim" onchange="showCustom('trim')"><option value="">--</option></select></div>
</div>
<div class="content">
  <div class="period-info" id="period-info">{fixes_data[0]["d"]} → {fixes_data[0]["f"]}</div>
  <div class="kpi-grid">
    <div class="kpi-card kpi-blue">
      <div class="kpi-icon">📑</div><div class="kpi-value" id="v-sel">{k0["sel"]}</div>
      <div class="kpi-label">Sélectionnés</div>
    </div>
    <div class="kpi-card kpi-purple">
      <div class="kpi-icon">🧪</div><div class="kpi-value" id="v-ana">{k0["ana"]}</div>
      <div class="kpi-label">Analyses</div><div class="kpi-obj">obj. 10 / sem.</div>
    </div>
    <div class="kpi-card kpi-teal">
      <div class="kpi-icon">👁️</div><div class="kpi-value" id="v-vis">{k0["vis"]}</div>
      <div class="kpi-label">Visites</div><div class="kpi-obj">obj. 5 / sem.</div>
    </div>
    <div class="kpi-card kpi-amber">
      <div class="kpi-icon">💰</div><div class="kpi-value" id="v-off">{k0["off"]}</div>
      <div class="kpi-label">Offres</div><div class="kpi-obj">obj. 3 / sem.</div>
    </div>
  </div>
  <div class="funnel">
    <div class="funnel-title">Taux de conversion</div>
    <div class="f-row"><span class="f-label">Sélectionnés → Analyses</span><div class="f-wrap"><div class="f-bar b1" id="b1" style="width:{pct(k0['ana'],k0['sel'])}%"></div></div><span class="f-pct" id="p1">{pct(k0['ana'],k0['sel'])}%</span></div>
    <div class="f-row"><span class="f-label">Analyses → Visites</span><div class="f-wrap"><div class="f-bar b2" id="b2" style="width:{pct(k0['vis'],k0['ana'])}%"></div></div><span class="f-pct" id="p2">{pct(k0['vis'],k0['ana'])}%</span></div>
    <div class="f-row"><span class="f-label">Visites → Offres</span><div class="f-wrap"><div class="f-bar b3" id="b3" style="width:{pct(k0['off'],k0['vis'])}%"></div></div><span class="f-pct" id="p3">{pct(k0['off'],k0['vis'])}%</span></div>
    <div class="f-row"><span class="f-label">Offres → Offre acceptée</span><div class="f-wrap"><div class="f-bar b4" id="b4" style="width:{pct(k0['acc'],k0['off'])}%"></div></div><span class="f-pct" id="p4">{pct(k0['acc'],k0['off'])}%</span></div>
  </div>
  <div class="chart-box">
    <div class="chart-title">Évolution mensuelle — 12 derniers mois</div>
    <canvas id="chart" height="100"></canvas>
  </div>
  <div class="footer">Données Notion · relancer update_dashboard.sh pour actualiser</div>
</div>
<script>
const FIXES={json.dumps(fixes_data, default=str)};
const BIENS={json.dumps(biens_js)};
const SEMAINES={json.dumps(semaines)};
const MOIS={json.dumps(mois_list)};
const TRIMS={json.dumps(trimestres)};
const S_ANA=new Set({json.dumps(STATUTS_ANALYSES)});
const S_VIS=new Set({json.dumps(STATUTS_VISITES)});
const S_OFF=new Set({json.dumps(STATUTS_OFFRES)});
const S_ACC=new Set({json.dumps(STATUTS_ACCEPTEES)});

function computeKpi(debut,fin){{
  const d0=new Date(debut),d1=new Date(fin);
  let sel=0,ana=0,vis=0,off=0,acc=0;
  for(const b of BIENS){{const bd=new Date(b.date);if(bd<d0||bd>d1)continue;sel++;if(S_ANA.has(b.statut))ana++;if(S_VIS.has(b.statut))vis++;if(S_OFF.has(b.statut))off++;if(S_ACC.has(b.statut))acc++;}}
  return{{sel,ana,vis,off,acc}};
}}
function pct(a,b){{return b?Math.round(a/b*100):0;}}
function updateUI(k,debut,fin){{
  document.getElementById('v-sel').textContent=k.sel;
  document.getElementById('v-ana').textContent=k.ana;
  document.getElementById('v-vis').textContent=k.vis;
  document.getElementById('v-off').textContent=k.off;
  document.getElementById('period-info').textContent=new Date(debut).toLocaleDateString('fr-FR')+' → '+new Date(fin).toLocaleDateString('fr-FR');
  [[pct(k.ana,k.sel),'b1','p1'],[pct(k.vis,k.ana),'b2','p2'],[pct(k.off,k.vis),'b3','p3'],[pct(k.acc,k.off),'b4','p4']].forEach(([v,b,p])=>{{document.getElementById(b).style.width=v+'%';document.getElementById(p).textContent=v+'%';}});
}}
function showFixed(i){{
  document.querySelectorAll('.tab-btn').forEach((b,j)=>b.classList.toggle('active',i===j));
  ['sel-sem','sel-mois','sel-trim'].forEach(id=>document.getElementById(id).value='');
  const p=FIXES[i];updateUI(p.kpi,p.debut,p.fin);
}}
function showCustom(type){{
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  const selId=type==='sem'?'sel-sem':type==='mois'?'sel-mois':'sel-trim';
  const val=document.getElementById(selId).value;if(!val)return;
  const[debut,fin]=val.split('|');
  if(type!=='sem')document.getElementById('sel-sem').value='';
  if(type!=='mois')document.getElementById('sel-mois').value='';
  if(type!=='trim')document.getElementById('sel-trim').value='';
  updateUI(computeKpi(debut,fin),debut,fin);
}}
function populateSelect(id,items){{const sel=document.getElementById(id);for(const it of items){{const o=document.createElement('option');o.value=it.debut+'|'+it.fin;o.textContent=it.label;sel.appendChild(o);}}}}
populateSelect('sel-sem',SEMAINES);
populateSelect('sel-mois',MOIS);
populateSelect('sel-trim',TRIMS);

// Graphe 12 mois
const ctx = document.getElementById('chart').getContext('2d');
new Chart(ctx, {{
  type: 'line',
  data: {{
    labels: {json.dumps(chart_labels)},
    datasets: [
      {{
        label: 'Sélectionnés',
        data: {json.dumps(chart_sel)},
        borderColor: '#185FA5',
        backgroundColor: 'rgba(24,95,165,0.08)',
        borderWidth: 2,
        pointRadius: 4,
        pointHoverRadius: 6,
        tension: 0.3,
        fill: false,
      }},
      {{
        label: 'Analyses',
        data: {json.dumps(chart_ana)},
        borderColor: '#534AB7',
        backgroundColor: 'rgba(83,74,183,0.08)',
        borderWidth: 2,
        pointRadius: 4,
        pointHoverRadius: 6,
        tension: 0.3,
        fill: false,
      }},
      {{
        label: 'Visites',
        data: {json.dumps(chart_vis)},
        borderColor: '#0f6e56',
        backgroundColor: 'rgba(15,110,86,0.08)',
        borderWidth: 2,
        pointRadius: 4,
        pointHoverRadius: 6,
        tension: 0.3,
        fill: false,
      }},
      {{
        label: 'Offres',
        data: {json.dumps(chart_off)},
        borderColor: '#EF9F27',
        backgroundColor: 'rgba(239,159,39,0.08)',
        borderWidth: 2,
        pointRadius: 4,
        pointHoverRadius: 6,
        tension: 0.3,
        fill: false,
      }},
    ]
  }},
  options: {{
    responsive: true,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{
      legend: {{
        position: 'top',
        labels: {{
          color: '#888',
          font: {{ size: 11 }},
          boxWidth: 12,
          padding: 16,
        }}
      }},
      tooltip: {{
        backgroundColor: '#1a1a2e',
        borderColor: '#2a2a4a',
        borderWidth: 1,
        titleColor: '#ccc',
        bodyColor: '#aaa',
        padding: 10,
      }}
    }},
    scales: {{
      x: {{
        grid: {{ color: '#1e1e30' }},
        ticks: {{ color: '#555', font: {{ size: 11 }} }}
      }},
      y: {{
        grid: {{ color: '#1e1e30' }},
        ticks: {{ color: '#555', font: {{ size: 11 }}, stepSize: 1 }},
        beginAtZero: true,
      }}
    }}
  }}
}});
</script>
</body></html>"""

def main():
    print("📡 Connexion à Notion...")
    try:
        biens = fetch_all_biens()
        print(f"✅ {len(biens)} biens récupérés")
    except Exception as e:
        print(f"❌ Erreur API Notion : {e}"); return

    today = date.today()
    print("📊 Calcul des KPI fixes...")
    for p in get_periodes_fixes(today):
        k = compute_kpi(biens, p["debut"], p["fin"])
        print(f"  {p['label']:<30} | 📑{k['sel']} 🧪{k['ana']} 👁️{k['vis']} 💰{k['off']} ✅{k['acc']}")

    html = render_html(biens, today)
    out  = os.path.join(os.path.dirname(__file__), "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n✅ Dashboard généré → {out}")
    webbrowser.open(f"file://{out}")

if __name__ == "__main__":
    main()