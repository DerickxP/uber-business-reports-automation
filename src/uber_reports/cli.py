"""Interface de linha de comando.

Cada subcomando corresponde a uma etapa do pipeline, para que qualquer etapa possa ser
executada e depurada isoladamente::

    save-session   captura a sessão de login (Uber ou webmail), uma única vez
    extract        solicita e baixa os relatórios no portal (Playwright)
    ingest         lê os relatórios baixados e grava as corridas no SQLite
    load-mapping   carrega funcionários e histórico de lotação da planilha
    dashboard      gera o dashboard HTML a partir do banco
    pipeline       executa extract -> ingest -> load-mapping -> dashboard
    demo           gera dados sintéticos e roda o pipeline sem acesso a portais
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from uber_reports import __version__
from uber_reports.config import ConfigError, Settings, load_settings

log = logging.getLogger("uber_reports")


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


# ----------------------------------------------------------------------------- etapas


def run_init_db(db: Path) -> None:
    from uber_reports.etl.schema import init_db

    init_db(db)
    log.info("Banco pronto em %s", db)


def run_ingest(reports_dir: Path, db: Path) -> None:
    from uber_reports.etl.load import ingest_reports

    summary = ingest_reports(reports_dir, db)
    log.info(
        "Ingestão: %d arquivo(s), %d corrida(s) no lote, %d nova(s) no banco",
        summary.files,
        summary.rides,
        summary.inserted,
    )


def run_load_mapping(workbook: Path, db: Path) -> None:
    from uber_reports.etl.load import load_mapping

    people, assignments = load_mapping(workbook, db)
    log.info("Mapeamento: %d pessoa(s), %d vigência(s) de lotação", people, assignments)


def run_dashboard(db: Path, output: Path, dashboard) -> None:
    from uber_reports.dashboard.queries import load_enriched_rides
    from uber_reports.dashboard.render import build_dashboard

    rides = load_enriched_rides(db)
    build_dashboard(
        rides,
        output,
        title=dashboard.title,
        subtitle=dashboard.subtitle,
        brand=dashboard.brand,
        logo=dashboard.logo,
    )
    log.info("Dashboard gerado: %s (%d corridas)", output, len(rides))


def run_extract(settings: Settings) -> None:
    from uber_reports.automation.extractor import run_extraction

    result = run_extraction(settings)
    log.info("Reportes solicitados: %s", ", ".join(result.requested) or "nenhum")
    for path in result.downloaded:
        log.info("Baixado: %s", path)


# --------------------------------------------------------------------------- comandos


def cmd_init_db(settings: Settings, args: argparse.Namespace) -> int:
    run_init_db(Path(args.db) if args.db else settings.paths.database)
    return 0


def cmd_ingest(settings: Settings, args: argparse.Namespace) -> int:
    reports_dir = Path(args.reports_dir) if args.reports_dir else settings.paths.downloads
    run_ingest(reports_dir, Path(args.db) if args.db else settings.paths.database)
    return 0


def cmd_load_mapping(settings: Settings, args: argparse.Namespace) -> int:
    workbook = Path(args.workbook) if args.workbook else settings.paths.mapping_workbook
    run_load_mapping(workbook, Path(args.db) if args.db else settings.paths.database)
    return 0


def cmd_dashboard(settings: Settings, args: argparse.Namespace) -> int:
    db = Path(args.db) if args.db else settings.paths.database
    output = Path(args.output) if args.output else settings.paths.dashboard
    run_dashboard(db, output, settings.dashboard)
    return 0


def cmd_extract(settings: Settings, args: argparse.Namespace) -> int:
    run_extract(settings)
    return 0


def cmd_save_session(settings: Settings, args: argparse.Namespace) -> int:
    from uber_reports.automation.sessions import save_session
    from uber_reports.automation.uber_portal import HOME_URL

    if args.target == "uber":
        save_session(HOME_URL, settings.paths.uber_session, label="Uber for Business")
    else:
        save_session(settings.mail.url, settings.paths.mail_session, label="Webmail")
    return 0


def cmd_pipeline(settings: Settings, args: argparse.Namespace) -> int:
    if args.skip_extract:
        log.info("Etapa de extração pulada (--skip-extract).")
    else:
        run_extract(settings)

    run_ingest(settings.paths.downloads, settings.paths.database)

    if settings.paths.mapping_workbook.exists():
        run_load_mapping(settings.paths.mapping_workbook, settings.paths.database)
    else:
        log.warning(
            "Planilha de mapeamento não encontrada (%s). Corridas ficarão como 'Não mapeado'.",
            settings.paths.mapping_workbook,
        )

    run_dashboard(settings.paths.database, settings.paths.dashboard, settings.dashboard)
    return 0


def cmd_demo(_settings: Settings | None, args: argparse.Namespace) -> int:
    from uber_reports.config import DashboardSettings
    from uber_reports.demo.synthetic import generate_demo_dataset

    output_dir = Path(args.output_dir)
    dataset = generate_demo_dataset(
        output_dir / "downloads",
        output_dir / "mapping.xlsx",
        seed=args.seed,
        months=args.months,
        employees=args.employees,
        rides_per_month=args.rides_per_month,
    )
    log.info(
        "Dados sintéticos: %d relatório(s), %d pessoa(s), %d corrida(s)",
        len(dataset.reports),
        dataset.employees,
        dataset.rides,
    )

    db = output_dir / "rides.db"
    run_init_db(db)
    run_ingest(dataset.reports_dir, db)
    run_load_mapping(dataset.mapping_workbook, db)
    run_dashboard(
        db,
        output_dir / "dashboard.html",
        DashboardSettings(subtitle="Dashboard de corridas (dados sintéticos)", brand="Demo"),
    )
    log.info("Abra %s no navegador.", output_dir / "dashboard.html")
    return 0


# ------------------------------------------------------------------------------ parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="uber-reports",
        description="Extração, consolidação e dashboard de relatórios do Uber for Business.",
    )
    parser.add_argument("--config", help="caminho do config.json (padrão: ./config.json)")
    parser.add_argument("-v", "--verbose", action="store_true", help="log detalhado")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init-db", help="cria o banco SQLite e as tabelas")
    p.add_argument("--db")
    p.set_defaults(func=cmd_init_db)

    p = sub.add_parser("ingest", help="lê os relatórios baixados e grava as corridas")
    p.add_argument("--reports-dir")
    p.add_argument("--db")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("load-mapping", help="carrega funcionários e lotação da planilha")
    p.add_argument("--workbook")
    p.add_argument("--db")
    p.set_defaults(func=cmd_load_mapping)

    p = sub.add_parser("dashboard", help="gera o dashboard HTML")
    p.add_argument("--db")
    p.add_argument("--output")
    p.set_defaults(func=cmd_dashboard)

    p = sub.add_parser("extract", help="solicita e baixa os relatórios no portal")
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("save-session", help="salva a sessão de login (uber ou mail)")
    p.add_argument("target", choices=("uber", "mail"))
    p.set_defaults(func=cmd_save_session)

    p = sub.add_parser("pipeline", help="executa todas as etapas em sequência")
    p.add_argument("--skip-extract", action="store_true", help="não abre o navegador")
    p.set_defaults(func=cmd_pipeline)

    p = sub.add_parser("demo", help="gera dados sintéticos e roda o pipeline completo")
    p.add_argument("--output-dir", default="demo_output")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--months", type=int, default=6)
    p.add_argument("--employees", type=int, default=40)
    p.add_argument("--rides-per-month", type=int, default=300)
    p.set_defaults(func=cmd_demo, needs_config=False)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

    settings: Settings | None = None
    if getattr(args, "needs_config", True):
        try:
            settings = load_settings(args.config)
        except ConfigError as exc:
            parser.error(str(exc))

    try:
        return int(args.func(settings, args))
    except KeyboardInterrupt:
        log.warning("Interrompido pelo usuário.")
        return 130
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        log.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
