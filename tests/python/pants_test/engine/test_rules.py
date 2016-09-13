# coding=utf-8
# Copyright 2015 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

import unittest
from collections import OrderedDict, deque
from textwrap import dedent

from pants.engine.addressable import Exactly
from pants.engine.rules import NodeBuilder, RulesetValidator
from pants.engine.selectors import Select
from pants.util.objects import datatype
from pants_test.engine.examples.planners import Goal


class AGoal(Goal):

  @classmethod
  def products(cls):
    return [A]


class A(object):

  def __repr__(self):
    return 'A()'


class B(object):

  def __repr__(self):
    return 'B()'


def noop(*args):
  pass


class SubA(A):

  def __repr__(self):
    return 'SubA()'


class NodeBuilderTest(unittest.TestCase):
  def test_creation_fails_with_bad_declaration_type(self):
    with self.assertRaises(TypeError) as cm:
      NodeBuilder.create([A()])
    self.assertEquals("Unexpected rule type: <class 'pants_test.engine.test_rules.A'>."
                      " Rules either extend Rule, or are 3 elem tuples.",
                      str(cm.exception))


class RulesetValidatorTest(unittest.TestCase):
  def test_ruleset_with_missing_product_type(self):
    rules = [(A, (Select(B),), noop)]
    validator = RulesetValidator(NodeBuilder.create(rules),
      goal_to_product=dict(),
      root_subject_types=tuple())
    with self.assertRaises(ValueError) as cm:
      validator.validate()

    self.assertEquals(dedent("""
                                Found 1 rules with errors:
                                  (A, (Select(B),), noop)
                                    There is no producer of Select(B)
                             """).strip(),
      str(cm.exception))

  def test_ruleset_with_rule_with_two_missing_selects(self):
    rules = [(A, (Select(B), Select(B)), noop)]
    validator = RulesetValidator(NodeBuilder.create(rules),
      goal_to_product=dict(),
      root_subject_types=tuple())
    with self.assertRaises(ValueError) as cm:
      validator.validate()

    self.assertEquals(dedent("""
                                Found 1 rules with errors:
                                  (A, (Select(B), Select(B)), noop)
                                    There is no producer of Select(B)
                                    There is no producer of Select(B)
                             """).strip(),
      str(cm.exception))

  def test_ruleset_with_with_selector_only_provided_as_root_subject(self):

    validator = RulesetValidator(NodeBuilder.create([(A, (Select(B),), noop)]),
      goal_to_product=dict(),
      root_subject_types=(B,))

    validator.validate()

  def test_ruleset_with_superclass_of_selected_type_produced_fails(self):

    rules = [
      (A, (Select(B),), noop),
      (B, (Select(SubA),), noop)
    ]
    validator = RulesetValidator(NodeBuilder.create(rules),
      goal_to_product=dict(),
      root_subject_types=tuple())

    with self.assertRaises(ValueError) as cm:
      validator.validate()
    self.assertEquals(dedent("""
                                Found 1 rules with errors:
                                  (B, (Select(SubA),), noop)
                                    There is no producer of Select(SubA)
                             """).strip(), str(cm.exception))

  def test_ruleset_with_goal_not_produced(self):
    rules = [
      (B, (Select(SubA),), noop)
    ]

    validator = RulesetValidator(NodeBuilder.create(rules),
      goal_to_product={'goal-name': AGoal},
      root_subject_types=tuple())
    with self.assertRaises(ValueError) as cm:
      validator.validate()

    self.assertEquals("no task for product used by goal \"goal-name\": <class 'pants_test.engine.test_rules.AGoal'>",
                      str(cm.exception))

  def test_ruleset_with_explicit_type_constraint(self):
    rules = [
      (Exactly(A), (Select(B),), noop),
      (B, (Select(A),), noop)
    ]
    validator = RulesetValidator(NodeBuilder.create(rules),
      goal_to_product=dict(),
      root_subject_types=tuple())

    validator.validate()


class Graph(datatype('Graph', ['root_subject', 'root_rules', 'rule_dependencies'])):

  def __str__(self):
    def key(r):
      return '"{}"'.format(r)

    return dedent("""
              {{
                root_subject: {}
                root_rules: {}
                {}

              }}""".format(self.root_subject, ', '.join(key(r) for r in self.root_rules),
    '\n                '.join('{} => ({},)'.format(rule, ', '.join(str(d) for d in deps)) for rule, deps in self.rule_dependencies.items())
    )).strip()


class Literal(datatype('Literal', ['value'])):
  """Product literal wrapper"""


class GraphMaker(object):

  def __init__(self, nodebuilder, goal_to_product, root_subject_types):
    self.root_subject_types = root_subject_types
    self.goal_to_product = goal_to_product
    self.nodebuilder = nodebuilder
    # naive
    # take the node builder index,
    # do another pass where we make a map of rule -> initial set of dependencies
    # then when generating a subgraph, follow all the dep to dep lists until have to give up
    #

  def get(self, subject, requested_product):

    root_subject = subject
    root_rules = tuple(self.nodebuilder.gen_rules(subject, requested_product))

    rule_dependency_edges = OrderedDict()
    #rules_by_some_name = {}
    rules_to_traverse = deque(root_rules)
    while rules_to_traverse:
      rule = rules_to_traverse.pop()
      for selector in rule.input_selectors:
        if type(selector) is Select:
          genned_rules = tuple(self.nodebuilder.gen_rules(subject, selector.product))
          rules_to_traverse.extend(g for g in genned_rules if g not in rule_dependency_edges)
          if type(subject) is selector.product:
            genned_rules += (Literal(subject),)
          rule_dependency_edges[rule] = genned_rules
        else:
          raise TypeError('cant handle a {} selector yet'.format(selector))

    return Graph(root_subject, root_rules, rule_dependency_edges)


class PremadeGraphTest(unittest.TestCase):

  # tests
  # print repr
  # noop subgraph elimination
  #
  # TODO something with variants
  def test_smallest_test(self):
    rules = [
      (Exactly(A), (Select(SubA),), noop)
    ]

    graphmaker = GraphMaker(NodeBuilder.create(rules),
      goal_to_product={'goal-name': AGoal},
      root_subject_types=tuple())
    subgraph = graphmaker.get(subject=SubA(), requested_product=A)

    self.assertEqual(dedent("""
                               {
                                 root_subject: SubA()
                                 root_rules: "(=A, (Select(SubA),), noop)"
                                 (=A, (Select(SubA),), noop) => (Literal(value=SubA()),)

                               }""").strip(),
      str(subgraph)
    )

  def test_something_or_other(self):
    #return
    rules = [
      (Exactly(A), (Select(B),), noop),
      (B, (Select(SubA),), noop)
    ]

    graphmaker = GraphMaker(NodeBuilder.create(rules),
      goal_to_product={'goal-name': AGoal},
      root_subject_types=tuple())
    subgraph = graphmaker.get(subject=SubA(), requested_product=A)

    self.assertEqual(dedent("""
                               {
                                 root_subject: SubA()
                                 root_rules: "(=A, (Select(B),), noop)"
                                 (=A, (Select(B),), noop) => ((B, (Select(SubA),), noop),)
                                 (B, (Select(SubA),), noop) => (Literal(value=SubA()),)

                               }""").strip(),
      str(subgraph)
    )
