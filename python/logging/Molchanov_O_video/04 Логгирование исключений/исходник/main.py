import logging.config

from settings import logger_config


logging.config.dictConfig(logger_config)

logger = logging.getLogger('app_logger')


words = ['new house', 'apple', 'ice cream', 3]

def main():
    for item in words:
        try:
            print(item.split(' '))
        except:
            logger.exception(f'Exception here, item = {item}')
            pass


if __name__ == '__main__':
    main()
