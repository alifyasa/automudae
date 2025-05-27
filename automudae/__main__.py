import yaml

from automudae.args import parser
from automudae.client import AutoMudaeClient
from automudae.config import Config


def main() -> None:
    args = parser.parse_args()
    config = Config.from_file(path=args.file)

    config_schema = yaml.dump(Config.model_json_schema())
    with open("config_schema.yaml", "w") as f:
        f.write(config_schema)

    client = AutoMudaeClient(config)
    client.run(token=client.config.discord.token, root_logger=True)


if __name__ == "__main__":
    main()
