import logging


logging.basicConfig()
# logger = logging.getLogger()
# print(logger)

app_logger = logging.getLogger('app_logger')

console_handler = logging.StreamHandler()
app_logger.addHandler(console_handler)

f = logging.Formatter(fmt='%(levelname)s - %(name)s - %(message)s')
console_handler.setFormatter(f)


utils_logger = logging.getLogger('app_logger.utils')
utils_logger.setLevel('DEBUG')


# root.app_logger.utils_logger


def main():
    utils_logger.debug('Hello world')


if __name__ == '__main__':
    main()
