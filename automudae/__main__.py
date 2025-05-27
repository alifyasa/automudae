import yaml

from automudae.agent.agent import AutoMudaeAgent
from automudae.args import parser
from automudae.config import Config


def main() -> None:
    args = parser.parse_args()
    config = Config.from_file(path=args.file)

    config_schema = yaml.dump(Config.model_json_schema())
    with open("configs/schema.yaml", "w") as f:
        f.write(config_schema)

    agent = AutoMudaeAgent(config)
    agent.run(token=agent.config.discord.token, root_logger=True)


if __name__ == "__main__":
    main()
