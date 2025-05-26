import argparse

parser = argparse.ArgumentParser(
    prog="Auto Mudae", description="Automated script for Mudae. Requires a config file."
)
parser.add_argument(
    "-f", "--file", type=str, required=True, help="Path to the config file"
)
