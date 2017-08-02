python
import sys
sys.path.insert(0, '~/Git/GDBUsabilityEnhancements/printers')
from examplepretty.printers import register_example_printers
register_example_printers()
from qt4pretty.printers import register_qt4_printers
register_qt4_printers()
end
