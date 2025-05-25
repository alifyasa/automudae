
from automudae.client import AutoMudaeClient
from automudae.config.v1 import get_config
from automudae.logging import handler

def main():
    config = get_config()
    client = AutoMudaeClient(config)
    # client.setup()
    client.run(token=client.config.discord.token, log_handler=handler, root_logger=True)


if __name__ == "__main__":
    main()
