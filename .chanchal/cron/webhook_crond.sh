#!/bin/sh

# Legacy compatibility entrypoint.

# Kept as a harmless no-op so any old process reference does not fail.

set -eu

echo "webhook_crond: legacy cron service disabled"
exit 0