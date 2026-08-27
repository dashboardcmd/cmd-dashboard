"""
Worker opcional: mantém um processo rodando que executa o sync automaticamente
todo dia num horário fixo. Use isso SE o seu host não tiver "Cron Job" nativo
(ex.: Railway). Se estiver no Render, prefira usar um "Cron Job" apontando
para `python sync.py` — é mais simples e mais barato.

Rodar:  python worker.py
"""
import os
from apscheduler.schedulers.blocking import BlockingScheduler
from sync import run_sync

HORA_SYNC = int(os.environ.get("SYNC_HOUR_UTC", "9"))  # 9h UTC ~ 6h no horário de Brasília

if __name__ == "__main__":
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(run_sync, "cron", hour=HORA_SYNC, minute=0)
    print(f"Worker iniciado. Sync automático agendado para {HORA_SYNC}h UTC todos os dias.")
    run_sync()  # roda uma vez imediatamente ao subir
    scheduler.start()
