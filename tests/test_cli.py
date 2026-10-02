from locdex.cli.app import build_parser

def test_cli_status():
    args=build_parser().parse_args(["status"]); assert args.command=="status"
def test_cli_prepare():
    args=build_parser().parse_args(["prepare","--task","inspect"]); assert args.command=="prepare" and args.task=="inspect"
