# coding=utf-8
# Copyright 2016 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

from abc import abstractmethod, abstractproperty

from pants.util.meta import AbstractClass


class Rule(AbstractClass):
  @abstractmethod
  def as_node(self, subject, product, variants):
    pass

  @abstractproperty
  def output_product_type(self):
    pass

  @abstractproperty
  def input_selects(self):
    pass
