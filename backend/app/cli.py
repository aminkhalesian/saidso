"""Command line: python -m app.cli seed [--llm-transcripts] [--llm-emails]
                 python -m app.cli import-csv <client_id> <folder>
                 python -m app.cli rebuild-actions [--llm-emails]"""
import argparse

from . import pipeline
from .connectors.csv_folder import CsvFolderConnector
from .models import Client, SessionLocal


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
    a = ap.parse_args()
    if a.cmd == "seed":
        pipeline.seed(a.llm_transcripts, a.llm_emails, a.seed)
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
