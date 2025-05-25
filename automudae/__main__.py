from automudae.client import AutoMudaeClient
from automudae.config.v1 import get_config


def main() -> None:
    config = get_config()
    client = AutoMudaeClient(config)
    client.run(token=client.config.discord.token, root_logger=True)


if __name__ == "__main__":
    main()
