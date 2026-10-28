"""Offline reporting commands and the explicitly opted-in model invocation."""

import json
from pathlib import Path

from ..analyst import analyze, prepare_report
from ..evaluation import evaluate_suite
from ..providers.azure_foundry import AzureFoundryClient, load_foundry_config
from ..storage import load_json, save_private
from .schema import REPORT_SCHEMA
from .validation import report_document, validate_report

COMMANDS = {"report-schema", "prepare-report", "validate-report", "evaluate", "analyze"}


def add_commands(commands):
    schema = commands.add_parser(
        "report-schema", help="Export the investigation report JSON Schema"
    )
    schema.add_argument("--out", required=True)
    prepare = commands.add_parser(
        "prepare-report", help="Prepare analyst input offline; no model call"
    )
    prepare.add_argument("--bundle", required=True)
    prepare.add_argument("--out", required=True)
    validate = commands.add_parser(
        "validate-report", help="Check report structure and citation integrity offline"
    )
    validate.add_argument("--bundle", required=True)
    validate.add_argument("--report", required=True)
    validate.add_argument("--out")
    evaluate = commands.add_parser(
        "evaluate", help="Score saved reports against separate fixture expectations offline"
    )
    evaluate.add_argument("--suite", required=True, help="Evaluation manifest JSON")
    evaluate.add_argument(
        "--reports", required=True, help="Directory containing CASE_ID.json reports"
    )
    evaluate.add_argument("--out")
    analyst = commands.add_parser(
        "analyze", help="Send reviewed evidence to Azure for one advisory report; no tools"
    )
    analyst.add_argument("--bundle", required=True)
    analyst.add_argument("--out", required=True)
    analyst.add_argument(
        "--model-config", help="Private Foundry config; separate from Wazuh credentials"
    )
    analyst.add_argument(
        "--allow-external",
        action="store_true",
        help="Explicitly permit sending this evidence to Azure Foundry",
    )


def _emit(data, output=None):
    value = {"output": str(save_private(output, data))} if output else data
    print(json.dumps(value, indent=2, ensure_ascii=False))


def run_command(args):
    if args.command == "report-schema":
        _emit(REPORT_SCHEMA, args.out)
        return 0
    if args.command == "prepare-report":
        _emit(prepare_report(load_json(args.bundle)), args.out)
        return 0
    if args.command == "validate-report":
        result = validate_report(report_document(load_json(args.report)), load_json(args.bundle))
        _emit(result, args.out)
        return 0 if result["valid"] else 2
    if args.command == "evaluate":
        result = evaluate_suite(args.suite, args.reports)
        _emit(result, args.out)
        return 0 if result["passed"] == result["total"] else 2
    if not args.allow_external:
        raise ValueError(
            "analyze sends evidence to Azure Foundry. Review the bundle and explicitly pass --allow-external"
        )
    output = Path(args.out).expanduser()
    if output.exists() or output.is_symlink():
        raise FileExistsError(
            "Analysis output already exists; refusing a billable request before overwriting"
        )
    bundle = load_json(args.bundle)
    config = load_foundry_config(args.model_config)
    result = analyze(bundle, AzureFoundryClient(config))
    result["model"].update({"provider": "azure_foundry", "requested_model": config.model})
    saved = save_private(output, result)
    report = result["report"]
    print(
        json.dumps(
            {
                "output": str(saved),
                "status": result["status"],
                "disposition": report.get("disposition") if isinstance(report, dict) else None,
                "usage": result["model"]["usage"],
                "human_review_required": True,
            },
            indent=2,
        )
    )
    return 0 if result["status"] == "validated" else 2
