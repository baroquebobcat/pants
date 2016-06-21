# coding=utf-8
# Copyright 2016 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

from abc import abstractmethod, abstractproperty

from pants.util.meta import AbstractClass


class Rule(AbstractClass):
  """This abstract class represents rules and their common properties.

   The idea is that the scheduler can lean on this abstraction to figure out how to create nodes
   from the tasks or intrinsics it supports"""

  @abstractmethod
  def as_node(self, subject, product_type, variants):
    pass

  @abstractproperty
  def output_product_type(self):
    pass

  @abstractproperty
  def input_selects(self):
    pass
