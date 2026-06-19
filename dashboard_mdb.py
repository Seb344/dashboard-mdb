#!/usr/bin/env python3
"""
Dashboard MDB — Seb
Interroge la DB Notion "Biens" et génère un HTML avec KPI par période.
Lance-le au démarrage ou manuellement.
"""

import os, json, requests, webbrowser, tempfile
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

TOKEN   = os.getenv("NOTION_TOKEN")
DB_ID   = os.getenv("NOTION_DB_ID")

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

# ─── Groupes de statuts (identiques à ta formule Notion) ─────────────────────

STATUTS_SELECTIONNES = None  # Tous les biens sur la période = pas de filtre statut

STATUTS_ANALYSES = [
    "Pré-étude avant appel", "KO avant appel", "KO pré-étude",
    "Pré-étude après appel", "A contacter", "Message laissé",
    "KO après appel", "Visite planifiée", "KO après visite",
    "Etude en cours", "KO après étude finale", "Faire offre",
    "Offre faite", "KO offre refusée", "Offre acceptée",
    "Attendre après Etude", "Relancer suite offre refusée",
]

STATUTS_VISITES = [
    "Visite planifiée", "KO après visite", "Etude en cours",
    "KO après étude finale", "Faire offre", "Offre faite",
    "KO offre refusée", "Relancer suite offre refusée", "Offre acceptée",
]

STATUTS_OFFRES = [
    "Offre faite", "KO offre refusée",
    "Relancer suite offre refusée", "Offre acceptée",
]

# ─── Calcul des périodes ──────────────────────────────────────────────────────

def periodes():
    today = date.today()
    y, m = today.year, today.month

    # Semaine en cours (lundi → dimanche)
    lundi = today - timedelta(days=today.weekday())
    dimanche = lundi + timedelta(days=6)

    # Semaine précédente
    lundi_prec = lundi - timedelta(weeks=1)
    dimanche_prec = lundi_prec + timedelta(days=6)

    # Mois en cours
    debut_mois = date(y, m, 1)
    if m == 12:
        fin_mois = date(y+1, 1, 1) - timedelta(days=1)
    else:
        fin_mois = date(y, m+1, 1) - timedelta(days=1)

    # Mois précédent
    if m == 1:
        debut_mois_prec = date(y-1, 12, 1)
        fin_mois_prec   = date(y, 1, 1) - timedelta(days=1)
    else:
        debut_mois_prec = date(y, m-1, 1)
        fin_mois_prec   = date(y, m, 1) - timedelta(days=1)

    # Trimestres
    def trimestre(n, annee):
        debuts = {1: (1,1), 2: (4,1), 3: (7,1), 4: (10,1)}
        fins   = {1: (3,31), 2: (6,30), 3: (9,30), 4: (12,31)}
        return date(annee, *debuts[n]), date(annee, *fins[n])

    q_courant = (m - 1) // 3 + 1
    q_prec    = q_courant - 1 if q_courant > 1 else 4
    q_prec_y  = y if q_courant > 1 else y - 1

    t1d, t1f = trimestre(1, y)
    t2d, t2f = trimestre(2, y)
    t3d, t3f = trimestre(3, y)
    t4d, t4f = trimestre(4, y)
    tpd, tpf = trimestre(q_prec, q_prec_y)

    debut_annee = date(y, 1, 1)
    fin_annee   = date(y, 12, 31)

    mois_noms = ["Jan","Fév","Mar","Avr","Mai","Jun","Jul","Aoû","Sep","Oct","Nov","Déc"]

    return [
        {"label": "Semaine en cours",    "debut": lundi,          "fin": dimanche},
        {"label": "Semaine précédente",  "debut": lundi_prec,     "fin": dimanche_prec},
        {"label": f"{mois_noms[m-1]}. {y} (mois en cours)", "debut": debut_mois, "fin": fin_mois},
        {"label": f"Mois précédent",     "debut": debut_mois_prec,"fin": fin_mois_prec},
        {"label": f"T. en cours (T{q_courant})", "debut": trimestre(q_courant, y)[0], "fin": trimestre(q_courant, y)[1]},
        {"label": f"T. précédent (T{q_prec} {q_prec_y})", "debut": tpd, "fin": tpf},
        {"label": f"T1 {y}",             "debut": t1d,            "fin": t1f},
        {"label": f"T2 {y}",             "debut": t2d,            "fin": t2f},
        {"label": f"T3 {y}",             "debut": t3d,            "fin": t3f},
        {"label": f"T4 {y}",             "debut": t4d,            "fin": t4f},
        {"label": f"Année {y}",          "debut": debut_annee,    "fin": fin_annee},
    ]

# ─── Appel API Notion (avec pagination) ──────────────────────────────────────

def fetch_all_biens():
    biens = []
    payload = {"page_size": 100}
    while True:
        r = requests.post(
            f"https://api.notion.com/v1/databases/{DB_ID}/query",
            headers=HEADERS,
            json=payload,
        )
        r.raise_for_status()
        data = r.json()
        biens.extend(data["results"])
        if not data.get("has_more"):
            break
        payload["start_cursor"] = data["next_cursor"]
    return biens

def get_date(bien):
    """Extrait la date MAJ Statuts d'un bien."""
    prop = bien["properties"].get("MAJ Statuts", {})
    d = prop.get("date", {})
    if not d or not d.get("start"):
        return None
    try:
        return date.fromisoformat(d["start"][:10])
    except Exception:
        return None

def get_statut(bien):
    prop = bien["properties"].get("Statut", {})
    sel = prop.get("select") or prop.get("status")
    if sel:
        return sel.get("name", "")
    return ""

# ─── Calcul des KPI pour une période ─────────────────────────────────────────

def compute_kpi(biens, debut, fin):
    selectionnes = analyses = visites = offres = 0
    for b in biens:
        d = get_date(b)
        if not d or not (debut <= d <= fin):
            continue
        selectionnes += 1
        statut = get_statut(b)
        if statut in STATUTS_ANALYSES:
            analyses += 1
        if statut in STATUTS_VISITES:
            visites += 1
        if statut in STATUTS_OFFRES:
            offres += 1
    return {"selectionnes": selectionnes, "analyses": analyses,
            "visites": visites, "offres": offres}

# ─── Génération HTML ──────────────────────────────────────────────────────────

def render_html(resultats, today):
    tabs_html = ""
    panels_html = ""

    for i, r in enumerate(resultats):
        active = "active" if i == 0 else ""
        p = r["label"]
        k = r["kpi"]
        debut_str = r["debut"].strftime("%d/%m/%Y")
        fin_str   = r["fin"].strftime("%d/%m/%Y")

        # Taux de conversion
        tx_analyse = round(k["analyses"] / k["selectionnes"] * 100) if k["selectionnes"] else 0
        tx_visite  = round(k["visites"]  / k["analyses"]    * 100) if k["analyses"] else 0
        tx_offre   = round(k["offres"]   / k["visites"]     * 100) if k["visites"] else 0

        tabs_html += f'<button class="tab-btn {active}" onclick="showTab({i})">{p}</button>\n'
        panels_html += f"""
<div class="panel {"active" if i == 0 else ""}" id="panel-{i}">
  <div class="period-label">{debut_str} → {fin_str}</div>
  <div class="kpi-grid">
    <div class="kpi-card kpi-blue">
      <div class="kpi-icon">📑</div>
      <div class="kpi-value">{k["selectionnes"]}</div>
      <div class="kpi-label">Sélectionnés</div>
    </div>
    <div class="kpi-card kpi-purple">
      <div class="kpi-icon">🧪</div>
      <div class="kpi-value">{k["analyses"]}</div>
      <div class="kpi-label">Analyses</div>
    </div>
    <div class="kpi-card kpi-teal">
      <div class="kpi-icon">👁️</div>
      <div class="kpi-value">{k["visites"]}</div>
      <div class="kpi-label">Visites</div>
    </div>
    <div class="kpi-card kpi-amber">
      <div class="kpi-icon">💰</div>
      <div class="kpi-value">{k["offres"]}</div>
      <div class="kpi-label">Offres</div>
    </div>
  </div>
  <div class="funnel">
    <div class="funnel-title">Taux de conversion</div>
    <div class="funnel-row">
      <span class="funnel-label">Sélectionnés → Analyses</span>
      <div class="funnel-bar-wrap">
        <div class="funnel-bar" style="width:{tx_analyse}%"></div>
      </div>
      <span class="funnel-pct">{tx_analyse}%</span>
    </div>
    <div class="funnel-row">
      <span class="funnel-label">Analyses → Visites</span>
      <div class="funnel-bar-wrap">
        <div class="funnel-bar bar-teal" style="width:{tx_visite}%"></div>
      </div>
      <span class="funnel-pct">{tx_visite}%</span>
    </div>
    <div class="funnel-row">
      <span class="funnel-label">Visites → Offres</span>
      <div class="funnel-bar-wrap">
        <div class="funnel-bar bar-amber" style="width:{tx_offre}%"></div>
      </div>
      <span class="funnel-pct">{tx_offre}%</span>
    </div>
  </div>
</div>
"""

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Dashboard MDB — Seb</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #0f1117; color: #e8e8e8; min-height: 100vh; }}

  header {{ background: #1a1a2e; padding: 1.5rem 2rem; border-bottom: 1px solid #2a2a4a; display: flex; align-items: center; justify-content: space-between; }}
  header h1 {{ font-size: 1.3rem; font-weight: 500; color: #fff; }}
  header .date {{ font-size: 0.85rem; color: #888; }}

  .tabs {{ display: flex; flex-wrap: wrap; gap: 6px; padding: 1.2rem 2rem 0; background: #0f1117; }}
  .tab-btn {{ background: #1e1e30; border: 1px solid #2a2a4a; color: #aaa; padding: 6px 14px; border-radius: 20px; cursor: pointer; font-size: 0.8rem; transition: all 0.15s; }}
  .tab-btn:hover {{ background: #2a2a4a; color: #ddd; }}
  .tab-btn.active {{ background: #0f6e56; border-color: #0f6e56; color: #fff; font-weight: 500; }}

  .content {{ padding: 1.5rem 2rem 2rem; }}
  .panel {{ display: none; }}
  .panel.active {{ display: block; }}

  .period-label {{ font-size: 0.8rem; color: #666; margin-bottom: 1.2rem; }}

  .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 2rem; }}

  .kpi-card {{ border-radius: 12px; padding: 1.5rem; text-align: center; }}
  .kpi-blue   {{ background: #0d2a4a; border: 1px solid #185FA5; }}
  .kpi-purple {{ background: #1e1535; border: 1px solid #534AB7; }}
  .kpi-teal   {{ background: #0a2820; border: 1px solid #0f6e56; }}
  .kpi-amber  {{ background: #2a1e08; border: 1px solid #854F0B; }}

  .kpi-icon {{ font-size: 1.8rem; margin-bottom: 0.5rem; }}
  .kpi-value {{ font-size: 2.8rem; font-weight: 700; color: #fff; line-height: 1; margin-bottom: 0.4rem; }}
  .kpi-label {{ font-size: 0.8rem; color: #999; text-transform: uppercase; letter-spacing: 0.05em; }}

  .funnel {{ background: #1a1a2e; border: 1px solid #2a2a4a; border-radius: 12px; padding: 1.2rem 1.5rem; }}
  .funnel-title {{ font-size: 0.8rem; color: #888; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 1rem; }}
  .funnel-row {{ display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }}
  .funnel-row:last-child {{ margin-bottom: 0; }}
  .funnel-label {{ font-size: 0.82rem; color: #aaa; min-width: 200px; }}
  .funnel-bar-wrap {{ flex: 1; background: #252540; border-radius: 4px; height: 8px; overflow: hidden; }}
  .funnel-bar {{ height: 100%; background: #185FA5; border-radius: 4px; transition: width 0.4s ease; }}
  .funnel-bar.bar-teal {{ background: #0f6e56; }}
  .funnel-bar.bar-amber {{ background: #854F0B; }}
  .funnel-pct {{ font-size: 0.85rem; font-weight: 500; color: #ddd; min-width: 36px; text-align: right; }}

  .refresh {{ font-size: 0.75rem; color: #555; margin-top: 1.5rem; text-align: right; }}
</style>
</head>
<body>
<header>
  <h1>🏗️ Dashboard MDB — Seb</h1>
  <div class="date">Généré le {today.strftime("%d/%m/%Y")}</div>
</header>
<div class="tabs">
{tabs_html}
</div>
<div class="content">
{panels_html}
  <div class="refresh">Données Notion · relancer dashboard_mdb.py pour actualiser</div>
</div>
<script>
function showTab(i) {{
  document.querySelectorAll('.tab-btn').forEach((b,j) => b.classList.toggle('active', i===j));
  document.querySelectorAll('.panel').forEach((p,j) => p.classList.toggle('active', i===j));
}}
</script>
</body>
</html>"""

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("📡 Connexion à Notion...")
    try:
        biens = fetch_all_biens()
        print(f"✅ {len(biens)} biens récupérés")
    except Exception as e:
        print(f"❌ Erreur API Notion : {e}")
        return

    today = date.today()
    ps = periodes()

    print("📊 Calcul des KPI...")
    resultats = []
    for p in ps:
        kpi = compute_kpi(biens, p["debut"], p["fin"])
        resultats.append({**p, "kpi": kpi})
        print(f"  {p['label']:<35} | 📑{kpi['selectionnes']} 🧪{kpi['analyses']} 👁️{kpi['visites']} 💰{kpi['offres']}")

    html = render_html(resultats, today)

    out = os.path.join(os.path.dirname(__file__), "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅ Dashboard généré → {out}")
    webbrowser.open(f"file://{out}")

if __name__ == "__main__":
    main()
