import logging.config

from settings import logger_config


logging.config.dictConfig(logger_config)

logger = logging.getLogger('app_logger')


def new_function():
    name = 'oleg'
    logger.debug('Enter in to the new_function()', extra={'new_name': name})


def main():
    name = 'pumpurum'
    logger.debug('Enter in to the main()', extra={'new_name': name})


if __name__ == '__main__':
    new_function()
    main()
