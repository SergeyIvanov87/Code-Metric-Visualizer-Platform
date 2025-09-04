#!/usr/bin/python

def get_symbols_canonization_dict():
    return { "?":"%question%",
             "<":"%left-angle-bracket%",
             ">":"%right-angle-bracket%",
             "/":"%slash%",
             '\\' :"%backslash%",
             "|":"%pipe%",
             "*":"%asterisk%",
             ":":"%colon%"
    }

def get_symbol_decanonization_dict():
    reverse_dict = {}
    for k,v in get_symbols_canonization_dict().items():
        reverse_dict[v] = k
    return reverse_dict

def canonize_rrd_source_name(source_name):
    # symbol ':' is forbidden in rrd-file names, because rrdtool graph uses it as a DEF args separator
    # replace it with ';'
    # Other symbols forbidden as symbol in item names across different OS
    # UNIX{/}, Winows{<,>,:,",/,\,|,?,*}
    # This requirements is a consequence ofthe fact than `source_name` represents
    # name of the file on filesystem, thus it must not contain any special character
    canonize_map = get_symbols_canonization_dict()
    # replace the last : on + to determine line in a file with function overloading
    if int(source_name.count(':') % 2) != 0:
        last_colon_pos = source_name.rfind(':')
        source_name = source_name[:last_colon_pos] + "+" + source_name[last_colon_pos + 1:]
    # canonize the elapsed content of the string
    for k,v in canonize_map.items():
        source_name = source_name.replace(k, v)
    return source_name


def decanonize_rrd_source_name(source_name):
    decanonize_map = get_symbol_decanonization_dict()
    # canonize the elapsed content of the string
    for k,v in decanonize_map.items():
        source_name = source_name.replace(k, v)
    return source_name
