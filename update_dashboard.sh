#!/bin/bash
# update_dashboard.sh
# Génère le dashboard MDB et le pousse sur GitHub Pages
# Se lance automatiquement au démarrage via cron

SCRIPT_DIR="/home/seb/Documents/Automatisation Notion/dashboard_mdb"
LOG="$SCRIPT_DIR/dashboard.log"

echo "========================================" >> "$LOG"
echo "$(date '+%d/%m/%Y %H:%M:%S') — Démarrage" >> "$LOG"

# Attendre que le réseau soit dispo (max 60s)
echo "⏳ Attente réseau..." >> "$LOG"
for i in $(seq 1 20); do
    if ping -c1 -W2 api.notion.com &>/dev/null 2>&1; then
        echo "✅ Réseau OK" >> "$LOG"
        break
    fi
    sleep 3
done

# Activer conda base
source /home/seb/miniconda3/etc/profile.d/conda.sh
conda activate base

# Générer le dashboard
echo "📡 Génération du dashboard..." >> "$LOG"
cd "$SCRIPT_DIR"
python3 dashboard_mdb.py >> "$LOG" 2>&1

if [ $? -ne 0 ]; then
    echo "❌ Erreur lors de la génération" >> "$LOG"
    exit 1
fi

# Push sur GitHub
echo "🚀 Push GitHub..." >> "$LOG"
git add index.html >> "$LOG" 2>&1
git commit -m "update $(date '+%d/%m/%Y %H:%M')" >> "$LOG" 2>&1
git push origin main >> "$LOG" 2>&1

if [ $? -eq 0 ]; then
    echo "✅ Dashboard mis à jour sur GitHub Pages" >> "$LOG"
else
    echo "❌ Erreur lors du push GitHub" >> "$LOG"
fi

echo "$(date '+%d/%m/%Y %H:%M:%S') — Terminé" >> "$LOG"
