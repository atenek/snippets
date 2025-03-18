import pandas as pd


class PandasFile:   # from f-downloader
    sep = ';'
    encoding = 'cp1251'

    def __init__(self, pd_filename):
        self.pd_filename = pd_filename
        self.pd_file = None
        self.open_csv(pd_filename)

    def open_csv(self, pd_filename):
        self.pd_file = pd.read_csv(pd_filename, sep=PandasFile.sep, encoding=PandasFile.encoding, dtype=str)

    def save_csv(self, pd_filename):
        pass

    def get_param(self, keycode, columnname):
        row = self.pd_file[self.pd_file['SECID'] == keycode]
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

    def __str__(self):
        return str(self.pd_file)


if __name__ == "__main__":
    pd_file = PandasFile("/resources/GAZP_2025-03-12.txt")
    print(pd_file)
