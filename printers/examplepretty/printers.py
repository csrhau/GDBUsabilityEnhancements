import gdb

class FooPrinter:
    def __init__(self, val):
        self.val = val
    def to_string(self):
        return 'foo object'

class BarPrinter:
    def __init__(self, val):
        self.val = val
    def to_string(self):
        return 'bar object'


def register_example_printers():
    pp = gdb.printing.RegexpCollectionPrettyPrinter("example")
    pp.add_printer('foo', '^foo$', FooPrinter)
    pp.add_printer('bar', '^bar$', BarPrinter)
    gdb.printing.register_pretty_printer(gdb.current_objfile(), pp)
