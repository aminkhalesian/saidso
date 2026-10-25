"""Command line: python -m app.cli seed [--llm-transcripts] [--llm-emails]
                 python -m app.cli import-csv <client_id> <folder>
                 python -m app.cli rebuild-actions [--llm-emails]
                 python -m app.cli add-sources            (demo usage, tickets and invoices for existing accounts)
                 python -m app.cli export-csv <client_id> <folder>"""
import argparse

from . import pipeline
from .connectors.csv_folder import CsvFolderConnector
from .models import Client, SessionLocal, init_db


def main():
    ap = argparse.ArgumentParser(prog="python -m app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed", help="rebuild the demo clients from synthetic data")
    s.add_argument("--llm-transcripts", action="store_true", help="LLM writes natural calls around the planted lines")
    s.add_argument("--llm-emails", action="store_true", help="LLM personalizes drafted emails")
    s.add_argument("--seed", type=int, default=7)
    i = sub.add_parser("import-csv", help="load a client's data from a folder of CSV exports")
    i.add_argument("client_id")
    i.add_argument("folder")
    r = sub.add_parser("rebuild-actions", help="redraft next steps from the current playbooks; keeps signals, scores and decided actions")
    r.add_argument("--llm-emails", action="store_true", help="LLM personalizes drafted emails")
    d = sub.add_parser("add-sources", help="(re)generate demo usage, support tickets and invoices for the current accounts; changes no score, signal or quote")
    d.add_argument("--seed", type=int, default=7)
    x = sub.add_parser("export-csv", help="write a client's data as the CSV pilot folder a customer would send")
    x.add_argument("client_id")
    x.add_argument("folder")
    a = ap.parse_args()
    if a.cmd != "seed":
        init_db()                      # creates tables added since the database was made (existing data is untouched)
    if a.cmd == "seed":
        pipeline.seed(a.llm_transcripts, a.llm_emails, a.seed)
    elif a.cmd == "add-sources":
        from .connectors import demo_sources
        from .packs import load_pack
        with SessionLocal() as session:
            for client in session.query(Client).all():
                print(client.name, demo_sources.add_sources(session, client, load_pack(client.pack_id), a.seed))
    elif a.cmd == "export-csv":
        from .connectors.csv_export import export_csv
        with SessionLocal() as session:
            print(export_csv(session, a.client_id, a.folder))
    elif a.cmd == "rebuild-actions":
        with SessionLocal() as session:
            for client in session.query(Client).all():
                print(client.name, pipeline.rebuild_actions(session, client, llm_emails=a.llm_emails))
    else:
        with SessionLocal() as session:
            client = session.get(Client, a.client_id)
            if client is None:
                raise SystemExit(f"unknown client {a.client_id}; run seed first or add the client")
            print(pipeline.run_client(session, client, CsvFolderConnector(a.folder)))


if __name__ == "__main__":
    main()
