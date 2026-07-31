import argparse
import json
import logging
import sys

from app.services.singbox_client_service import SingBoxClientService

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    level=logging.INFO,
)


def dry_run() -> None:
    service = SingBoxClientService()
    inbound_tag = "vless-reality"
    email = "dry-run-test-user"

    result = service.create_client_dry_run(inbound_tag, email)
    report = {
        "success": result.success,
        "message": result.message,
    }
    if result.vpn_client:
        report["vpn_client"] = result.vpn_client.to_dict()
    if result.vless_uri:
        report["vless_uri"] = result.vless_uri
    if result.errors:
        report["errors"] = result.errors

    print(json.dumps(report, indent=2, ensure_ascii=False))


def full_pipeline_dry_run() -> None:
    from scripts.singbox_full_pipeline_dry_run import run_pipeline

    run_pipeline(telegram_id=None, email="main-dry-run-user")


def main() -> None:
    parser = argparse.ArgumentParser(description="KontaktVPN App")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run a dry-run client creation test",
    )
    parser.add_argument(
        "--full-pipeline-dry-run",
        action="store_true",
        help="Run the full sing-box pipeline dry-run",
    )
    args = parser.parse_args()

    if args.dry_run:
        dry_run()
        return

    if args.full_pipeline_dry_run:
        full_pipeline_dry_run()
        return

    print("No action specified. Use --dry-run or --full-pipeline-dry-run.")


if __name__ == "__main__":
    main()
