python
import sys
sys.path.insert(0, '/home/sterob01/Git/GDBUsabilityEnhancements/printers')
from boostpretty.printers import register_printer_gen
register_printer_gen(None)
from examplepretty.printers import register_example_printers
register_example_printers()
from qt4pretty.printers import register_qt4_printers
register_qt4_printers()
end
