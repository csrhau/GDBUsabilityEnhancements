import gdb
import itertools
import re

class QStringPrinter:
    def __init__(self, val):
        self.val = val

    def is_null(self):
        st_null = self.val['shared_null'].address
        return st_null == self.val['d']

    def to_string(self):
        
        if self.is_null():
             return 'QString::null'
         
        size = self.val['d']['size']

        if (size > 10000): size = 10000;
        #while i < size:
        #    char = self.val['d']['data'][i]
        #    if (char > 127):
        #        ret += "\\u%x" % int(char)
        #    else:
        #        ret += chr(char)
        #    i = i + 1
        #return ret
        try:
            dataAsCharPointer = self.val['d']['data'].cast(gdb.lookup_type("char").pointer())
            return dataAsCharPointer.string(encoding = 'UTF-16', length = size * 2)
        except UnicodeDecodeError:
            return '<uninitialized/error value>'

    def display_hint (self):
        return 'string' if not self.is_null() else 'array'


class QByteArrayPrinter:

    def __init__(self, val):
        self.val = val

    class _iterator:
        def __init__(self, data, size):
            self.data = data
            self.size = size
            self.count = 0

        def __iter__(self):
            return self

        def next(self):
            if self.count >= self.size:
                raise StopIteration
            count = self.count
            self.count = self.count + 1
            return ('[%d]' % count, self.data[count])

    def children(self):
        return self._iterator(self.val['d']['data'], self.val['d']['size'])

    def to_string(self):
        #todo: handle charset correctly
        return self.val['d']['data'].string()

    def display_hint (self):
        return 'string'

class QListPrinter:
    "Print a QList"

    class _iterator:
        def __init__(self, nodetype, d):
            self.nodetype = nodetype
            self.d = d
            self.count = 0

        def __iter__(self):
            return self

        def next(self):
            if self.count >= self.d['end'] - self.d['begin']:
                raise StopIteration
            count = self.count
            array = self.d['array'][self.d['begin'] + count]

            #from QTypeInfo::isLarge
            isLarge = self.nodetype.sizeof > gdb.lookup_type('void').pointer().sizeof

            #isStatic is not needed anymore since Qt 4.6
            #isPointer = self.nodetype.code == gdb.TYPE_CODE_PTR
            #
            ##unfortunately we can't use QTypeInfo<T>::isStatic as it's all inlined, so use
            ##this list of types that use Q_DECLARE_TYPEINFO(T, Q_MOVABLE_TYPE)
            ##(obviously it won't work for custom types)
            #movableTypes = ['QRect', 'QRectF', 'QString', 'QMargins', 'QLocale', 'QChar', 'QDate', 'QTime', 'QDateTime', 'QVector',
            #    'QRegExpr', 'QPoint', 'QPointF', 'QByteArray', 'QSize', 'QSizeF', 'QBitArray', 'QLine', 'QLineF', 'QModelIndex', 'QPersitentModelIndex',
            #    'QVariant', 'QFileInfo', 'QUrl', 'QXmlStreamAttribute', 'QXmlStreamNamespaceDeclaration', 'QXmlStreamNotationDeclaration',
            #    'QXmlStreamEntityDeclaration']
            #if movableTypes.count(self.nodetype.tag):
            #    isStatic = False
            #else:
            #    isStatic = not isPointer
            isStatic = False

            if isLarge or isStatic: #see QList::Node::t()
                node = array.cast(gdb.lookup_type('QList<%s>::Node' % self.nodetype).pointer())
            else:
                node = array.cast(gdb.lookup_type('QList<%s>::Node' % self.nodetype))
            self.count = self.count + 1
            return ('[%d]' % count, node['v'].cast(self.nodetype))

    def __init__(self, val, container, itype):
        self.val = val
        self.container = container
        if itype == None:
            self.itype = self.val.type.template_argument(0)
        else:
            self.itype = gdb.lookup_type(itype)

    def children(self):
        return self._iterator(self.itype, self.val['d'])

    def to_string(self):
        if self.val['d']['end'] == self.val['d']['begin']:
            empty = "empty "
        else:
            empty = ""

        return "%s%s<%s>" % ( empty, self.container, self.itype )

class QVectorPrinter:
    "Print a QVector"

    class _iterator:
        def __init__(self, nodetype, d, p):
            self.nodetype = nodetype
            self.d = d
            self.p = p
            self.count = 0

        def __iter__(self):
            return self

        def next(self):
            if self.count >= self.p['size']:
                raise StopIteration
            count = self.count

            self.count = self.count + 1
            return ('[%d]' % count, self.p['array'][count])

    def __init__(self, val, container):
        self.val = val
        self.container = container
        self.itype = self.val.type.template_argument(0)

    def children(self):
        return self._iterator(self.itype, self.val['d'], self.val['p'])

    def to_string(self):
        if self.val['d']['size'] == 0:
            empty = "empty "
        else:
            empty = ""

        return "%s%s<%s>" % ( empty, self.container, self.itype )

class QMapPrinter:
    "Print a QMap"

    class _iterator:
        def __init__(self, val):
            self.val = val
            self.ktype = self.val.type.template_argument(0)
            self.vtype = self.val.type.template_argument(1)
            self.data_node = self.val['e']['forward'][0]
            self.count = 0

        def __iter__(self):
            return self

        def payload (self):

            #we can't use QMapPayloadNode as it's inlined
            #as a workaround take the sum of sizeof(members)
            ret = self.ktype.sizeof
            ret += self.vtype.sizeof
            ret += gdb.lookup_type('void').pointer().sizeof

            #but because of data alignment the value can be higher
            #so guess it's aliged by sizeof(void*)
            #TODO: find a real solution for this problem
            ret += ret % gdb.lookup_type('void').pointer().sizeof

            ret -= gdb.lookup_type('void').pointer().sizeof
            return ret

        def concrete (self, data_node):
            node_type = gdb.lookup_type('QMapNode<%s, %s>' % (self.ktype, self.vtype)).pointer()
            return (data_node.cast(gdb.lookup_type('char').pointer()) - self.payload()).cast(node_type)

        def next(self):
            if self.data_node == self.val['e']:
                raise StopIteration
            node = self.concrete(self.data_node).dereference()
            if self.count % 2 == 0:
                item = node['key']
            else:
                item = node['value']
                self.data_node = node['forward'][0]

            result = ('[%d]' % self.count, item)
            self.count = self.count + 1
            return result


    def __init__(self, val):
        self.val = val

    def children(self):
        return self._iterator(self.val)

    def to_string(self):
        if self.val['d']['size'] == 0:
            empty = "empty "
        else:
            empty = ""

        return "%sQMap<%s, %s>" % ( empty , self.val.type.template_argument(0), self.val.type.template_argument(1) )

    def display_hint (self):
        return 'map'

class QHashPrinter:
    "Print a QHash"

    class _iterator:
        def __init__(self, val):
            self.val = val
            self.d = self.val['d']
            self.ktype = self.val.type.template_argument(0)
            self.vtype = self.val.type.template_argument(1)
            self.end_node = self.d.cast(gdb.lookup_type('QHashData::Node').pointer())
            self.data_node = self.firstNode()
            self.count = 0

        def __iter__(self):
            return self

        def hashNode (self):
            "Casts the current QHashData::Node to a QHashNode and returns the result. See also QHash::concrete()"
            return self.data_node.cast(gdb.lookup_type('QHashNode<%s, %s>' % (self.ktype, self.vtype)).pointer())

        def firstNode (self):
            "Get the first node, See QHashData::firstNode()."
            e = self.d.cast(gdb.lookup_type('QHashData::Node').pointer())
            #print "QHashData::firstNode() e %s" % e
            bucketNum = 0
            bucket = self.d['buckets'][bucketNum]
            #print "QHashData::firstNode() *bucket %s" % bucket
            n = self.d['numBuckets']
            #print "QHashData::firstNode() n %s" % n
            while n:
                #print "QHashData::firstNode() in while, n %s" % n;
                if bucket != e:
                    #print "QHashData::firstNode() in while, return *bucket %s" % bucket
                    return bucket
                bucketNum += 1
                bucket = self.d['buckets'][bucketNum]
                #print "QHashData::firstNode() in while, new bucket %s" % bucket
                n -= 1
            #print "QHashData::firstNode() return e %s" % e
            return e


        def nextNode (self, node):
            "Get the nextNode after the current, see also QHashData::nextNode()."
            #print "******************************** nextNode"
            #print "nextNode: node %s" % node
            next = node['next'].cast(gdb.lookup_type('QHashData::Node').pointer())
            e = next

            #print "nextNode: next %s" % next
            if next['next']:
                #print "nextNode: return next"
                return next

            #print "nextNode: node->h %s" % node['h']
            #print "nextNode: numBuckets %s" % self.d['numBuckets']
            start = (node['h'] % self.d['numBuckets']) + 1
            bucketNum = start
            #print "nextNode: start %s" % start
            bucket = self.d['buckets'][start]
            #print "nextNode: bucket %s" % bucket
            n = self.d['numBuckets'] - start
            #print "nextNode: n %s" % n
            while n:
                #print "nextNode: in while; n %s" % n
                #print "nextNode: in while; e %s" % e
                #print "nextNode: in while; *bucket %s" % bucket
                if bucket != e:
                    #print "nextNode: in while; return bucket %s" % bucket
                    return bucket
                bucketNum += 1
                bucket = self.d['buckets'][bucketNum]
                n -= 1
            #print "nextNode: return e %s" % e
            return e

        def next(self):
            "GDB iteration, first call returns key, second value and then jumps to the next hash node."
            if self.data_node == self.end_node:
                raise StopIteration

            node = self.hashNode()

            if self.count % 2 == 0:
                item = node['key']
            else:
                item = node['value']
                self.data_node = self.nextNode(self.data_node)

            self.count = self.count + 1
            return ('[%d]' % self.count, item)

    def __init__(self, val):
        self.val = val

    def children(self):
        return self._iterator(self.val)

    def to_string(self):
        if self.val['d']['size'] == 0:
            empty = "empty "
        else:
            empty = ""

        return "%sQHash<%s, %s>" % ( empty , self.val.type.template_argument(0), self.val.type.template_argument(1) )

    def display_hint (self):
        return 'map'

class QDatePrinter:

    def __init__(self, val):
        self.val = val

    def to_string(self):
        julianDay = self.val['jd']

        if julianDay == 0:
            return "invalid QDate"

        # Copied from Qt sources
        if julianDay >= 2299161:
            # Gregorian calendar starting from October 15, 1582
            # This algorithm is from Henry F. Fliegel and Thomas C. Van Flandern
            ell = julianDay + 68569;
            n = (4 * ell) / 146097;
            ell = ell - (146097 * n + 3) / 4;
            i = (4000 * (ell + 1)) / 1461001;
            ell = ell - (1461 * i) / 4 + 31;
            j = (80 * ell) / 2447;
            d = ell - (2447 * j) / 80;
            ell = j / 11;
            m = j + 2 - (12 * ell);
            y = 100 * (n - 49) + i + ell;
        else:
            # Julian calendar until October 4, 1582
            # Algorithm from Frequently Asked Questions about Calendars by Claus Toendering
            julianDay += 32082;
            dd = (4 * julianDay + 3) / 1461;
            ee = julianDay - (1461 * dd) / 4;
            mm = ((5 * ee) + 2) / 153;
            d = ee - (153 * mm + 2) / 5 + 1;
            m = mm + 3 - 12 * (mm / 10);
            y = dd - 4800 + (mm / 10);
            if y <= 0:
                --y;
        return "%d-%02d-%02d" % (y, m, d)

class QTimePrinter:

    def __init__(self, val):
        self.val = val

    def to_string(self):
        ds = self.val['mds']

        if ds == -1:
            return "invalid QTime"

        MSECS_PER_HOUR = 3600000
        SECS_PER_MIN = 60
        MSECS_PER_MIN = 60000

        hour = ds / MSECS_PER_HOUR
        minute = (ds % MSECS_PER_HOUR) / MSECS_PER_MIN
        second = (ds / 1000)%SECS_PER_MIN
        msec = ds % 1000
        return "%02d:%02d:%02d.%03d" % (hour, minute, second, msec)

class QDateTimePrinter:

    def __init__(self, val):
        self.val = val

    def to_string(self):
        #val['d'] is a QDateTimePrivate, but for some reason casting to that doesn't work
        #so work around by manually adjusting the pointer
        date = self.val['d'].cast(gdb.lookup_type('char').pointer());
        date += gdb.lookup_type('int').sizeof #increment for QAtomicInt ref;
        date = date.cast(gdb.lookup_type('QDate').pointer()).dereference();

        time = self.val['d'].cast(gdb.lookup_type('char').pointer());
        time += gdb.lookup_type('int').sizeof + gdb.lookup_type('QDate').sizeof #increment for QAtomicInt ref; and QDate date;
        time = time.cast(gdb.lookup_type('QTime').pointer()).dereference();
        return "%s %s" % (date, time)

class QUrlPrinter:

    def __init__(self, val):
        self.val = val

    def to_string(self):
        try:
            return self.val['d']['encodedOriginal']
        except RuntimeError as error:
            #if no debug information is avaliable for Qt, try guessing the correct address for encodedOriginal
            #problem with this is that if QUrlPrivate members get changed, this fails
            offset = gdb.lookup_type('int').sizeof
            offset += offset % gdb.lookup_type('void').pointer().sizeof #alignment
            offset += gdb.lookup_type('QString').sizeof * 6
            offset += gdb.lookup_type('QByteArray').sizeof
            encodedOriginal = self.val['d'].cast(gdb.lookup_type('char').pointer());
            encodedOriginal += offset
            encodedOriginal = encodedOriginal.cast(gdb.lookup_type('QByteArray').pointer()).dereference();
            encodedOriginal = encodedOriginal['d']['data'].string()
            return encodedOriginal

class QSetPrinter:
    "Print a QSet"

    def __init__(self, val):
        self.val = val

    class _iterator:
        def __init__(self, hashIterator):
            self.hashIterator = hashIterator
            self.count = 0

        def __iter__(self):
            return self

        def next(self):
            if self.hashIterator.data_node == self.hashIterator.end_node:
                raise StopIteration

            node = self.hashIterator.hashNode()

            item = node['key']
            self.hashIterator.data_node = self.hashIterator.nextNode(self.hashIterator.data_node)

            self.count = self.count + 1
            return ('[%d]' % (self.count-1), item)

    def children(self):
        hashPrinter = QHashPrinter(self.val['q_hash'])
        hashIterator = hashPrinter._iterator(self.val['q_hash'])
        return self._iterator(hashIterator)

    def to_string(self):
        return 'QSet'


class QCharPrinter:

    def __init__(self, val):
        self.val = val

    def to_string(self):
        return unichr(self.val['ucs'])

    def display_hint (self):
        return 'string'
 
class QLinkedListPrinter:
    "Print a QLinkedList"

    class _iterator:
        def __init__(self, nodetype, begin, size):
            self.nodetype = nodetype
            self.it = begin
            self.pos = 0
            self.size = size

        def __iter__(self):
            return self

        def next(self):
            if self.pos >= self.size:
                raise StopIteration

            pos = self.pos
            val = self.it['t']
            self.it = self.it['n']
            self.pos = self.pos + 1
            return ('[%d]' % pos, val)

    def __init__(self, val):
        self.val = val
        self.itype = self.val.type.template_argument(0)

    def children(self):
        return self._iterator(self.itype, self.val['e']['n'], self.val['d']['size'])

    def to_string(self):
        if self.val['d']['size'] == 0:
            empty = "empty "
        else:
            empty = ""

        return "%sQLinkedList<%s>" % ( empty, self.itype )

def register_qt4_printers():
    pp = gdb.printing.RegexpCollectionPrettyPrinter("qt4")
    pp.add_printer('QString', '^QString$', QStringPrinter)
    pp.add_printer('QByteArray', '^QByteArray$', QByteArrayPrinter)
    pp.add_printer('QList', '^QList$', QListPrinter)
    pp.add_printer('QVector', '^QVector$', QVectorPrinter)
    pp.add_printer('QMap', '^QMap$', QMapPrinter)
    pp.add_printer('QHash', '^QHash$', QHashPrinter)
    pp.add_printer('QDate', '^QDate$', QDatePrinter)
    pp.add_printer('QTime', '^QTime$', QTimePrinter)
    pp.add_printer('QDateTime', '^QDateTime$', QDateTimePrinter)
    pp.add_printer('QUrl', '^QUrl$', QUrlPrinter)
    pp.add_printer('QSet', '^QSet$', QSetPrinter)
    pp.add_printer('QChar', '^QChar$', QCharPrinter)
    pp.add_printer('QLinkedList', '^QLinkedList$', QLinkedListPrinter)
    gdb.printing.register_pretty_printer(gdb.current_objfile(), pp)

