# coding=utf-8
# Copyright 2016 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

from collections import namedtuple


def datatype(*args, **kwargs):
  """A wrapper for `namedtuple` that accounts for the type of the object in equality.

  :param is_iterable: If passed as True, then the resulting type will be iterable. False by default.
  """
  is_iterable = kwargs.pop('is_iterable', False)
  class DataType(namedtuple(*args, **kwargs)):
    def __eq__(self, other):
      if self is other:
        return True

      # Compare types and fields.
      if type(self) != type(other):
        return False
      # Explicitly return super.__eq__'s value in case super returns NotImplemented
      return super(DataType, self).__eq__(other)

    def __ne__(self, other):
      return not (self == other)

    if not is_iterable:
      def __iter__(self):
        raise TypeError("'{}' object is not iterable".format(type(self).__name__))
  return DataType
