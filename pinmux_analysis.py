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
from jsonschema import validate, ValidationError
from pathlib import Path


##############################################################################
### Global Variable


CONFIG_SCHEMA = {
    '$schema': 'https://json-schema.org/draft/2020-12/schema',
    'type': 'object',
    'additionalProperties': False,
    'required': ['hide_parse', 'column_parse', 'function_group'],
    'properties': {
        'hide_parse': {'type': 'boolean'},
        'column_parse': {
            'type': 'object',
            'additionalProperties': False,
            'required': ['function', 'pad_name', 'ref_name'],
            'properties': {
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
                    'required': ['pattern'],
                    'properties': {
                        'pattern': {'type': 'string'},
                        'clock': {
                            'type': 'array',
                            'items': {'type': 'string'}
                        },
                    }
                }
            }
        }
    }
}


##############################################################################
### Procedure


##############################################################################
### Main


def create_argparse() -> argparse.ArgumentParser:
    """Create an argument parser."""
    parser = argparse.ArgumentParser(
                formatter_class=argparse.RawTextHelpFormatter,
                description='Pinmux Table Analysis for the iVot project')

    parser.add_argument('conf_fp', help="Configuration file") 
    parser.add_argument('table_fp', help="File path of the pinmux table") 
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

    import pdb; pdb.set_trace()


if __name__ == '__main__':
    main()


