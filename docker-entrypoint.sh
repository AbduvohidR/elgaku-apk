#!/bin/sh
# ELGAKU — fly.io konteynerga kirish skripti.
# Maqsad: SQLite bazasi, uploads/ va backups/ ni doimiy /data volume'da saqlash.
set -e

mkdir -p /data/uploads/tasks /data/backups

# 1) SQLite DB (birinchi marta seed nusxasidan ko'chiramiz)
if [ ! -f /data/elgaku.db ]; then
    echo "[entrypoint] /data/elgaku.db topilmadi, seed'dan ko'chirilmoqda..."
    cp /app/elgaku.db.seed /data/elgaku.db
    # WAL uchun eski qoldiqlar bo'lmasin
    rm -f /data/elgaku.db-wal /data/elgaku.db-shm || true
fi

# 2) uploads/ va backups/ ni volume'ga symlink qilamiz
rm -rf /app/uploads /app/backups
ln -s /data/uploads /app/uploads
ln -s /data/backups /app/backups

# 3) server.py ishlatadigan muhir o'zgaruvchilar
export ELGAKU_DB=/data/elgaku.db
export PORT=8000

echo "[entrypoint] ELGAKU server ishga tushmoqda (DB=$ELGAKU_DB, PORT=$PORT)"
exec python /app/server.py
