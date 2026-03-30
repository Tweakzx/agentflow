#!/usr/bin/env bash
set -euo pipefail

DB_PATH="${1:-./data/agentflow.db}"

agentflow --db "$DB_PATH" init
agentflow --db "$DB_PATH" create-project kthena --repo volcano-sh/kthena
agentflow --db "$DB_PATH" add-task --project kthena --title "controller partition revision bug" --priority 5 --impact 5 --effort 2 --source github --external-id 841
agentflow --db "$DB_PATH" add-task --project kthena --title "partition percentage support" --priority 4 --impact 4 --effort 3 --source github --external-id 838
agentflow --db "$DB_PATH" board --project kthena
agentflow --db "$DB_PATH" dashboard --out ./dashboard.html

echo "Bootstrap completed. Open ./dashboard.html"
