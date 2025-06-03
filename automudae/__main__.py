"""
AutoMudae

Automatically Play Mudae
"""

import yaml

from automudae.agent import AutoMudaeAgent
from automudae.args import parser
from automudae.config import Config


def main() -> None:
    """Entry point for the AutoMudae Discord Bot"""
    args = parser.parse_args()
    config = Config.from_file(path=args.file)

    config_schema = yaml.dump(Config.model_json_schema())
    with open("config/schema.yaml", "w", encoding="utf-8") as f:
        f.write(config_schema)

    agent = AutoMudaeAgent(config)
    agent.run(token=agent.config.discord.token, root_logger=True)


if __name__ == "__main__":
    main()
