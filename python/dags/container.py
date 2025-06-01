from datetime import datetime as dt

class asset_base:
    def __init__(self, context, deps: dict = {}):
        self.deps = deps
        self._status = None
        self._value = None
        self._value_timestamp = None

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self._value = value
        self._status = "done"
        self._value_timestamp = dt.now()

    @property
    def status(self):
        return self._status


class TEST_asset0(asset_base):
    pass


class TEST_asset1(asset_base):
    pass


class TEST_asset2(asset_base):
    pass


context = { }
a00 = TEST_asset0(context)
a01 = TEST_asset1(context, deps=[a00])
a02 = TEST_asset1(context, deps=[a00])
a03 = TEST_asset1(context, deps=[a00])
a04 = TEST_asset1(context, deps=[a00])
a20 = TEST_asset2(context, deps=[a00, a01, a02, a03, a04])

aList = [a00, a01, a02, a03, a04, a20]


class Container:
    def __init__(self):
        self.graph = {}

    def add(self, name: str, obj: object):
        if name in self.graph.keys():
            raise Exception
        else:
            obj.graph = self.graph
            self.graph.update({name: obj})


    def get_all(self, ):
        pass

    def get_item(self, item):
        pass

    def dag(self):
        for item in self.li:
            if (not item.deps) or item.status == "done":
                print(f"{item} ", end='')


if __name__ == "__main__":
    container = Container()

    container.add("lbiam_token", TEST_asset0)
    container.add("lbman_get_lb", TEST_asset1())








