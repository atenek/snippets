import logging


class NewFunctionFilter(logging.Filter):
    def filter(self, record):
        # print(dir(record))
        print(record.new_name)
        return record.funcName == 'new_function'


logger_config = {
    'version': 1,
    'disable_existing_loggers': False,

    'formatters': {
        'std_format': {
            'format': '{asctime} - {levelname} - {name} - {message}',
            'style': '{'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'DEBUG',
            'formatter': 'std_format',
            'filters': ['new_filter']
        }
    },
    'loggers': {
        'app_logger': {
            'level': 'DEBUG',
            'handlers': ['console']
            #'propagate': False
        }
    },

    'filters': {
        'new_filter': {
            '()': NewFunctionFilter   # filters.py > import filters > filters.NewFunctionFilter
        }
    },
    # 'root': {}   # '': {}
    # 'incremental': True
}
