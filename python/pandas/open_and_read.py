import pandas as pd


class PandasFile:   # from f-downloader
    sep = ';'
    encoding = 'cp1251'

    def __init__(self, params_filename):
        self._params_filename = params_filename
        self._params_df = pd.read_csv(params_filename, sep=PandasFile.sep, encoding=PandasFile.encoding, dtype=str)

    def get_param(self, keycode, columnname):
        row = self._params_df[self._params_df['SECID'] == keycode]
        if not row.empty:
            value = row[columnname].iloc[0]
            if pd.notna(value):
                try:
                    return str(value)
                except ValueError:
                    print(f"KeyCodeParams Error: {value}; wrong str() convertation")
            else:
                print(f"KeyCodeParams Error: 'keycode':'{keycode}' / 'colum':'{columnname}' is empty")
        else:
            print(f"KeyCodeParams Error: No line for 'keycode':'{keycode}'")

