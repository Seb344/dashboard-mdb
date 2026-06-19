#!/bin/bash
# Lance le dashboard MDB au démarrage
# Ajoute ce script dans : Menu → Session et démarrage → Démarrage automatique
# Ou dans crontab : @reboot /chemin/vers/launch_dashboard.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Attendre que le réseau soit disponible (max 30s)
for i in $(seq 1 10); do
    if ping -c1 api.notion.com &>/dev/null 2>&1; then
        break
    fi
    sleep 3
done

# Lancer le dashboard
cd "$SCRIPT_DIR"
python3 dashboard_mdb.py >> "$SCRIPT_DIR/dashboard.log" 2>&1
