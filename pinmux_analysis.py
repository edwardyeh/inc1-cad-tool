#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
#
# Pinmux Table Analysis for the iVot project
#
# Copyright (C) 2025 Yeh, Hsin-Hsien <yhh76227@gmail.com>
#
import argparse
import json
import openpyxl
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from jsonschema import validate, ValidationError
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from pathlib import Path


##############################################################################
### Global Variable


CONFIG_SCHEMA = {
    '$schema': 'https://json-schema.org/draft/2020-12/schema',
    'type': 'object',
    'additionalProperties': False,
    'required': ['hide_parse', 'table_parse', 'function_group', 'function_ignore'],
    'properties': {
        'hide_parse': {'type': 'boolean'},
        'table_parse': {
            'type': 'object',
            'additionalProperties': False,
            'required': ['active_ws', 'function', 'pad_name', 'ref_name'],
            'properties': {
                'active_ws': {'type': 'string'},
                'function': {
                    'type': 'object',
                    'additionalProperties': False,
                    'required': ['rid', 'pattern'],
                    'properties': {
                        'rid': {'type': 'integer'},
                        'pattern': {
                            'type': 'array',
                            'items': {'type': 'string'}
                        }
                    }
                },
                'pad_name': {
                    'type': 'object',
                    'additionalProperties': False,
                    'required': ['rid', 'pattern'],
                    'properties': {
                        'rid': {'type': 'integer'},
                        'pattern': {'type': 'string'}
                    }
                },
                'ref_name': {
                    'type': 'object',
                    'additionalProperties': False,
                    'required': ['rid', 'pattern'],
                    'properties': {
                        'rid': {'type': 'integer'},
                        'pattern': {'type': 'string'}
                    }
                }
            }
        },
        'function_group': {
            'type': 'object',
            'additionalProperties': False,
            'patternProperties': {
                r'\S+': {
                    'type': 'object',
                    'additionalProperties': False,
                    'required': ['pattern', 'clock', 'custom'],
                    'properties': {
                        'pattern': {'type': 'string'},
                        'clock': {
                            'type': 'array',
                            'items': {'type': 'string'}
                        },
                        'custom': {
                            'type': 'object',
                            'additionalProperties': False,
                            'patternProperties': {
                                r'\S+': {'type': 'string'}
                            }
                        }
                    }
                }
            }
        },
        'function_ignore': {
            'type': 'array',
            'items': {'type': 'string'}
        }
    }
}

DIR_I_TAG = {'I', 'IO'}
DIR_O_TAG = {'O', 'IO'}
DIR_TAG = set(list(DIR_I_TAG) + list(DIR_O_TAG))


##############################################################################
### Data Structure


@dataclass
class Pin:
    func: str
    dir:  str
    pad:  str
    ref:  str


@dataclass
class SubGroup:
    pin_list: list[Pin] = field(default_factory=list)
    data_pin: list[Pin] = field(default_factory=list)
    clk_pin:  list[Pin] = field(default_factory=list)


@dataclass
class GroupData:
    repat:     re.Pattern
    clk_repat: list[re.Pattern] = field(default_factory=list)
    cus_pin:   dict[re.Pattern] = field(default_factory=dict)
    sub_group: dict[SubGroup]   = field(default_factory=dict)


##############################################################################
### Procedure


def parse_table(config: dict, workbook: Workbook, is_debug: bool=False) -> dict:
    """Parsing the pinmux table"""
    ws = workbook[config['table_parse']['active_ws']]

    ### Get table format
    re_pat_list = []
    for pat in config['table_parse']['function']['pattern']:
        re_pat_list.append(re.compile(pat))

    func_cidx_list = []
    for i, cell in enumerate(ws[config['table_parse']['function']['rid']], start=1):
        for re_pat in re_pat_list:
            if re_pat.fullmatch(str(cell.value)):
                func_cidx_list.append(i)
                break
    func_cidx_list = [(x-1, x) for x in func_cidx_list]

    re_pat = re.compile(config['table_parse']['pad_name']['pattern'])
    pad_cidx = None
    for i, cell in enumerate(ws[config['table_parse']['pad_name']['rid']], start=1):
        value = str(cell.value).replace('\n', ' ').strip()
        if re_pat.fullmatch(value):
            pad_cidx = i
            break

    re_pat = re.compile(config['table_parse']['ref_name']['pattern'])
    ref_cidx = None
    for i, cell in enumerate(ws[config['table_parse']['ref_name']['rid']], start=1):
        value = str(cell.value).replace('\n', ' ').strip()
        if re_pat.fullmatch(value):
            ref_cidx = i
            break

    if is_debug:
        print('Function column index:', func_cidx_list)
        print('Pad name index:', pad_cidx)
        print('Ref name index:', ref_cidx)

    ### Get ignore list
    ignore_list = []
    for pat in config['function_ignore']:
        ignore_list.append(re.compile(pat))

    if is_debug:
        print('\nIgnore list: [')
        for repat in ignore_list:
            print(f'  {repat},')
        print(']')

    ### Get group format
    unknown_list = []
    group_dict = {}
    for gname, gdata in config['function_group'].items():
        group_dict[gname] = (grp_data := GroupData(repat=re.compile(gdata['pattern'])))
        for clk_pat in gdata['clock']:
            grp_data.clk_repat.append(re.compile(clk_pat))
        for name, pat in gdata['custom'].items():
            grp_data.cus_pin[name] = re.compile(pat)
        grp_data.sub_group['default'] = SubGroup()

    if is_debug:
        debug_group_dict(group_dict, 'initial')

    ### Parsing table
    for ridx in range(1, ws.max_row+1):
        # row hidden check
        if ws.row_dimensions[ridx].hidden:
            continue

        for dir_cidx, func_cidx in func_cidx_list:
            # cell strike check
            if ws.cell(ridx, dir_cidx).font.strike == True:
                continue

            # ignore function check
            func_name, is_ignore = str(ws.cell(ridx, func_cidx).value), False
            for repat in ignore_list:
                if repat.fullmatch(func_name):
                    is_ignore = True
                    break
            if is_ignore:
                continue

            # parsing content
            direction = ws.cell(ridx, dir_cidx).value
            if direction is not None and str(direction).upper() in DIR_TAG:
                pin_data = Pin(
                    func=func_name,
                    dir=str(direction).upper(),
                    pad=ws.cell(ridx, pad_cidx).value,
                    ref=ws.cell(ridx, ref_cidx).value
                )
                
                if is_debug:
                    print(pin_data)

                is_unknown = True
                for gname, gdata in group_dict.items():
                    if (m := gdata.repat.fullmatch(pin_data.func)):
                        is_clk, is_unknown = False, False
                        for repat in gdata.clk_repat:
                            if repat.fullmatch(pin_data.func):
                                is_clk = True
                                break

                        if len(m.groups()):
                            sgdata = gdata.sub_group.setdefault(m[1], SubGroup())
                        else:
                            sgdata = gdata.sub_group['default']

                        if is_clk:
                            sgdata.clk_pin.append(pin_data)
                        else:
                            sgdata.data_pin.append(pin_data)
                        sgdata.pin_list.append(pin_data)

                if is_unknown:
                    unknown_list.append(pin_data)

    group_dict['unknown'] = unknown_list
    if is_debug:
        debug_group_dict(group_dict, 'update')
    return group_dict


def print_group(group_dict: dict, out_fp):
    """Print the group result"""

    ### Sub function
    def _print_pin(pin_list: list, tabspace: int=0):
        func_len, pad_len, ref_len = 0, 0, 0
        for pin in pin_list:
            if (strlen := len(pin.func)) > func_len:
                func_len = strlen
            if (strlen := len(pin.pad)) > pad_len:
                pad_len = strlen
            if (strlen := len(pin.ref)) > ref_len:
                ref_len = strlen

        for pin in pin_list:
            print('{}{} {:2} {} ({})'.format(
                    ' ' * tabspace,
                    pin.func.ljust(func_len), 
                    pin.dir, 
                    pin.pad.ljust(pad_len), 
                    pin.ref.ljust(ref_len)), 
                  file=out_fp)

    ### Print group result
    print('\n=== Category:\n', file=out_fp)
    for gname, gdata in group_dict.items():
        if gname == 'unknown':
            continue
        print(f'    {gname}: '.ljust(10), end='', file=out_fp)
        msg = ''
        for sgname in gdata.sub_group.keys():
            if sgname == 'default':
                continue
            msg += f'{sgname}, '
        print(msg[:-2], file=out_fp)

    if len(group_dict['unknown']):
        print('\n=== Unknown Function:\n', file=out_fp)
        # print the information of pins
        _print_pin(group_dict['unknown'], tabspace=4)

    print('\n=== Function:\n', file=out_fp)
    for gname, gdata in group_dict.items():
        if gname == 'unknown':
            continue
        for sgname, sgdata in gdata.sub_group.items():
            if len(sgdata.pin_list) == 0:
                continue
            if sgname == 'default':
                title = f'{gname} (ungroup)'
            else:
                title = sgname
                
            print(f'- {title}:\n', file=out_fp)

            # print pin information
            _print_pin(sgdata.pin_list, tabspace=4)
            print(file=out_fp)

            # print tool command
            cus_pin_dict = defaultdict(list)
            var_len = len(sgname) + 9

            ci_list, co_list = [], []
            for pin in sgdata.clk_pin:
                is_cus = False
                for cus_name, cus_repat in gdata.cus_pin.items():
                    if cus_repat.fullmatch(pin.func):
                        cus_pin_dict[cus_name].append(pin.pad)
                        is_cus = True
                        break

                if is_cus:
                    continue
                if pin.dir in DIR_I_TAG:
                    ci_list.append(pin.pad)
                if pin.dir in DIR_O_TAG:
                    co_list.append(pin.pad)

            if len(ci_list):
                print('{}set {} [get_ports {{{}}}]'.format(
                        ' ' * 4,
                        (sgname + '_PADCLK_I').ljust(var_len),
                        ','.join(ci_list)), file=out_fp)

            if len(co_list):
                print('{}set {} [get_ports {{{}}}]'.format(
                        ' ' * 4,
                        (sgname + '_PADCLK_O').ljust(var_len),
                        ','.join(co_list)), file=out_fp)

            di_list, do_list = [], []
            for pin in sgdata.data_pin:
                is_cus = False
                for cus_name, cus_repat in gdata.cus_pin.items():
                    if cus_repat.fullmatch(pin.func):
                        cus_pin_dict[cus_name].append(pin.pad)
                        is_cus = True
                        break

                if is_cus:
                    continue
                if pin.dir in DIR_I_TAG:
                    di_list.append(pin.pad)
                if pin.dir in DIR_O_TAG:
                    do_list.append(pin.pad)

            if len(di_list):
                print('{}set {} [get_ports {{{}}}]'.format(
                        ' ' * 4,
                        (sgname + '_PORT_I').ljust(var_len),
                        ','.join(di_list)), file=out_fp)

            if len(do_list):
                print('{}set {} [get_ports {{{}}}]'.format(
                        ' ' * 4,
                        (sgname + '_PORT_O').ljust(var_len),
                        ','.join(do_list)), file=out_fp)

            print(file=out_fp)

            if len(cus_pin_dict):
                var_len = 0
                for var_name in cus_pin_dict.keys():
                    if (new_len := len(var_name)) > var_len:
                        var_len = new_len
                var_len += 1

                for var_name, pin_list in cus_pin_dict.items():
                    print('{}set {} [get_ports {{{}}}]'.format(
                            ' ' * 4,
                            (sgname + '_' + var_name).ljust(var_len),
                            ','.join(pin_list)), file=out_fp)
                print(file=out_fp)


def debug_group_dict(group_dict: dict, status: str):
    print()
    print(f'Group({status}): {{')
    for gname, gdata in group_dict.items():
        if gname == 'unknown':
            print(f'  {gname}: [')
            for pin in gdata:
                print(f'    {pin},')
            print(f'  ],')
        else:
            print(f'  {gname}: {{')
            print(f'    repat:     {gdata.repat}')
            print(f'    clk_repat: {gdata.clk_repat}')
            print(f'    cus_pin:   {gdata.cus_pin}')
            for sgname, sgdata in gdata.sub_group.items():
                print(f'    {sgname}: {{')
                print(f'      data_pin: [')
                for pin in sgdata.data_pin:
                    print(f'        {pin},')
                print(f'      ],')
                print(f'      clk_pin: [')
                for pin in sgdata.clk_pin:
                    print(f'        {pin},')
                print(f'      ],')
                print(f'    }},')
            print(f'  }},')
    print('}\n')


##############################################################################
### Main


def create_argparse() -> argparse.ArgumentParser:
    """Create an argument parser."""
    parser = argparse.ArgumentParser(
                formatter_class=argparse.RawTextHelpFormatter,
                description='Pinmux Table Analysis for the iVot project')

    parser.add_argument('conf_fp', help="Configuration file") 
    parser.add_argument('table_fp', help="File path of the pinmux table") 
    parser.add_argument('-outfile', dest='out_fp', metavar='<file_path>', 
                            help="Set the output file path") 
    return parser


def main():
    """Main function."""
    parser = create_argparse()
    args = parser.parse_args()

    with open(args.conf_fp, 'r', encoding='utf-8') as json_fp:
        config = json.load(json_fp)
    try:
        validate(instance=config, schema=CONFIG_SCHEMA)
    except ValidationError as e:
        print(f'Error: JSON schema check fail.')
        print(e)
        exit(1)

    wb = openpyxl.load_workbook(args.table_fp)
    group_dict = parse_table(config, wb, is_debug=False)

    if args.out_fp is None:
        print_group(group_dict, sys.stdout)
    else:
        with open(args.out_fp, 'w') as fp:
            print_group(group_dict, fp)


if __name__ == '__main__':
    main()


