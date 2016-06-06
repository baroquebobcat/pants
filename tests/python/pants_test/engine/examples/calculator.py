# coding=utf-8
# Copyright 2016 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

import functools
import subprocess
from logging import basicConfig

from pants.base.file_system_project_tree import FileSystemProjectTree
from pants.binaries import binary_util
from pants.engine.engine import LocalSerialEngine
from pants.engine.fs import identity
from pants.engine.scheduler import LocalScheduler
from pants.engine.selectors import Select, SelectDependencies, SelectProjection
from pants.engine.storage import Storage
from pants.util.contextutil import temporary_file_path
from pants.util.objects import datatype
from pants_test.engine.examples.graph_validator import GraphValidator


basicConfig(level='DEBUG')


def printing_func(func):
  @functools.wraps(func)
  def wrapper(*inputs):
    product = func(*inputs)
    return_val = product if product else '<<<Fake-{}-Product>>>'.format(func.__name__)
    print('{} executed for {}, returned: {}'.format(func.__name__, inputs, return_val))
    return return_val
  return wrapper


class CalcSource(datatype('CalcSource', ['source'])):
  pass


class CalcValue(datatype('v', ['value'])):
  pass


class CalcAst(datatype('ast',['wrapped'])):
  pass


class CalcInt(datatype('i', ['value'])):
  pass


class CalcOp(datatype('op', ['op_type', 'lhs', 'rhs'])):
  pass


class CalcOpType(datatype('optype', ['type'])):
  pass


OP_TYPE_ADD = CalcOpType('+')
#OP_TYPE_ADD = '+'


class CalcOpSubexpressions(object):
  def __init__(self, lhs, rhs):
    self.dependencies = [lhs, rhs]
  #- dependencies: len() == 2, [0] lhs, [1] rhs


def parse(calc_source):
  # Handwave 1+1
  return CalcAst(CalcOp(OP_TYPE_ADD, CalcInt(1), CalcInt(1)))


def int_to_val(i):
  return i.value


def perform_op(op, values):
  if op is OP_TYPE_ADD:
    return CalcValue(sum(v.value for v in values))


def extract_lhs_rhs(op):
  return CalcOpSubexpressions(op.lhs, op.rhs)


def extract_op_type(op):
  return op.op_type


def cast(obj):
  return obj

#
#CalcValue -> CalcInt
#CalcValue -> CalcOpType, dependencies w/ values
#CalcOpType -> SelectProjection CalcOpType, CalcOp, ('wrapped'), CalcAst , identity
#
# I think it would be better if changing subjects and selecting products for the current subject
# were to be split into separate DSL concepts.
# What would that look like in the python DSL tho?
#

# Should a rule be the place where
# lhs_select(Z).select_for_current_subject(X).convert_subject(to=Y, by_fields=(a, b, c))
#  Look for an X for subject: C
#  Take X's a,b,c fields and construct a Y with their values
#  Look for a Z with the instantiated Y as the subject
#
#SelectProjection

#subject:CalcSource("1+1")
#select:Head,Tail
#Parse
#'product', 'projected_subject', 'fields', 'input_product'
#SelectProjection
RULES = [
  #1: [CalcAST, (Select(CalcSource)), parse_exp]
  (CalcAst, (Select(CalcSource),), parse),
  #2: [CalcValue, (Select(CalcInt)), int_to_val]
  (CalcValue, (Select(CalcInt),), int_to_val),

  #3: [CalcValue, (Select(CalcOpType), SelectDependencies(CalcValue, CalcOpSubexpressions)), perform_op]
  (CalcValue, (Select(CalcOpType), SelectDependencies(CalcValue, CalcOpSubexpressions)), perform_op),
  #4: [CalcOpSubexpressions, (Select(CalcOp)), extract_lhs_rhs]
  (CalcOpSubexpressions, (Select(CalcOp),), extract_lhs_rhs),

#5: [CalcOpType, (Select(CalcOp)), extract_op_type]
  (CalcOpType, (Select(CalcOp),), extract_op_type),
#6: [CalcInt, (Select(CalcAST)), cast]
(CalcInt, (Select(CalcAst),), identity),
#[CalcAst, (SelectProjection(CalcAst, CalcAst, ('wrapped',), input_product=CalcAst),), identity]

]


def traversability(subject_type, product_type):
  if subject_type is product_type:
    print('is traversable! s:{} p:{}'.format(subject_type, product_type))
    return True

  for i, r in enumerate(RULES):
    r_pt, clauses, fn = r
    if r_pt == product_type:
      print('gothere')
      #select_traversable = True
      for c in clauses:
        if isinstance(c, Select):
          if traversability(subject_type, c.product):
            print('through select of rule {} for {}'.format(i, c.product))
          else:
            return False
            #return True
        elif isinstance(c, SelectDependencies):
          dep_traverse_pt_i = traversability(subject_type, c.dep_product)
          if dep_traverse_pt_i:
            print("can at least say that you can reach the dep_product for the dependencies for rule No {}".format(i))
            #return True #hesitant true
          else:
            return False
        elif isinstance(c, SelectProjection):
          #SelectProjection(datatype('Projection', ['product', 'projected_subject', 'fields', 'input_product']), Selector):
          input_p_traversable = traversability(subject_type, c.input_product)
          if input_p_traversable:
            projection_traversable = traversability(c.projected_subject, c.product)
            if projection_traversable:
              print('projection traversable! rule {}'.format(i))
              #return True
            else:
              return False
          else:
            return False
      print('matched {!r}'.format(r))
      return True



goals = {
    'calc': CalcValue
  }


class NotSureWhatThisIsUsedFor(object):
  @classmethod
  def table(cls):
    return {}


def setup_json_scheduler(build_root, inline_nodes=True):
  """Return a build graph and scheduler configured for BLD.json files under the given build root.

  :rtype :class:`pants.engine.scheduler.LocalScheduler`
  """

  #symbol_table_cls = ExampleTable

  # Register "literal" subjects required for these tasks.
  # TODO: Replace with `Subsystems`.
  #address_mapper = AddressMapper(symbol_table_cls=symbol_table_cls,
  #                                                build_pattern=r'^BLD.json$',
  #                                                parser_cls=JsonParser)
  #source_roots = SourceRoots(('src/java','src/scala'))
  #scrooge_tool_address = Address.parse('src/scala/scrooge')


  project_tree = FileSystemProjectTree(build_root)
  return LocalScheduler(goals,
                        RULES,
                        project_tree,
                        graph_lock=None,
                        inline_nodes=inline_nodes,
                        graph_validator=GraphValidator(NotSureWhatThisIsUsedFor))


def main_addresses():
  print(traversability(CalcSource, CalcValue))
  #build_root, goals, args = pop_build_root_and_goals('[build root path] [goal]+ [address spec]*', sys.argv[1:])

  #cmd_line_spec_parser = CmdLineSpecParser(build_root)
  #spec_roots = [cmd_line_spec_parser.parse_spec(spec) for spec in args]
  build_root = '/whatever'
  visualize_build_request(build_root, goals, [CalcSource("1+1")])


def visualize_build_request(build_root, goals, subjects):
  scheduler = setup_json_scheduler(build_root)

  execution_request = scheduler.build_request(goals, subjects)
  # NB: Calls `reduce` independently of `execute`, in order to render a graph before validating it.
  engine = LocalSerialEngine(scheduler, Storage.create(debug=True))
  engine.start()
  try:
    engine.reduce(execution_request)
    visualize_execution_graph(scheduler, execution_request)
  finally:
    engine.close()


def visualize_execution_graph(scheduler, request):
  with temporary_file_path(cleanup=False, suffix='.dot') as dot_file:
    scheduler.visualize_graph_to_file(request.roots, dot_file)
    print('dot file saved to: {}'.format(dot_file))

  with temporary_file_path(cleanup=False, suffix='.svg') as image_file:
    subprocess.check_call('dot -Tsvg -o{} {}'.format(image_file, dot_file), shell=True)
    print('svg file saved to: {}'.format(image_file))
    binary_util.ui_open(image_file)
