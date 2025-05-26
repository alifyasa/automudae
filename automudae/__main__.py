import yaml

from automudae.args import parser
from automudae.client import AutoMudaeClient
from automudae.config.v1 import Config, get_config


def main() -> None:
    args = parser.parse_args()
    config = get_config(path=args.file)

    config_schema = yaml.dump(Config.model_json_schema())
    with open("config_schema.yaml", "w") as f:
        f.write(config_schema)

    client = AutoMudaeClient(config)
    client.run(token=client.config.discord.token, root_logger=True)


if __name__ == "__main__":
    main()
