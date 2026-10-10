FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# server.py faqat Python stdlib ishlatadi — requirements.txt shart emas,
# lekin kelajakda qo'shilsha deb bo'sh fayl qoldiramiz.
COPY requirements.txt* /app/

# Statik fayllar va kod
COPY server.py init_db.py /app/
COPY *.html /app/
COPY css/ /app/css/
COPY js/ /app/js/
COPY images/ /app/images/
COPY Hujjatlar/ /app/Hujjatlar/
COPY _pay_pages/ /app/_pay_pages/

# Joriy bazani birinchi ishga tushirishda seed sifatida olib kelamiz.
# Asl ma'lumotlar /data volume'ga ko'chiriladi.
COPY elgaku.db /app/elgaku.db.seed

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh && \
    mkdir -p /data && \
    mkdir -p /app/uploads /app/backups

EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]
